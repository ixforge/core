"""IPAM service: IP pool management and address allocation."""

import ipaddress
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.exceptions import ConflictError, NotFoundError, ValidationError
from ixforge.models.ip import IPAssignment, IPPool
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.schemas.ip import IPAssignmentRead, IPPoolCreate, IPPoolRead
from ixforge.services.base import paginate


async def create_pool(
    session: AsyncSession,
    data: IPPoolCreate,
) -> IPPool:
    """Create an IP pool."""
    # Validate that network is valid CIDR and gateway is within it.
    try:
        network = ipaddress.ip_network(data.network, strict=False)
    except ValueError as exc:
        raise ValidationError(f"Invalid network CIDR: {data.network}") from exc

    try:
        gateway = ipaddress.ip_address(data.gateway)
    except ValueError as exc:
        raise ValidationError(f"Invalid gateway address: {data.gateway}") from exc

    if gateway not in network:
        raise ValidationError(f"Gateway {data.gateway} is not within network {data.network}")

    expected_af = 4 if network.version == 4 else 6
    if data.af != expected_af:
        raise ValidationError(
            f"Address family mismatch: network is IPv{network.version} but af={data.af}"
        )

    pool = IPPool(
        vlan_id=data.vlan_id,
        network=data.network,
        gateway=data.gateway,
        af=data.af,
    )
    session.add(pool)
    await session.flush()
    return pool


async def get_pool(session: AsyncSession, pool_id: uuid.UUID) -> IPPool:
    """Get an IP pool by id or raise NotFoundError."""
    pool = await session.get(IPPool, pool_id)
    if pool is None:
        raise NotFoundError("IPPool", str(pool_id))
    return pool


async def list_pools(
    session: AsyncSession,
    vlan_id: uuid.UUID,
    params: CursorParams,
) -> CursorPage[IPPoolRead]:
    """List IP pools for a VLAN with cursor-based pagination."""
    stmt = select(IPPool).where(IPPool.vlan_id == vlan_id)
    return await paginate(
        session,
        stmt,
        params,
        sort_column=IPPool.created_at,
        id_column=IPPool.id,
        schema=IPPoolRead,
    )


async def delete_pool(session: AsyncSession, pool_id: uuid.UUID) -> None:
    """Delete an IP pool."""
    pool = await get_pool(session, pool_id)
    await session.delete(pool)
    await session.flush()


def _reserved_addresses(
    network: ipaddress.IPv4Network | ipaddress.IPv6Network,
    gateway: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Return the set of addresses that cannot be assigned (network, broadcast, gateway)."""
    reserved: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = {gateway}
    # IPv4: reservar network y broadcast solo para prefijos menores a /31
    # /31 (RFC 3021): ambas IPs son usables, solo reservar gateway
    # /32: single host, solo reservar gateway
    if isinstance(network, ipaddress.IPv4Network) and network.prefixlen < 31:
        reserved.add(network.network_address)
        reserved.add(network.broadcast_address)
    return reserved


async def _get_used_addresses(session: AsyncSession, pool_id: uuid.UUID) -> set[str]:
    """Return all addresses currently assigned in a pool."""
    stmt = select(IPAssignment.address).where(IPAssignment.pool_id == pool_id)
    result = await session.execute(stmt)
    return {row[0] for row in result.all()}


def _validate_address_in_pool(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
    network: ipaddress.IPv4Network | ipaddress.IPv6Network,
    gateway: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> None:
    """Validate that an address is usable within the pool."""
    if address not in network:
        raise ValidationError(f"Address {address} is not within network {network}")

    reserved = _reserved_addresses(network, gateway)
    if address in reserved:
        raise ValidationError(f"Address {address} is reserved (network, broadcast, or gateway)")


async def _check_global_uniqueness(
    session: AsyncSession,
    address_str: str,
) -> None:
    """Ensure the address is not assigned anywhere in the system."""
    existing = await session.scalar(
        select(IPAssignment.id).where(IPAssignment.address == address_str).limit(1)
    )
    if existing is not None:
        raise ConflictError(f"Address {address_str} is already assigned")


async def allocate_sequential(
    session: AsyncSession,
    pool_id: uuid.UUID,
    connection_id: uuid.UUID,
) -> IPAssignment:
    """Allocate the next available IP address in a pool."""
    pool = await session.get(IPPool, pool_id, with_for_update=True)
    if pool is None:
        raise NotFoundError("IPPool", str(pool_id))
    network = ipaddress.ip_network(pool.network, strict=False)
    gateway = ipaddress.ip_address(pool.gateway)
    reserved = _reserved_addresses(network, gateway)
    used = await _get_used_addresses(session, pool_id)

    for host in network:
        if host in reserved:
            continue
        address_str = str(host)
        if address_str in used:
            continue

        # Found an available address; verify global uniqueness.
        await _check_global_uniqueness(session, address_str)

        assignment = IPAssignment(
            pool_id=pool_id,
            connection_id=connection_id,
            address=address_str,
        )
        session.add(assignment)
        try:
            await session.flush()
        except IntegrityError:
            raise ConflictError(f"Address {address_str} was allocated concurrently") from None
        return assignment

    raise ConflictError(f"No available addresses in pool {pool.network}")


async def allocate_manual(
    session: AsyncSession,
    pool_id: uuid.UUID,
    connection_id: uuid.UUID,
    address: str,
) -> IPAssignment:
    """Allocate a specific IP address from a pool."""
    pool = await session.get(IPPool, pool_id, with_for_update=True)
    if pool is None:
        raise NotFoundError("IPPool", str(pool_id))
    network = ipaddress.ip_network(pool.network, strict=False)
    gateway = ipaddress.ip_address(pool.gateway)

    try:
        addr = ipaddress.ip_address(address)
    except ValueError as exc:
        raise ValidationError(f"Invalid IP address: {address}") from exc

    _validate_address_in_pool(addr, network, gateway)
    await _check_global_uniqueness(session, address)

    assignment = IPAssignment(
        pool_id=pool_id,
        connection_id=connection_id,
        address=address,
    )
    session.add(assignment)
    try:
        await session.flush()
    except IntegrityError:
        raise ConflictError(f"Address {address} was allocated concurrently") from None
    return assignment


async def release(session: AsyncSession, assignment_id: uuid.UUID) -> None:
    """Release an IP assignment."""
    assignment = await session.get(IPAssignment, assignment_id)
    if assignment is None:
        raise NotFoundError("IPAssignment", str(assignment_id))
    await session.delete(assignment)
    await session.flush()


async def list_assignments(
    session: AsyncSession,
    pool_id: uuid.UUID,
    params: CursorParams,
) -> CursorPage[IPAssignmentRead]:
    """List IP assignments in a pool with cursor-based pagination."""
    stmt = select(IPAssignment).where(IPAssignment.pool_id == pool_id)
    return await paginate(
        session,
        stmt,
        params,
        sort_column=IPAssignment.created_at,
        id_column=IPAssignment.id,
        schema=IPAssignmentRead,
    )

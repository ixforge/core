"""IPAM service: IP pool management and address allocation."""

import ipaddress
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.exceptions import ConflictError, NotFoundError, ValidationError
from ixforge.models.connection import Connection
from ixforge.models.ip import IPAssignment, IPPool
from ixforge.models.member import Member
from ixforge.models.vlan import VLAN
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.schemas.ip import IPAssignmentRead, IPPoolCreate, IPPoolRead
from ixforge.services.base import paginate


async def create_pool(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    data: IPPoolCreate,
) -> IPPool:
    """Create an IP pool."""
    # Validate that network is valid CIDR
    try:
        network = ipaddress.ip_network(data.network, strict=False)
    except ValueError as exc:
        raise ValidationError(f"Invalid network CIDR: {data.network}") from exc

    expected_af = 4 if network.version == 4 else 6
    if data.af != expected_af:
        raise ValidationError(
            f"Address family mismatch: network is IPv{network.version} but af={data.af}"
        )

    pool = IPPool(
        ixp_id=ixp_id,
        vlan_id=data.vlan_id,
        network=data.network,
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

    has_assignments = await session.scalar(
        select(IPAssignment.id)
        .where(IPAssignment.pool_id == pool_id)
        .limit(1)
    )
    if has_assignments is not None:
        raise ConflictError(
            "Cannot delete pool: release all IP assignments first"
        )

    await session.delete(pool)
    await session.flush()


def _reserved_addresses(
    network: ipaddress.IPv4Network | ipaddress.IPv6Network,
) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Return the set of addresses that cannot be assigned (network, broadcast)."""
    reserved: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
    # IPv4: reservar network y broadcast solo para prefijos menores a /31
    # /31 (RFC 3021): ambas IPs son usables
    # /32: single host
    if isinstance(network, ipaddress.IPv4Network) and network.prefixlen < 31:
        reserved.add(network.network_address)
        reserved.add(network.broadcast_address)
    return reserved


async def _get_used_addresses(
    session: AsyncSession, pool_id: uuid.UUID, *, lock: bool = False
) -> set[str]:
    """Return all addresses currently assigned in a pool.

    When lock=True, uses FOR UPDATE to prevent concurrent allocations
    from seeing the same set of available addresses.
    """
    stmt = select(IPAssignment.address).where(IPAssignment.pool_id == pool_id)
    if lock:
        stmt = stmt.with_for_update()
    result = await session.execute(stmt)
    return {row[0] for row in result.all()}


async def _validate_pool_connection_same_tenant(
    session: AsyncSession,
    pool_id: uuid.UUID,
    connection_id: uuid.UUID,
) -> None:
    """Validate that the pool and connection belong to the same IXP."""
    pool = await session.get(IPPool, pool_id)
    if pool is None:
        raise NotFoundError("IPPool", str(pool_id))

    vlan = await session.get(VLAN, pool.vlan_id)
    if vlan is None:
        raise NotFoundError("VLAN", str(pool.vlan_id))

    connection = await session.get(Connection, connection_id)
    if connection is None:
        raise NotFoundError("Connection", str(connection_id))

    member = await session.get(Member, connection.member_id)
    if member is None:
        raise NotFoundError("Member", str(connection.member_id))

    if vlan.ixp_id != member.ixp_id:
        raise ValidationError("IP pool and connection belong to different IXPs")


def _validate_address_in_pool(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
    network: ipaddress.IPv4Network | ipaddress.IPv6Network,
) -> None:
    """Validate that an address is usable within the pool."""
    if address not in network:
        raise ValidationError(f"Address {address} is not within network {network}")

    reserved = _reserved_addresses(network)
    if address in reserved:
        raise ValidationError(f"Address {address} is reserved (network or broadcast)")


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
    ixp_id: uuid.UUID,
    pool_id: uuid.UUID,
    connection_id: uuid.UUID,
) -> IPAssignment:
    """Allocate the next available IP address in a pool."""
    await _validate_pool_connection_same_tenant(session, pool_id, connection_id)

    pool = await session.get(IPPool, pool_id, with_for_update=True)
    if pool is None:
        raise NotFoundError("IPPool", str(pool_id))
    network = ipaddress.ip_network(pool.network, strict=False)
    reserved = _reserved_addresses(network)
    # Lock existing assignments to prevent concurrent allocations
    used = await _get_used_addresses(session, pool_id, lock=True)

    for host in network:
        if host in reserved:
            continue
        address_str = str(host)
        if address_str in used:
            continue

        # Found an available address; verify global uniqueness.
        await _check_global_uniqueness(session, address_str)

        assignment = IPAssignment(
            ixp_id=ixp_id,
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
    ixp_id: uuid.UUID,
    pool_id: uuid.UUID,
    connection_id: uuid.UUID,
    address: str,
) -> IPAssignment:
    """Allocate a specific IP address from a pool."""
    await _validate_pool_connection_same_tenant(session, pool_id, connection_id)

    pool = await session.get(IPPool, pool_id, with_for_update=True)
    if pool is None:
        raise NotFoundError("IPPool", str(pool_id))
    network = ipaddress.ip_network(pool.network, strict=False)

    try:
        addr = ipaddress.ip_address(address)
    except ValueError as exc:
        raise ValidationError(f"Invalid IP address: {address}") from exc

    _validate_address_in_pool(addr, network)
    await _check_global_uniqueness(session, address)

    assignment = IPAssignment(
        ixp_id=ixp_id,
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

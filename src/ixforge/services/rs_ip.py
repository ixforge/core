"""RS IP assignment service: allocate/release IPs from pool for route servers."""

import ipaddress
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.exceptions import ConflictError, NotFoundError, ValidationError
from ixforge.models.ip import IPAssignment, IPPool
from ixforge.models.route_server import RouteServer
from ixforge.models.rs_ip_assignment import RSIPAssignment
from ixforge.schemas.rs_ip import RSIPAssignmentCreate, RSIPAssignmentRead
from ixforge.services.ipam import _reserved_addresses, _validate_address_in_pool


async def _get_rs_used_in_pool(session: AsyncSession, pool_id: uuid.UUID) -> set[str]:
    """Return all addresses currently in use in the pool across both member and RS assignments."""
    member_result = await session.execute(
        select(IPAssignment.address).where(IPAssignment.pool_id == pool_id).with_for_update()
    )
    rs_result = await session.execute(
        select(RSIPAssignment.address).where(RSIPAssignment.pool_id == pool_id).with_for_update()
    )
    return {row[0] for row in member_result.all()} | {row[0] for row in rs_result.all()}


async def _check_address_unique(session: AsyncSession, address: str) -> None:
    """Ensure the address is not already assigned within the current tenant context."""
    in_member = await session.scalar(
        select(IPAssignment.id).where(IPAssignment.address == address).limit(1)
    )
    if in_member is not None:
        raise ConflictError(f"Address {address} is already assigned to a member connection")
    in_rs = await session.scalar(
        select(RSIPAssignment.id).where(RSIPAssignment.address == address).limit(1)
    )
    if in_rs is not None:
        raise ConflictError(f"Address {address} is already assigned to a route server")


async def list_assignments(session: AsyncSession, ixp_id: uuid.UUID, rs_id: uuid.UUID) -> list[RSIPAssignmentRead]:
    """List all IP assignments for a route server."""
    rs = await session.get(RouteServer, rs_id)
    if rs is None or rs.ixp_id != ixp_id:
        raise NotFoundError("RouteServer", str(rs_id))
    result = await session.execute(
        select(RSIPAssignment).where(RSIPAssignment.route_server_id == rs_id)
    )
    return [RSIPAssignmentRead.model_validate(r) for r in result.scalars().all()]


async def assign(
    session: AsyncSession, ixp_id: uuid.UUID, rs_id: uuid.UUID, data: RSIPAssignmentCreate
) -> RSIPAssignment:
    """Allocate an IP from a pool and assign it to a route server."""
    rs = await session.get(RouteServer, rs_id)
    if rs is None or rs.ixp_id != ixp_id:
        raise NotFoundError("RouteServer", str(rs_id))

    pool = await session.get(IPPool, data.pool_id, with_for_update=True)
    if pool is None:
        raise NotFoundError("IPPool", str(data.pool_id))

    if pool.ixp_id != ixp_id:
        raise ValidationError("IP pool belongs to a different IXP")

    network = ipaddress.ip_network(pool.network, strict=False)
    af = 4 if network.version == 4 else 6

    existing = await session.scalar(
        select(RSIPAssignment.id).where(
            RSIPAssignment.route_server_id == rs_id,
            RSIPAssignment.af == af,
        ).limit(1)
    )
    if existing is not None:
        raise ConflictError(f"Route server already has an IPv{af} assignment")

    if data.address is not None:
        try:
            addr = ipaddress.ip_address(data.address)
        except ValueError as exc:
            raise ValidationError(f"Invalid IP address: {data.address}") from exc
        _validate_address_in_pool(addr, network)
        address_str = str(addr)
        await _check_address_unique(session, address_str)
    else:
        reserved = _reserved_addresses(network)
        used = await _get_rs_used_in_pool(session, data.pool_id)
        address_str = None
        for host in network:
            if host in reserved:
                continue
            candidate = str(host)
            if candidate in used:
                continue
            # Verify global uniqueness across all pools
            try:
                await _check_address_unique(session, candidate)
            except ConflictError:
                continue
            address_str = candidate
            break
        if address_str is None:
            raise ConflictError(f"No available addresses in pool {pool.network}")

    assignment = RSIPAssignment(
        ixp_id=ixp_id,
        route_server_id=rs_id,
        pool_id=data.pool_id,
        address=address_str,
        af=af,
    )
    session.add(assignment)
    try:
        await session.flush()
    except IntegrityError:
        raise ConflictError(f"Address {address_str} was allocated concurrently") from None

    if af == 4:
        rs.ip_v4 = address_str
    else:
        rs.ip_v6 = address_str
    await session.flush()

    return assignment


async def release(session: AsyncSession, ixp_id: uuid.UUID, rs_id: uuid.UUID, assignment_id: uuid.UUID) -> None:
    """Release an RS IP assignment and clear the corresponding rs.ip_v4 or rs.ip_v6."""
    assignment = await session.get(RSIPAssignment, assignment_id)
    if assignment is None or assignment.ixp_id != ixp_id:
        raise NotFoundError("RSIPAssignment", str(assignment_id))
    if assignment.route_server_id != rs_id:
        raise NotFoundError("RSIPAssignment", str(assignment_id))

    rs = await session.get(RouteServer, rs_id)
    if rs is None:
        raise NotFoundError("RouteServer", str(rs_id))
    if assignment.af == 4:
        rs.ip_v4 = None
    else:
        rs.ip_v6 = None

    await session.delete(assignment)
    await session.flush()

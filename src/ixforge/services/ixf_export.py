"""IX-F Member Export JSON generation (schema v1.0).

Builds the IX-F Member Export JSON consumed by PeeringDB and other tools.
Reference: https://github.com/euro-ix/json-schemas
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from ixforge.enums import ConnectionState, MemberState, VLANType
from ixforge.models.connection import Connection, ConnectionVLAN
from ixforge.models.ip import IPAssignment, IPPool
from ixforge.models.ixp import IXP
from ixforge.models.member import Member
from ixforge.models.port import Port
from ixforge.models.vlan import VLAN

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


async def generate_ixf_member_export(
    session: AsyncSession,
    ixp_id: uuid.UUID,
) -> dict[str, Any]:
    """Generate IX-F Member Export JSON (schema v1.0) for a given IXP.

    Only includes active members with at least one active connection
    that has assigned IP addresses.
    """
    # Fetch the IXP record.
    ixp = await session.get(IXP, ixp_id)
    if ixp is None:
        return _empty_export()

    # Fetch all production VLANs for this IXP (used in vlan_list).
    vlans = await _get_vlans(session, ixp_id)
    vlan_list = [{"vlan_id": vlan.vid, "name": vlan.name} for vlan in vlans]

    # Build a lookup from VLAN UUID -> vid for later use.
    vlan_vid_map: dict[uuid.UUID, int] = {v.id: v.vid for v in vlans}

    # Fetch active members.
    members = await _get_active_members(session, ixp_id)

    member_list: list[dict[str, Any]] = []
    for member in members:
        connections = await _get_active_connections(session, member.id)
        if not connections:
            continue

        connection_list: list[dict[str, Any]] = []
        for conn in connections:
            conn_entry = await _build_connection_entry(
                session,
                conn,
                ixp,
                vlan_vid_map,
            )
            if conn_entry is not None:
                connection_list.append(conn_entry)

        if not connection_list:
            continue

        member_entry: dict[str, Any] = {
            "asnum": member.asn,
            "name": member.name,
            "url": member.website or "",
            "peering_policy": member.peering_policy,
            "connection_list": connection_list,
        }
        member_list.append(member_entry)

    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        "version": "1.0",
        "timestamp": timestamp,
        "ixp_list": [
            {
                "ixp_id": ixp.peeringdb_id or 0,
                "shortname": ixp.short_name,
                "name": ixp.name,
                "vlan": vlan_list,
            },
        ],
        "member_list": member_list,
    }


def _empty_export() -> dict[str, Any]:
    """Return an empty but valid IX-F export structure."""
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "version": "1.0",
        "timestamp": timestamp,
        "ixp_list": [],
        "member_list": [],
    }


async def _get_vlans(session: AsyncSession, ixp_id: uuid.UUID) -> list[VLAN]:
    """Fetch production VLANs for an IXP."""
    stmt = (
        select(VLAN)
        .where(VLAN.ixp_id == ixp_id, VLAN.type == VLANType.production)
        .order_by(VLAN.vid)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _get_active_members(session: AsyncSession, ixp_id: uuid.UUID) -> list[Member]:
    """Fetch active members for an IXP."""
    stmt = (
        select(Member)
        .where(Member.ixp_id == ixp_id, Member.state == MemberState.active)
        .order_by(Member.asn)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _get_active_connections(session: AsyncSession, member_id: uuid.UUID) -> list[Connection]:
    """Fetch active connections for a member."""
    stmt = (
        select(Connection)
        .where(Connection.member_id == member_id, Connection.state == ConnectionState.active)
        .order_by(Connection.created_at)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _build_connection_entry(
    session: AsyncSession,
    conn: Connection,
    ixp: IXP,
    vlan_vid_map: dict[uuid.UUID, int],
) -> dict[str, Any] | None:
    """Build a single connection entry for the IX-F export.

    Returns None if the connection has no IP assignments (skip it).
    """
    # Get IP assignments for this connection.
    ip_assignments = await _get_ip_assignments(session, conn.id)
    if not ip_assignments:
        return None

    # Build if_list from the connection's port.
    if_list: list[dict[str, Any]] = []
    if conn.port_id is not None:
        port = await session.get(Port, conn.port_id)
        if port is not None:
            if_entry: dict[str, Any] = {
                "switch_id": str(port.switch_id),
                "if_speed": port.speed,
                "if_type": "LAN",
            }
            if_list.append(if_entry)

    # Build vlan_list from connection's VLAN assignments and IP addresses.
    vlan_list = await _build_vlan_list(session, conn.id, ip_assignments, vlan_vid_map)

    return {
        "ixp_id": ixp.peeringdb_id or 0,
        "state": "active",
        "if_list": if_list,
        "vlan_list": vlan_list,
    }


async def _get_ip_assignments(
    session: AsyncSession, connection_id: uuid.UUID
) -> list[IPAssignment]:
    """Fetch IP assignments for a connection."""
    stmt = (
        select(IPAssignment)
        .where(IPAssignment.connection_id == connection_id)
        .order_by(IPAssignment.address)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _build_vlan_list(
    session: AsyncSession,
    connection_id: uuid.UUID,
    ip_assignments: list[IPAssignment],
    vlan_vid_map: dict[uuid.UUID, int],
) -> list[dict[str, Any]]:
    """Build the vlan_list for a connection entry.

    Groups IP assignments by their VLAN (via the IP pool -> VLAN relationship)
    and the connection's VLAN assignments.
    """
    # Get connection VLAN assignments.
    stmt = select(ConnectionVLAN).where(ConnectionVLAN.connection_id == connection_id)
    result = await session.execute(stmt)
    conn_vlans = list(result.scalars().all())

    # Build a lookup: pool_id -> IPPool (to get the VLAN for each IP).
    pool_ids = {ip_assign.pool_id for ip_assign in ip_assignments}
    pools: dict[uuid.UUID, IPPool] = {}
    for pool_id in pool_ids:
        pool = await session.get(IPPool, pool_id)
        if pool is not None:
            pools[pool_id] = pool

    # Group IPs by VLAN ID.
    vlan_ips: dict[uuid.UUID, dict[str, str]] = {}
    for ip_assign in ip_assignments:
        pool = pools.get(ip_assign.pool_id)
        if pool is None:
            continue

        vlan_uuid = pool.vlan_id
        if vlan_uuid not in vlan_ips:
            vlan_ips[vlan_uuid] = {}

        if pool.af == 4:
            vlan_ips[vlan_uuid]["ipv4"] = ip_assign.address
        elif pool.af == 6:
            vlan_ips[vlan_uuid]["ipv6"] = ip_assign.address

    # If there are no IPs grouped by VLANs, try to build from ConnectionVLAN entries.
    vlan_uuids = set(vlan_ips.keys())
    for cv in conn_vlans:
        if cv.vlan_id not in vlan_uuids:
            vlan_uuids.add(cv.vlan_id)

    vlan_list: list[dict[str, Any]] = []
    for vlan_uuid in sorted(vlan_uuids, key=lambda v: vlan_vid_map.get(v, 0)):
        vid = vlan_vid_map.get(vlan_uuid, 0)
        entry: dict[str, Any] = {"vlan_id": vid}

        ips = vlan_ips.get(vlan_uuid, {})
        if "ipv4" in ips:
            entry["ipv4"] = {"address": ips["ipv4"]}
        if "ipv6" in ips:
            entry["ipv6"] = {"address": ips["ipv6"]}

        vlan_list.append(entry)

    return vlan_list

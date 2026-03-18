"""IX-F Member Export JSON generation (schema v1.0).

Builds the IX-F Member Export JSON consumed by PeeringDB and other tools.
Reference: https://github.com/euro-ix/json-schemas
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from ixforge.enums import ConnectionState, MemberState, TrunkState, VLANType
from ixforge.models.connection import Connection
from ixforge.models.ip import IPAssignment, IPPool
from ixforge.models.ixp import IXP
from ixforge.models.member import Member
from ixforge.models.trunk import Trunk, TrunkVLAN
from ixforge.models.vlan import VLAN

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


async def generate_ixf_member_export(
    session: AsyncSession,
    ixp_id: uuid.UUID,
) -> dict[str, Any]:
    """Generate IX-F Member Export JSON (schema v1.0) for a given IXP.

    Only includes active members with at least one active trunk
    that has at least one active connection with assigned IP addresses.
    """
    ixp = await session.get(IXP, ixp_id)
    if ixp is None:
        return _empty_export()

    vlans = await _get_vlans(session, ixp_id)
    vlan_list = [{"vlan_id": vlan.vid, "name": vlan.name} for vlan in vlans]
    vlan_vid_map: dict[uuid.UUID, int] = {v.id: v.vid for v in vlans}

    members = await _get_active_members(session, ixp_id)
    if not members:
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
            "member_list": [],
        }

    member_ids = [m.id for m in members]
    bulk_data = await _load_bulk_data(session, member_ids)

    member_list: list[dict[str, Any]] = []
    for member in members:
        trunks = bulk_data.trunks_by_member.get(member.id, [])
        if not trunks:
            continue

        connection_list: list[dict[str, Any]] = []
        for trunk in trunks:
            conn_entry = _build_connection_entry(
                trunk,
                ixp,
                vlan_vid_map,
                bulk_data,
            )
            if conn_entry is not None:
                connection_list.append(conn_entry)

        if not connection_list:
            continue

        member_entry: dict[str, Any] = {
            "asnum": member.asn,
            "member_since": member.created_at.strftime("%Y-%m-%dT00:00:00Z"),
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
    """Fetch active members for an IXP, excluding those flagged to skip IXF export."""
    stmt = (
        select(Member)
        .where(
            Member.ixp_id == ixp_id,
            Member.state == MemberState.active,
            Member.skip_ixf_export == False,  # noqa: E712
        )
        .order_by(Member.asn)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


class _BulkData:
    """Container for bulk-loaded data to avoid N+1 queries."""

    def __init__(
        self,
        trunks_by_member: dict[uuid.UUID, list[Trunk]],
        connections_by_trunk: dict[uuid.UUID, list[Connection]],
        ip_assignments_by_trunk_vlan: dict[uuid.UUID, list[IPAssignment]],
        trunk_vlans_by_trunk: dict[uuid.UUID, list[TrunkVLAN]],
        pools: dict[uuid.UUID, IPPool],
    ) -> None:
        self.trunks_by_member = trunks_by_member
        self.connections_by_trunk = connections_by_trunk
        self.ip_assignments_by_trunk_vlan = ip_assignments_by_trunk_vlan
        self.trunk_vlans_by_trunk = trunk_vlans_by_trunk
        self.pools = pools


async def _load_bulk_data(session: AsyncSession, member_ids: list[uuid.UUID]) -> _BulkData:
    """Load all necessary data in bulk to avoid N+1 queries."""
    # Load active trunks for members
    stmt = (
        select(Trunk)
        .where(
            Trunk.member_id.in_(member_ids),
            Trunk.state == TrunkState.active,
        )
        .order_by(Trunk.member_id, Trunk.created_at)
    )
    result = await session.execute(stmt)
    trunks = list(result.scalars().all())

    trunks_by_member: dict[uuid.UUID, list[Trunk]] = {}
    for trunk in trunks:
        if trunk.member_id not in trunks_by_member:
            trunks_by_member[trunk.member_id] = []
        trunks_by_member[trunk.member_id].append(trunk)

    trunk_ids = [t.id for t in trunks]
    if not trunk_ids:
        return _BulkData({}, {}, {}, {}, {})

    # Load active connections for trunks
    conn_result = await session.execute(
        select(Connection)
        .where(
            Connection.trunk_id.in_(trunk_ids),
            Connection.state == ConnectionState.active,
        )
        .order_by(Connection.trunk_id, Connection.created_at)
    )
    all_connections = list(conn_result.scalars().all())

    connections_by_trunk: dict[uuid.UUID, list[Connection]] = {}
    for conn in all_connections:
        if conn.trunk_id not in connections_by_trunk:
            connections_by_trunk[conn.trunk_id] = []
        connections_by_trunk[conn.trunk_id].append(conn)

    # Load trunk VLANs
    tv_result = await session.execute(
        select(TrunkVLAN).where(TrunkVLAN.trunk_id.in_(trunk_ids))
    )
    all_trunk_vlans = list(tv_result.scalars().all())

    trunk_vlans_by_trunk: dict[uuid.UUID, list[TrunkVLAN]] = {}
    trunk_vlan_ids: list[uuid.UUID] = []
    for tv in all_trunk_vlans:
        if tv.trunk_id not in trunk_vlans_by_trunk:
            trunk_vlans_by_trunk[tv.trunk_id] = []
        trunk_vlans_by_trunk[tv.trunk_id].append(tv)
        trunk_vlan_ids.append(tv.id)

    # Load IP assignments by trunk_vlan_id
    ip_assignments_by_trunk_vlan: dict[uuid.UUID, list[IPAssignment]] = {}
    if trunk_vlan_ids:
        ip_result = await session.execute(
            select(IPAssignment)
            .where(IPAssignment.trunk_vlan_id.in_(trunk_vlan_ids))
            .order_by(IPAssignment.trunk_vlan_id, IPAssignment.address)
        )
        all_ip_assignments = list(ip_result.scalars().all())

        for ip_assign in all_ip_assignments:
            if ip_assign.trunk_vlan_id not in ip_assignments_by_trunk_vlan:
                ip_assignments_by_trunk_vlan[ip_assign.trunk_vlan_id] = []
            ip_assignments_by_trunk_vlan[ip_assign.trunk_vlan_id].append(ip_assign)

        pool_ids = list({ip.pool_id for ip in all_ip_assignments})
    else:
        pool_ids = []

    pools: dict[uuid.UUID, IPPool] = {}
    if pool_ids:
        pool_result = await session.execute(select(IPPool).where(IPPool.id.in_(pool_ids)))
        pools = {p.id: p for p in pool_result.scalars().all()}

    return _BulkData(
        trunks_by_member=trunks_by_member,
        connections_by_trunk=connections_by_trunk,
        ip_assignments_by_trunk_vlan=ip_assignments_by_trunk_vlan,
        trunk_vlans_by_trunk=trunk_vlans_by_trunk,
        pools=pools,
    )


def _build_connection_entry(
    trunk: Trunk,
    ixp: IXP,
    vlan_vid_map: dict[uuid.UUID, int],
    bulk_data: _BulkData,
) -> dict[str, Any] | None:
    """Build a single IX-F connection entry from a Trunk.

    Trunk = IX-F connection, Connection = IX-F interface (if_list item).
    Returns None if the trunk has no IP assignments (skip it).
    """
    # Collect all IP assignments across trunk VLANs
    trunk_vlans = bulk_data.trunk_vlans_by_trunk.get(trunk.id, [])
    all_ip_assignments: list[IPAssignment] = []
    for tv in trunk_vlans:
        all_ip_assignments.extend(bulk_data.ip_assignments_by_trunk_vlan.get(tv.id, []))

    if not all_ip_assignments:
        return None

    # Build if_list from the trunk's active connections
    connections = bulk_data.connections_by_trunk.get(trunk.id, [])
    if_list: list[dict[str, Any]] = []
    for conn in connections:
        if conn.switch_id is not None:
            if_entry: dict[str, Any] = {
                "switch_id": str(conn.switch_id),
                "if_speed": conn.speed * 1_000_000,
                "if_type": "LAN",
            }
            if_list.append(if_entry)

    vlan_list = _build_vlan_list(trunk.id, all_ip_assignments, vlan_vid_map, bulk_data)

    return {
        "ixp_id": ixp.peeringdb_id or 0,
        "state": "active",
        "if_list": if_list,
        "vlan_list": vlan_list,
    }


def _build_vlan_list(
    trunk_id: uuid.UUID,
    ip_assignments: list[IPAssignment],
    vlan_vid_map: dict[uuid.UUID, int],
    bulk_data: _BulkData,
) -> list[dict[str, Any]]:
    """Build the vlan_list for a connection entry.

    Groups IP assignments by their VLAN (via the IP pool -> VLAN relationship)
    and the trunk's VLAN assignments.
    """
    trunk_vlans = bulk_data.trunk_vlans_by_trunk.get(trunk_id, [])

    vlan_ips: dict[uuid.UUID, dict[str, str]] = {}
    for ip_assign in ip_assignments:
        pool = bulk_data.pools.get(ip_assign.pool_id)
        if pool is None:
            continue

        vlan_uuid = pool.vlan_id
        if vlan_uuid not in vlan_ips:
            vlan_ips[vlan_uuid] = {}

        if pool.af == 4:
            vlan_ips[vlan_uuid]["ipv4"] = ip_assign.address
        elif pool.af == 6:
            vlan_ips[vlan_uuid]["ipv6"] = ip_assign.address

    vlan_uuids = set(vlan_ips.keys())
    for tv in trunk_vlans:
        if tv.vlan_id not in vlan_uuids:
            vlan_uuids.add(tv.vlan_id)

    vlan_list: list[dict[str, Any]] = []
    for vlan_uuid in sorted(vlan_uuids, key=lambda v: vlan_vid_map.get(v, 0)):
        vid = vlan_vid_map.get(vlan_uuid)
        if vid is None:
            continue
        entry: dict[str, Any] = {"vlan_id": vid}

        ips = vlan_ips.get(vlan_uuid, {})
        if "ipv4" in ips:
            entry["ipv4"] = {"address": ips["ipv4"]}
        if "ipv6" in ips:
            entry["ipv6"] = {"address": ips["ipv6"]}

        vlan_list.append(entry)

    return vlan_list

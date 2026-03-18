"""Monitoring service: build target payloads for the Collector agent."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.enums import ConnectionState, MemberState, TrunkState
from ixforge.models.connection import Connection
from ixforge.models.ip import IPAssignment, IPPool
from ixforge.models.member import Member
from ixforge.models.switch import Switch
from ixforge.models.trunk import Trunk, TrunkVLAN
from ixforge.schemas.monitoring import (
    MonitoringMemberIP,
    MonitoringPortTarget,
    MonitoringSwitchTarget,
    MonitoringTargets,
)
from ixforge.services.switches import decrypt_snmp


async def build_targets(
    session: AsyncSession,
    ixp_id: uuid.UUID,
) -> MonitoringTargets:
    """Build monitoring targets payload for the Collector.

    Returns active switches with decrypted SNMP communities,
    active ports, and IP addresses for active members.
    """
    # Active switches with decrypted SNMP communities
    switch_stmt = select(Switch).where(Switch.ixp_id == ixp_id, Switch.is_active.is_(True))
    switch_result = await session.execute(switch_stmt)
    switches_raw = list(switch_result.scalars().all())

    switch_targets: list[MonitoringSwitchTarget] = []
    switch_ids: list[uuid.UUID] = []
    for sw in switches_raw:
        snmp: str | None = None
        if sw.snmp_community_encrypted is not None:
            snmp = decrypt_snmp(sw.snmp_community_encrypted)
        switch_targets.append(
            MonitoringSwitchTarget(
                id=sw.id,
                name=sw.name,
                management_ip=sw.management_ip,
                snmp_community=snmp,
            )
        )
        switch_ids.append(sw.id)

    # Active connections on active switches (resolve member_id via trunk)
    port_targets: list[MonitoringPortTarget] = []
    if switch_ids:
        conn_stmt = (
            select(Connection, Trunk.member_id)
            .join(Trunk, Connection.trunk_id == Trunk.id)
            .where(
                Connection.switch_id.in_(switch_ids),
                Connection.state == ConnectionState.active,
            )
        )
        conn_result = await session.execute(conn_stmt)
        for conn, member_id in conn_result.all():
            port_targets.append(
                MonitoringPortTarget(
                    id=conn.id,
                    switch_id=conn.switch_id,
                    name=conn.name,
                    speed=conn.speed,
                    member_id=member_id,
                )
            )

    # IP addresses for active members (via trunk -> trunk_vlan -> ip_assignment)
    member_ip_stmt = (
        select(
            Member.id.label("member_id"),
            Member.name.label("member_name"),
            IPAssignment.address,
            IPPool.af,
        )
        .join(Trunk, Trunk.member_id == Member.id)
        .join(TrunkVLAN, TrunkVLAN.trunk_id == Trunk.id)
        .join(IPAssignment, IPAssignment.trunk_vlan_id == TrunkVLAN.id)
        .join(IPPool, IPPool.id == IPAssignment.pool_id)
        .where(
            Member.ixp_id == ixp_id,
            Member.state == MemberState.active,
            Trunk.state == TrunkState.active,
        )
    )
    member_ip_result = await session.execute(member_ip_stmt)
    member_ips = [
        MonitoringMemberIP(
            member_id=row.member_id,
            member_name=row.member_name,
            address=row.address,
            af=row.af,
        )
        for row in member_ip_result.all()
    ]

    return MonitoringTargets(
        switches=switch_targets,
        ports=port_targets,
        member_ips=member_ips,
    )

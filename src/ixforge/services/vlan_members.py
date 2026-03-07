"""VLANMember service: manage member associations for private VLANs."""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.enums import VLANType
from ixforge.exceptions import ConflictError, NotFoundError, ValidationError
from ixforge.models.member import Member
from ixforge.models.vlan import VLAN
from ixforge.models.vlan_member import VLANMember
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.schemas.vlan_member import VLANMemberRead
from ixforge.services.base import paginate


async def list_members(
    session: AsyncSession, ixp_id: uuid.UUID, vlan_id: uuid.UUID, params: CursorParams
) -> CursorPage[VLANMemberRead]:
    stmt = select(VLANMember).where(VLANMember.vlan_id == vlan_id, VLANMember.ixp_id == ixp_id)
    return await paginate(session, stmt, params, VLANMember.created_at, VLANMember.id, VLANMemberRead)


async def add_member(
    session: AsyncSession, ixp_id: uuid.UUID, vlan_id: uuid.UUID, member_id: uuid.UUID
) -> VLANMember:
    vlan = await session.get(VLAN, vlan_id)
    if vlan is None or vlan.ixp_id != ixp_id:
        raise NotFoundError("VLAN", str(vlan_id))
    if vlan.type != VLANType.private:
        raise ValidationError("Only private VLANs can have member associations")

    member = await session.get(Member, member_id)
    if member is None or member.ixp_id != ixp_id:
        raise NotFoundError("Member", str(member_id))

    vm = VLANMember(ixp_id=ixp_id, vlan_id=vlan_id, member_id=member_id)
    session.add(vm)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError("Member already associated with this VLAN") from exc
    return vm


async def remove_member(
    session: AsyncSession, ixp_id: uuid.UUID, vlan_id: uuid.UUID, member_id: uuid.UUID
) -> None:
    vm = await session.scalar(
        select(VLANMember).where(
            VLANMember.ixp_id == ixp_id,
            VLANMember.vlan_id == vlan_id,
            VLANMember.member_id == member_id,
        )
    )
    if vm is None:
        raise NotFoundError("VLANMember", f"vlan={vlan_id} member={member_id}")
    await session.delete(vm)
    await session.flush()

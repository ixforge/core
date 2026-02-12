"""Switch service: CRUD with Fernet encryption for SNMP community."""

import base64
import hashlib
import uuid

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.config import get_settings
from ixforge.exceptions import NotFoundError, ValidationError
from ixforge.models.switch import Switch
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.schemas.switch import SwitchCreate, SwitchRead, SwitchUpdate
from ixforge.services.base import paginate


def _get_fernet() -> Fernet:
    """Derive a Fernet key from the application secret_key."""
    secret = get_settings().secret_key.encode()
    key_bytes = hashlib.sha256(secret).digest()
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    return Fernet(fernet_key)


def encrypt_snmp(plaintext: str) -> str:
    """Encrypt an SNMP community string."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_snmp(ciphertext: str) -> str:
    """Decrypt an SNMP community string."""
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise ValidationError("Failed to decrypt SNMP community") from exc


async def create(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    data: SwitchCreate,
) -> Switch:
    """Create a switch, encrypting the SNMP community if provided."""
    encrypted_community: str | None = None
    if data.snmp_community is not None:
        encrypted_community = encrypt_snmp(data.snmp_community)

    switch = Switch(
        ixp_id=ixp_id,
        name=data.name,
        hostname=data.hostname,
        vendor=data.vendor,
        model=data.model,
        management_ip=data.management_ip,
        snmp_community_encrypted=encrypted_community,
        is_active=data.is_active,
        extra_data=data.extra_data,
    )
    session.add(switch)
    await session.flush()
    return switch


async def get(session: AsyncSession, switch_id: uuid.UUID) -> Switch:
    """Get a switch by id or raise NotFoundError."""
    switch = await session.get(Switch, switch_id)
    if switch is None:
        raise NotFoundError("Switch", str(switch_id))
    return switch


async def list_switches(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    params: CursorParams,
) -> CursorPage[SwitchRead]:
    """List switches for an IXP with cursor-based pagination."""
    stmt = select(Switch).where(Switch.ixp_id == ixp_id)
    return await paginate(
        session,
        stmt,
        params,
        sort_column=Switch.created_at,
        id_column=Switch.id,
        schema=SwitchRead,
    )


async def update(
    session: AsyncSession,
    switch_id: uuid.UUID,
    data: SwitchUpdate,
) -> Switch:
    """Update a switch. Handles SNMP community encryption on change."""
    switch = await get(session, switch_id)
    update_fields = data.model_dump(exclude_unset=True)

    snmp_community = update_fields.pop("snmp_community", None)
    if snmp_community is not None:
        switch.snmp_community_encrypted = encrypt_snmp(snmp_community)

    for field, value in update_fields.items():
        setattr(switch, field, value)

    await session.flush()
    return switch


async def delete(session: AsyncSession, switch_id: uuid.UUID) -> None:
    """Delete a switch."""
    switch = await get(session, switch_id)
    await session.delete(switch)
    await session.flush()

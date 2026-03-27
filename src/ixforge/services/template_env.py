"""Shared Jinja2 template environment builder."""

import uuid

from jinja2 import DictLoader
from jinja2.sandbox import SandboxedEnvironment
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.services.rs_templates import get_all_templates
from ixforge.services.template_filters import bird_str, ipaddr, prefixlist


async def build_template_env(
    session: AsyncSession, ixp_id: uuid.UUID,
) -> SandboxedEnvironment:
    """Build a SandboxedEnvironment with templates loaded from DB"""
    templates = await get_all_templates(session, ixp_id)
    env = SandboxedEnvironment(
        loader=DictLoader(templates),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters["ipaddr"] = ipaddr
    env.filters["bird_str"] = bird_str
    env.filters["prefixlist"] = prefixlist
    return env

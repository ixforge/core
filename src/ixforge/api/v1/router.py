"""v1 router aggregator."""

from fastapi import APIRouter

from ixforge.api.v1.agent import agent_router
from ixforge.api.v1.auth import auth_router
from ixforge.api.v1.bgp_sessions import bgp_sessions_router
from ixforge.api.v1.config import config_router
from ixforge.api.v1.connections import connections_router
from ixforge.api.v1.contacts import contacts_router
from ixforge.api.v1.custom_fields import custom_fields_router
from ixforge.api.v1.events import events_router
from ixforge.api.v1.health import health_router
from ixforge.api.v1.ip_pools import ip_pools_router
from ixforge.api.v1.ixf_export import ixf_router
from ixforge.api.v1.members import members_router
from ixforge.api.v1.monitoring import monitoring_router
from ixforge.api.v1.ports import ports_router
from ixforge.api.v1.route_servers import route_servers_router
from ixforge.api.v1.switches import switches_router
from ixforge.api.v1.users import users_router
from ixforge.api.v1.vlans import vlans_router

v1_router = APIRouter()
v1_router.include_router(agent_router)
v1_router.include_router(health_router)
v1_router.include_router(auth_router)
v1_router.include_router(users_router)
v1_router.include_router(config_router)
v1_router.include_router(ixf_router)
v1_router.include_router(members_router)
v1_router.include_router(contacts_router)
v1_router.include_router(switches_router)
v1_router.include_router(ports_router)
v1_router.include_router(vlans_router)
v1_router.include_router(ip_pools_router)
v1_router.include_router(connections_router)
v1_router.include_router(route_servers_router)
v1_router.include_router(bgp_sessions_router)
v1_router.include_router(events_router)
v1_router.include_router(custom_fields_router)
v1_router.include_router(monitoring_router)

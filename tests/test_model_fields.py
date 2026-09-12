"""Tests for new model fields."""


def test_member_has_new_fields():
    from ixforge.models.member import Member

    cols = {c.name for c in Member.__table__.columns}
    for field in (
        "member_type",
        "description",
        "city",
        "country",
        "connection_date",
        "contract_type",
        "notes",
        "skip_ixf_export",
    ):
        assert field in cols, f"Missing field: {field}"


def test_user_has_new_fields():
    from ixforge.models.user import User

    cols = {c.name for c in User.__table__.columns}
    for field in ("phone", "position", "pgp_key"):
        assert field in cols, f"Missing field: {field}"


def test_switch_has_location_id():
    from ixforge.models.switch import Switch

    cols = {c.name for c in Switch.__table__.columns}
    assert "location_id" in cols


async def test_member_prefix_filter_roundtrip(db_session, ixp):
    from ixforge.enums import MemberState, PeeringPolicy, PrefixFilterSource
    from ixforge.models.member import Member
    from ixforge.models.member_prefix_filter import MemberPrefixFilter

    member = Member(
        ixp_id=ixp.id,
        name="Apoapsis",
        short_name="APO",
        asn=273973,
        state=MemberState.active,
        peering_policy=PeeringPolicy.open,
    )
    db_session.add(member)
    await db_session.flush()

    pf = MemberPrefixFilter(
        ixp_id=ixp.id,
        member_id=member.id,
        af=4,
        origin_asns=[273973, 64512],
        prefixes=["45.170.100.0/24", "45.238.179.0/24"],
        as_set="AS-APOAPSIS",
        source=PrefixFilterSource.manual,
    )
    db_session.add(pf)
    await db_session.flush()

    assert pf.origin_asns == [273973, 64512]
    assert pf.prefixes == ["45.170.100.0/24", "45.238.179.0/24"]
    assert pf.source is PrefixFilterSource.manual


async def test_member_prefix_filter_nullable_lists(db_session, ixp):
    """origin_asns y prefixes en NULL son el caso normal, no un error"""
    from ixforge.enums import MemberState, PeeringPolicy
    from ixforge.models.member import Member
    from ixforge.models.member_prefix_filter import MemberPrefixFilter

    member = Member(
        ixp_id=ixp.id, name="LACTLD", short_name="LACTLD", asn=61455,
        state=MemberState.active, peering_policy=PeeringPolicy.open,
    )
    db_session.add(member)
    await db_session.flush()

    pf = MemberPrefixFilter(ixp_id=ixp.id, member_id=member.id, af=6)
    db_session.add(pf)
    await db_session.flush()

    assert pf.origin_asns is None
    assert pf.prefixes is None


async def test_route_server_peer_roundtrip(db_session, ixp):
    from ixforge.enums import BGPAdminState, RouteServerPeerType
    from ixforge.models.route_server import RouteServer
    from ixforge.models.route_server_peer import RouteServerPeer

    rs = RouteServer(ixp_id=ixp.id, name="rs1", ip_v4="192.0.2.1", is_active=True)
    db_session.add(rs)
    await db_session.flush()

    peer = RouteServerPeer(
        ixp_id=ixp.id,
        route_server_id=rs.id,
        name="PIT Chile upstream",
        peer_ip="192.0.2.5",
        peer_asn=64166,
        local_asn=64166,
        passive=True,
        peer_type=RouteServerPeerType.upstream,
        mark_community="64166:9999",
    )
    db_session.add(peer)
    await db_session.flush()

    assert peer.peer_type is RouteServerPeerType.upstream
    assert peer.admin_state is BGPAdminState.up


async def test_route_server_peer_has_no_af_column(db_session, ixp):
    """El af se deriva de peer_ip: guardarlo seria una segunda fuente de verdad"""
    from ixforge.models.route_server_peer import RouteServerPeer

    assert "af" not in {c.name for c in RouteServerPeer.__table__.columns}


async def test_rpki_server_defaults(db_session, ixp):
    from ixforge.enums import RPKITransport
    from ixforge.models.rpki_server import RPKIServer

    srv = RPKIServer(ixp_id=ixp.id, name="routinator", host="10.20.30.65")
    db_session.add(srv)
    await db_session.flush()

    assert srv.port == 3323
    assert srv.transport is RPKITransport.tcp
    assert srv.route_server_id is None


async def test_route_server_new_defaults(db_session, ixp):
    from ixforge.models.route_server import RouteServer

    rs = RouteServer(ixp_id=ixp.id, name="rs1", ip_v4="192.0.2.1", is_active=True)
    db_session.add(rs)
    await db_session.flush()

    assert rs.passive_sessions is True
    assert rs.rpki_enabled is False

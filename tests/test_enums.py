from ixforge.enums import ContractType, MemberType, VLANType


def test_member_type_values():
    assert set(MemberType) == {
        "isp", "cdn", "ixp", "academico", "gobierno",
        "corporativo", "infraestructura_critica", "otro",
    }


def test_contract_type_values():
    assert set(ContractType) == {"free", "standard"}


def test_vlan_type_has_private():
    assert VLANType.private == "private"


def test_route_server_peer_type_values():
    from ixforge.enums import RouteServerPeerType

    assert {e.value for e in RouteServerPeerType} == {"upstream", "collector", "special"}


def test_rpki_policy_values():
    from ixforge.enums import RPKIPolicy

    assert {e.value for e in RPKIPolicy} == {"info_only", "reject_invalid"}


def test_prefix_filter_source_values():
    from ixforge.enums import PrefixFilterSource

    assert {e.value for e in PrefixFilterSource} == {"manual", "irr"}


def test_rpki_transport_values():
    from ixforge.enums import RPKITransport

    assert {e.value for e in RPKITransport} == {"tcp", "ssh"}

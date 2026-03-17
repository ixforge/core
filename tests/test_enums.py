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

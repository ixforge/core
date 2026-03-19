"""Tests for new and updated schemas."""


def test_location_schema():
    from ixforge.schemas.location import LocationCreate

    loc = LocationCreate(name="DC1", city="Santiago", country="CL")
    assert loc.name == "DC1"


def test_member_read_has_logo_url():
    from ixforge.schemas.member import MemberRead

    fields = MemberRead.model_fields
    assert "logo_url" in fields
    assert "member_type" in fields
    assert "skip_ixf_export" in fields


def test_ixp_update_schema():
    from ixforge.schemas.ixp import IXPUpdate

    upd = IXPUpdate(name="New Name")
    assert upd.name == "New Name"


def test_rs_ip_schemas():
    from ixforge.schemas.rs_ip import RSIPAssignmentCreate

    assert RSIPAssignmentCreate.model_fields


def test_vlan_member_schema():
    from ixforge.schemas.vlan_member import VLANMemberCreate

    assert VLANMemberCreate.model_fields


def test_route_server_vlan_schema():
    from ixforge.schemas.route_server_vlan import RouteServerVLANCreate

    assert RouteServerVLANCreate.model_fields


def test_switch_read_has_location_id():
    from ixforge.schemas.switch import SwitchRead

    assert "location_id" in SwitchRead.model_fields

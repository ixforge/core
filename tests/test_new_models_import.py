def test_location_model_importable():
    from ixforge.models.location import Location
    assert Location.__tablename__ == "locations"

def test_route_server_vlan_importable():
    from ixforge.models.route_server_vlan import RouteServerVLAN
    assert RouteServerVLAN.__tablename__ == "route_server_vlans"

def test_rs_ip_assignment_importable():
    from ixforge.models.rs_ip_assignment import RSIPAssignment
    assert RSIPAssignment.__tablename__ == "rs_ip_assignments"

def test_vlan_member_importable():
    from ixforge.models.vlan_member import VLANMember
    assert VLANMember.__tablename__ == "vlan_members"

def test_asn_cache_importable():
    from ixforge.models.asn_cache import ASNCache
    assert ASNCache.__tablename__ == "asn_cache"

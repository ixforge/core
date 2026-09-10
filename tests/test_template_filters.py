"""Tests for Jinja2 template filters."""

from ixforge.services.template_filters import bird_str, ipaddr, prefixlist


class TestIpaddrFilter:
    def test_passthrough(self):
        assert ipaddr("192.0.2.1") == "192.0.2.1"

    def test_network(self):
        assert ipaddr("192.0.2.0/24", "network") == "192.0.2.0"

    def test_prefixlen(self):
        assert ipaddr("192.0.2.0/24", "prefixlen") == "24"

    def test_netmask(self):
        assert ipaddr("192.0.2.0/24", "netmask") == "255.255.255.0"


class TestBirdStrFilter:
    def test_safe_string(self):
        assert bird_str("hello-world") == "hello-world"

    def test_removes_special_chars(self):
        assert bird_str("test@#$%") == "test"

    def test_truncates_at_255(self):
        assert len(bird_str("a" * 300)) == 255


class TestPrefixlistFilter:
    def test_empty(self):
        assert prefixlist([]) == "define pfxlist = [];"

    def test_single(self):
        result = prefixlist(["192.0.2.0/24"])
        assert "192.0.2.0/24" in result

    def test_custom_name(self):
        result = prefixlist(["10.0.0.0/8"], name="bogons")
        assert "define bogons" in result


def test_bird_community_splits_pair():
    from ixforge.services.template_filters import bird_community

    assert bird_community("64166:9999") == "64166, 9999"


def test_bird_community_rejects_garbage():
    import pytest

    from ixforge.services.template_filters import bird_community

    for bad in ("64166", "a:b", "64166:9999:1", "", "-1:5"):
        with pytest.raises(ValueError):
            bird_community(bad)


def test_bird_community_rejects_four_byte_asn():
    """Una community estandar son 16:16 bits, un ASN de 4 bytes no entra y BIRD
    rechaza el config entero con "value out of bounds in pair constructor"
    """
    import pytest

    from ixforge.services.template_filters import bird_community

    with pytest.raises(ValueError):
        bird_community("273973:9999")

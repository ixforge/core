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

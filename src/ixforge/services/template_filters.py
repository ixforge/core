"""Custom Jinja2 filters for BIRD config template rendering."""

import ipaddress
import re


def ipaddr(value: str, fmt: str = "") -> str:
    """Format an IP address string.

    Supported formats:
        ""       -> address as-is (e.g. "192.0.2.1")
        "network" -> network address from CIDR (e.g. "192.0.2.0" from "192.0.2.0/24")
        "prefixlen" -> prefix length (e.g. "24" from "192.0.2.0/24")
        "netmask" -> netmask for IPv4 (e.g. "255.255.255.0")
    """
    if fmt == "":
        return value

    network = ipaddress.ip_network(value, strict=False)
    if fmt == "network":
        return str(network.network_address)
    if fmt == "prefixlen":
        return str(network.prefixlen)
    if fmt == "netmask":
        return str(network.netmask)
    return value


def bird_str(value: str) -> str:
    """Sanitize a string for safe use in BIRD config"""
    return re.sub(r'[^\w \t\-.]', '', value)[:255]


def prefixlist(prefixes: list[str], name: str = "pfxlist") -> str:
    """Render a list of prefixes as a BIRD prefix list definition."""
    if not prefixes:
        return f"define {name} = [];"

    lines = [f"define {name} = ["]
    for i, prefix in enumerate(prefixes):
        separator = "," if i < len(prefixes) - 1 else ""
        lines.append(f"    {prefix}{separator}")
    lines.append("];")
    return "\n".join(lines)

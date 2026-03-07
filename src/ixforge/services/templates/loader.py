"""Jinja2 template environment for BIRD config generation."""

import ipaddress
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

_BIRD_TEMPLATE_DIR = Path(__file__).parent / "bird"


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


def get_template_env() -> Environment:
    """Create and return the Jinja2 environment for BIRD templates."""
    env = Environment(
        loader=FileSystemLoader(str(_BIRD_TEMPLATE_DIR)),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters["ipaddr"] = ipaddr
    env.filters["bird_str"] = bird_str
    env.filters["prefixlist"] = prefixlist
    return env


def get_template_snapshots() -> dict[str, str]:
    """Read all template files and return a dict of {filename: content} for traceability."""
    snapshots: dict[str, str] = {}
    for template_path in _BIRD_TEMPLATE_DIR.rglob("*.j2"):
        relative = template_path.relative_to(_BIRD_TEMPLATE_DIR)
        snapshots[str(relative)] = template_path.read_text()
    return snapshots

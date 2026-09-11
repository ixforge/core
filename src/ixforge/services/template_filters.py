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


def bird_community(value: str) -> str:
    """Convierte "64166:9999" en "64166, 9999" para usar dentro de parentesis

    Valida agresivamente porque el resultado se inyecta en un config que maneja
    infraestructura critica
    """
    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError(f"community invalida, se esperaba asn:value: {value!r}")
    try:
        asn, val = int(parts[0]), int(parts[1])
    except ValueError as exc:
        raise ValueError(f"community con partes no numericas: {value!r}") from exc
    # una community estandar es de 32 bits partidos en 16:16, asi que NINGUNO
    # de los dos componentes puede pasar de 65535. Permitir un ASN de 4 bytes
    # aca produce un config que BIRD rechaza con "Can't operate with value out
    # of bounds in pair constructor"
    if not (0 <= asn <= 65535) or not (0 <= val <= 65535):
        raise ValueError(
            f"community fuera de rango, cada componente admite hasta 65535: {value!r}"
        )
    return f"{asn}, {val}"


def rangos_a_borrar(conservados: tuple[tuple[int, int], ...]) -> str:
    """Set de communities (rsasn, *) a borrar en el export, salteando intervalos

    Se expresa como complemento y no como un delete seguido de un re-add
    condicional. Un re-add necesita saber que estaba presente DESPUES de haber
    borrado todo, que sin variables locales obliga a anidar una rama por
    combinacion. El complemento es una sola sentencia declarativa, crece lineal
    y no depende de sintaxis que varie entre menores de BIRD 2.x
    """
    if not conservados:
        return "( routeserverasn, * )"
    # normalizar: ordenar y fundir los que se tocan o solapan, o el complemento
    # deja tramos invertidos que BIRD rechaza
    fundidos: list[list[int]] = []
    for lo, hi in sorted(conservados):
        if fundidos and lo <= fundidos[-1][1] + 1:
            fundidos[-1][1] = max(fundidos[-1][1], hi)
        else:
            fundidos.append([lo, hi])

    tramos: list[str] = []
    inicio = 0
    for lo, hi in fundidos:
        if inicio <= lo - 1:
            tramos.append(f"( routeserverasn, {inicio}..{lo - 1} )")
        inicio = hi + 1
    if inicio <= 65535:
        tramos.append(f"( routeserverasn, {inicio}..65535 )")
    return ", ".join(tramos)


def intervalos_como_set(conservados: tuple[tuple[int, int], ...]) -> str:
    """Los intervalos publicos como set BIRD, para borrarlos al importar

    Es el mismo conjunto que el export conserva. Lo que el route server tiene
    derecho a poner es exactamente lo que no puede aceptar de un peer: si viene
    de afuera esta falsificado
    """
    partes = []
    for lo, hi in sorted(set(conservados)):
        partes.append(
            f"( routeserverasn, {lo} )" if lo == hi
            else f"( routeserverasn, {lo}..{hi} )"
        )
    return ", ".join(partes)

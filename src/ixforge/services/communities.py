"""Mapeo de conceptos del dominio a communities BGP informativas.

El esquema es el de PIT Chile, no el de euro-ix. Una community lleva el ASN
adelante, asi que 61522:65120 y 64166:65120 son distintas por construccion y
nunca hubo colision que evitar entre dos IXPs. Usar los mismos valores hace que
un miembro conectado a varios use un solo numero por concepto, y que un IXP
nuevo adopte el esquema tal cual en vez de inventar el suyo.

Los valores viven en el rango de ASN privados (64512-65534) y eso NO es casual:
en el control de anuncio, (routeserverasn, peer-as) significa "anunciar a este
peer". Si el tipo de miembro usara valores bajos como 220 o 250, esos numeros
son ASN de 16 bits reales y el route server no podria distinguir un caso del
otro. La colision es explotable y va en la direccion peligrosa: el route server
agrega la community de tipo en el import, y despues la funcion de control de
anuncio la lee como una excepcion "anunciar a este peer". Un miembro CDN que
pide "no anunciar a nadie" con (0, rsasn) termina con su ruta anunciada a
AS250, porque el propio route server la marco con (rsasn, 250).

En el rango privado no hay peers reales en un IXP, asi que los dos espacios de
nombres quedan separados por construccion.
"""

from ixforge.enums import MemberType, RouteServerPeerType

MEMBER_TYPE_COMMUNITIES: dict[MemberType, int | None] = {
    MemberType.ixp: 65110,
    MemberType.isp: 65120,
    MemberType.academico: 65130,
    MemberType.gobierno: 65140,
    MemberType.cdn: 65150,
    MemberType.corporativo: 65160,
    MemberType.infraestructura_critica: 65170,
    MemberType.otro: None,
}

# PIT no modela peers que no son miembros, asi que estas dos son extension
PEER_TYPE_COMMUNITIES: dict[RouteServerPeerType, int | None] = {
    RouteServerPeerType.upstream: 65180,
    RouteServerPeerType.collector: 65190,
    # special no dice nada en particular, igual que otro en los miembros
    RouteServerPeerType.special: None,
}

# Solo los dos estados que un miembro puede llegar a ver. Una ruta RPKI invalida
# se descarta, asi que no hay a quien informarle; y "no verificado" solo existiria
# con RPKI apagado, que es cuando tampoco se emite nada
RPKI_COMMUNITIES: dict[str, int] = {
    "valid": 65012,
    "unknown": 65023,
}

# Rango que el filtro de export NO borra y que el de import SI borra. Todo lo que
# clasifica el origen o el estado de una ruta vive aca y es publico a proposito:
# el miembro tiene que poder distinguir transito de peering, y una ruta validada
# de una que no, sin conocer numeros inventados por el operador
BLOQUE_PUBLICO = (65000, 65199)


def member_type_community(member_type: MemberType | None) -> int | None:
    """Devuelve el valor de la community informativa de tipo de miembro

    None significa que no se agrega ninguna community
    """
    if member_type is None:
        return None
    return MEMBER_TYPE_COMMUNITIES.get(member_type)


def peer_type_community(peer_type: RouteServerPeerType | None) -> int | None:
    """Community informativa de tipo para un peer que no es miembro

    Comparte el esquema con los miembros: el que recibe la ruta clasifica su
    origen mirando un solo bloque, sin importar si vino de un miembro o de un
    upstream
    """
    if peer_type is None:
        return None
    return PEER_TYPE_COMMUNITIES.get(peer_type)

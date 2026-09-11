"""Mapeo de conceptos del dominio a communities BGP informativas.

Los valores van en el rango 65xxx, que cae dentro de los ASN privados
(64512-65534), y eso NO es casual: en el esquema de control de anuncio,
(routeserverasn, peer-as) significa "anunciar a este peer". Si el tipo de
miembro usara valores bajos como 220 o 250, esos numeros son ASN de 16 bits
reales y el route server no podria distinguir un caso del otro.

La colision es explotable y va en la direccion peligrosa: el route server
agrega la community de tipo en el import, y despues la funcion de control de
anuncio la lee como una excepcion "anunciar a este peer". Un miembro CDN que
pide "no anunciar a nadie" con (0, rsasn) termina con su ruta anunciada a
AS250, porque el propio route server la marco con (rsasn, 250).

En el rango privado no hay peers reales en un IXP, asi que los dos espacios de
nombres quedan separados por construccion. Es ademas lo que la referencia
tecnica publica de PatagoniaIX ya documenta
"""

from ixforge.enums import MemberType

MEMBER_TYPE_COMMUNITIES: dict[MemberType, int | None] = {
    MemberType.ixp: 65210,
    MemberType.isp: 65220,
    MemberType.academico: 65230,
    MemberType.gobierno: 65240,
    MemberType.cdn: 65250,
    MemberType.corporativo: 65260,
    MemberType.infraestructura_critica: 65270,
    MemberType.otro: None,
}


def member_type_community(member_type: MemberType | None) -> int | None:
    """Devuelve el valor de la community informativa de tipo de miembro

    None significa que no se agrega ninguna community
    """
    if member_type is None:
        return None
    return MEMBER_TYPE_COMMUNITIES.get(member_type)

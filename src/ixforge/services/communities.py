"""Mapeo de conceptos del dominio a communities BGP del esquema euro-ix.

Los numeros son los del esquema euro-ix de tipo de miembro y no son
configurables: cambiarlos rompe la interoperabilidad con los looking glass y
con lo que los miembros ya tienen documentado
"""

from ixforge.enums import MemberType

MEMBER_TYPE_COMMUNITIES: dict[MemberType, int | None] = {
    MemberType.ixp: 210,
    MemberType.isp: 220,
    MemberType.academico: 230,
    MemberType.gobierno: 240,
    MemberType.cdn: 250,
    MemberType.corporativo: 260,
    MemberType.infraestructura_critica: 270,
    MemberType.otro: None,
}


def member_type_community(member_type: MemberType | None) -> int | None:
    """Devuelve el valor de la community informativa de tipo de miembro

    None significa que no se agrega ninguna community
    """
    if member_type is None:
        return None
    return MEMBER_TYPE_COMMUNITIES.get(member_type)

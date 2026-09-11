"""Tests del mapeo de tipo de miembro a community informativa euro-ix."""

import pytest

from ixforge.enums import MemberType
from ixforge.services.communities import member_type_community


@pytest.mark.parametrize(
    ("member_type", "expected"),
    [
        (MemberType.ixp, 65210),
        (MemberType.isp, 65220),
        (MemberType.academico, 65230),
        (MemberType.gobierno, 65240),
        (MemberType.cdn, 65250),
        (MemberType.corporativo, 65260),
        (MemberType.infraestructura_critica, 65270),
        (MemberType.otro, None),
        (None, None),
    ],
)
def test_member_type_community(member_type, expected):
    assert member_type_community(member_type) == expected


def test_every_member_type_is_mapped():
    """Un MemberType nuevo sin entrada en el mapeo tiene que romper este test"""
    from ixforge.services.communities import MEMBER_TYPE_COMMUNITIES

    assert set(MEMBER_TYPE_COMMUNITIES) == set(MemberType)


def test_los_valores_no_colisionan_con_asn_publicos():
    """El control de anuncio usa (rsasn, peer-as) para "anunciar a este peer".

    Si el tipo de miembro usara valores que son ASN publicos validos, el route
    server no podria distinguir los dos casos, y como el propio route server
    agrega la community de tipo en el import, terminaria leyendola como una
    excepcion de anuncio. Un miembro que pidio "no anunciar a nadie" veria su
    ruta anunciada al ASN que coincida con su tipo.

    El rango 64512-65534 es de ASN privados: ahi no hay peers en un IXP
    """
    from ixforge.services.communities import MEMBER_TYPE_COMMUNITIES

    for tipo, valor in MEMBER_TYPE_COMMUNITIES.items():
        if valor is None:
            continue
        assert 64512 <= valor <= 65534, (
            f"{tipo} usa {valor}, que es un ASN publico valido y colisiona con "
            "el espacio de control de anuncio (rsasn, peer-as)"
        )


def test_no_hay_valores_repetidos():
    """Dos tipos con el mismo valor los vuelve indistinguibles en el looking glass"""
    from ixforge.services.communities import MEMBER_TYPE_COMMUNITIES

    valores = [v for v in MEMBER_TYPE_COMMUNITIES.values() if v is not None]

    assert len(valores) == len(set(valores))

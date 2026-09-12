"""Tests del mapeo de tipo de miembro a community informativa euro-ix."""

import pytest

from ixforge.enums import MemberType
from ixforge.services.communities import member_type_community


@pytest.mark.parametrize(
    ("member_type", "expected"),
    [
        (MemberType.ixp, 65110),
        (MemberType.isp, 65120),
        (MemberType.academico, 65130),
        (MemberType.gobierno, 65140),
        (MemberType.cdn, 65150),
        (MemberType.corporativo, 65160),
        (MemberType.infraestructura_critica, 65170),
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


def test_tipo_de_peer_no_miembro_tiene_community():
    """Un upstream o un colector tambien se clasifican, con el mismo esquema"""
    from ixforge.enums import RouteServerPeerType
    from ixforge.services.communities import peer_type_community

    assert peer_type_community(RouteServerPeerType.upstream) == 65180
    assert peer_type_community(RouteServerPeerType.collector) == 65190
    # special no significa nada en particular, como otro en los miembros
    assert peer_type_community(RouteServerPeerType.special) is None
    assert peer_type_community(None) is None


def test_los_tipos_de_peer_no_chocan_con_los_de_miembro():
    from ixforge.services.communities import (
        MEMBER_TYPE_COMMUNITIES,
        PEER_TYPE_COMMUNITIES,
    )

    miembros = {v for v in MEMBER_TYPE_COMMUNITIES.values() if v is not None}
    peers = {v for v in PEER_TYPE_COMMUNITIES.values() if v is not None}
    assert not (miembros & peers)


def test_los_tipos_siguen_la_numeracion_de_pit_chile():
    """El esquema es el de PIT Chile, no el de euro-ix.

    Una community lleva el ASN adelante, asi que 61522:65120 y 64166:65120 son
    distintas por construccion y no habia colision que evitar. Usar los mismos
    valores hace que un miembro conectado a los dos IXPs use un solo numero por
    concepto, y que otro IXP pueda adoptar el esquema tal cual
    """
    from ixforge.enums import MemberType, RouteServerPeerType
    from ixforge.services.communities import (
        MEMBER_TYPE_COMMUNITIES,
        PEER_TYPE_COMMUNITIES,
    )

    # las siete de PIT, con los mismos valores
    assert MEMBER_TYPE_COMMUNITIES[MemberType.ixp] == 65110
    assert MEMBER_TYPE_COMMUNITIES[MemberType.isp] == 65120
    assert MEMBER_TYPE_COMMUNITIES[MemberType.academico] == 65130
    assert MEMBER_TYPE_COMMUNITIES[MemberType.gobierno] == 65140
    assert MEMBER_TYPE_COMMUNITIES[MemberType.cdn] == 65150
    assert MEMBER_TYPE_COMMUNITIES[MemberType.corporativo] == 65160
    assert MEMBER_TYPE_COMMUNITIES[MemberType.infraestructura_critica] == 65170
    # y dos extensiones, que PIT no tiene porque no modela peers no miembro
    assert PEER_TYPE_COMMUNITIES[RouteServerPeerType.upstream] == 65180
    assert PEER_TYPE_COMMUNITIES[RouteServerPeerType.collector] == 65190


def test_rpki_usa_communities_estandar_como_pit():
    """PIT publica el estado ROA en estandar, no en large"""
    from ixforge.services.communities import RPKI_COMMUNITIES

    assert RPKI_COMMUNITIES == {"valid": 65012, "unknown": 65023}


def test_el_bloque_publico_cubre_rpki_y_los_tipos():
    from ixforge.services.communities import (
        BLOQUE_PUBLICO,
        MEMBER_TYPE_COMMUNITIES,
        PEER_TYPE_COMMUNITIES,
        RPKI_COMMUNITIES,
    )

    lo, hi = BLOQUE_PUBLICO
    todos = [
        *[v for v in MEMBER_TYPE_COMMUNITIES.values() if v is not None],
        *[v for v in PEER_TYPE_COMMUNITIES.values() if v is not None],
        *RPKI_COMMUNITIES.values(),
    ]
    assert todos
    for v in todos:
        assert lo <= v <= hi, v
    # sigue dentro de los ASN privados, que es lo que lo separa del control de
    # anuncio (rsasn, peer-as): ahi no hay peers reales
    assert lo >= 64512
    assert hi <= 65534

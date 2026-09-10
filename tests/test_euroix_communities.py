"""Tests del mapeo de tipo de miembro a community informativa euro-ix."""

import pytest

from ixforge.enums import MemberType
from ixforge.services.communities import member_type_community


@pytest.mark.parametrize(
    ("member_type", "expected"),
    [
        (MemberType.ixp, 210),
        (MemberType.isp, 220),
        (MemberType.academico, 230),
        (MemberType.gobierno, 240),
        (MemberType.cdn, 250),
        (MemberType.corporativo, 260),
        (MemberType.infraestructura_critica, 270),
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

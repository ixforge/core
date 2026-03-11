"""Tests for new model fields."""


def test_member_has_new_fields():
    from ixforge.models.member import Member

    cols = {c.name for c in Member.__table__.columns}
    for field in (
        "member_type",
        "description",
        "city",
        "country",
        "connection_date",
        "contract_type",
        "notes",
        "skip_ixf_export",
    ):
        assert field in cols, f"Missing field: {field}"


def test_user_has_new_fields():
    from ixforge.models.user import User

    cols = {c.name for c in User.__table__.columns}
    for field in ("phone", "position", "pgp_key"):
        assert field in cols, f"Missing field: {field}"


def test_switch_has_location_id():
    from ixforge.models.switch import Switch

    cols = {c.name for c in Switch.__table__.columns}
    assert "location_id" in cols

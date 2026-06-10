"""Tests for RouteServerTemplate model and schemas."""

import pytest
from httpx import AsyncClient
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.exceptions import ConflictError, NotFoundError
from ixforge.models.ixp import IXP
from ixforge.models.rs_template import RouteServerTemplate
from ixforge.schemas.rs_template import RSTemplateCreate, RSTemplateUpdate
from ixforge.services import rs_templates as tpl_svc


def test_route_server_template_has_expected_columns():
    cols = {c.name for c in RouteServerTemplate.__table__.columns}
    expected = {
        "id",
        "ixp_id",
        "created_at",
        "updated_at",
        "filename",
        "content",
        "description",
        "is_protected",
        "updated_by_id",
    }
    assert expected == cols


def test_route_server_template_tablename():
    assert RouteServerTemplate.__tablename__ == "route_server_templates"


def test_route_server_template_unique_constraint():
    constraints = {
        c.name for c in RouteServerTemplate.__table__.constraints if hasattr(c, "name") and c.name
    }
    assert "uq_rs_templates_ixp_filename" in constraints


def test_filename_max_length():
    col = RouteServerTemplate.__table__.c.filename
    assert col.type.length == 255


def test_description_max_length():
    col = RouteServerTemplate.__table__.c.description
    assert col.type.length == 500


def test_content_is_text_type():
    from sqlalchemy import Text

    col = RouteServerTemplate.__table__.c.content
    assert isinstance(col.type, Text)


def test_is_protected_default_false():
    col = RouteServerTemplate.__table__.c.is_protected
    assert col.default.arg is False


def test_updated_by_id_nullable():
    col = RouteServerTemplate.__table__.c.updated_by_id
    assert col.nullable is True


def test_ixp_id_not_nullable():
    col = RouteServerTemplate.__table__.c.ixp_id
    assert col.nullable is False


def test_ixp_id_foreign_key():
    col = RouteServerTemplate.__table__.c.ixp_id
    fk = next(iter(col.foreign_keys))
    assert fk.target_fullname == "ixps.id"


def test_updated_by_id_foreign_key():
    col = RouteServerTemplate.__table__.c.updated_by_id
    fk = next(iter(col.foreign_keys))
    assert fk.target_fullname == "users.id"


@pytest.mark.anyio
async def test_create_route_server_template(db_session, ixp):
    template = RouteServerTemplate(
        ixp_id=ixp.id,
        filename="test.j2",
        content="# test template",
        description="Test template",
        is_protected=False,
    )
    db_session.add(template)
    await db_session.flush()

    result = await db_session.execute(
        select(RouteServerTemplate).where(RouteServerTemplate.id == template.id)
    )
    saved = result.scalar_one()
    assert saved.filename == "test.j2"
    assert saved.content == "# test template"
    assert saved.is_protected is False
    assert saved.ixp_id == ixp.id


@pytest.mark.anyio
async def test_unique_filename_per_ixp(db_session, ixp):
    t1 = RouteServerTemplate(
        ixp_id=ixp.id,
        filename="duplicate.j2",
        content="content 1",
    )
    db_session.add(t1)
    await db_session.flush()

    t2 = RouteServerTemplate(
        ixp_id=ixp.id,
        filename="duplicate.j2",
        content="content 2",
    )
    db_session.add(t2)
    with pytest.raises(IntegrityError):
        await db_session.flush()


class TestRSTemplateSchemas:
    def test_create_valid(self):
        from ixforge.schemas.rs_template import RSTemplateCreate

        data = RSTemplateCreate(filename="filters/custom.j2", content="{% block main %}{% endblock %}", description="Custom filter")
        assert data.filename == "filters/custom.j2"

    def test_create_filename_must_end_j2(self):
        from ixforge.schemas.rs_template import RSTemplateCreate

        with pytest.raises(PydanticValidationError):
            RSTemplateCreate(filename="bad.txt", content="x")

    def test_create_filename_rejects_path_traversal(self):
        from ixforge.schemas.rs_template import RSTemplateCreate

        with pytest.raises(PydanticValidationError):
            RSTemplateCreate(filename="../etc/passwd.j2", content="x")

    def test_create_filename_rejects_double_slash(self):
        from ixforge.schemas.rs_template import RSTemplateCreate

        with pytest.raises(PydanticValidationError):
            RSTemplateCreate(filename="a//b.j2", content="x")

    def test_create_filename_rejects_leading_slash(self):
        from ixforge.schemas.rs_template import RSTemplateCreate

        with pytest.raises(PydanticValidationError):
            RSTemplateCreate(filename="/root.j2", content="x")

    def test_create_filename_max_depth_one(self):
        from ixforge.schemas.rs_template import RSTemplateCreate

        with pytest.raises(PydanticValidationError):
            RSTemplateCreate(filename="a/b/c.j2", content="x")

    def test_create_content_max_length(self):
        from ixforge.schemas.rs_template import RSTemplateCreate

        with pytest.raises(PydanticValidationError):
            RSTemplateCreate(filename="big.j2", content="x" * 524289)

    def test_update_none_means_no_change(self):
        from ixforge.schemas.rs_template import RSTemplateUpdate

        data = RSTemplateUpdate()
        assert data.model_dump(exclude_unset=True) == {}

    def test_update_partial(self):
        from ixforge.schemas.rs_template import RSTemplateUpdate

        data = RSTemplateUpdate(description="new desc")
        assert data.model_dump(exclude_unset=True) == {"description": "new desc"}


# ---------------------------------------------------------------------------
# Service tests
# ---------------------------------------------------------------------------

async def _seed_template(db, ixp, filename="test.j2", **kw):
    defaults = {"ixp_id": ixp.id, "filename": filename, "content": "hello {{ name }}"}
    defaults.update(kw)
    tpl = RouteServerTemplate(**defaults)
    db.add(tpl)
    await db.flush()
    return tpl


class TestRSTemplateService:
    @pytest.mark.anyio
    async def test_create_template(self, db_session, ixp):
        data = RSTemplateCreate(filename="new.j2", content="{% block x %}{% endblock %}")
        tpl = await tpl_svc.create(db_session, ixp.id, data)
        assert tpl.filename == "new.j2"
        assert tpl.content == "{% block x %}{% endblock %}"
        assert tpl.ixp_id == ixp.id

    @pytest.mark.anyio
    async def test_create_duplicate_filename_raises(self, db_session, ixp):
        data = RSTemplateCreate(filename="dup.j2", content="a")
        await tpl_svc.create(db_session, ixp.id, data)
        with pytest.raises(ConflictError):
            await tpl_svc.create(db_session, ixp.id, data)

    @pytest.mark.anyio
    async def test_list_templates_ordered_by_filename(self, db_session, ixp):
        await _seed_template(db_session, ixp, filename="zebra.j2")
        await _seed_template(db_session, ixp, filename="alpha.j2")
        result = await tpl_svc.list_templates(db_session, ixp.id)
        filenames = [t.filename for t in result]
        assert filenames == ["alpha.j2", "zebra.j2"]

    @pytest.mark.anyio
    async def test_get_template(self, db_session, ixp):
        tpl = await _seed_template(db_session, ixp)
        fetched = await tpl_svc.get(db_session, ixp.id, tpl.id)
        assert fetched.id == tpl.id

    @pytest.mark.anyio
    async def test_get_nonexistent_raises(self, db_session, ixp):
        import uuid

        with pytest.raises(NotFoundError):
            await tpl_svc.get(db_session, ixp.id, uuid.uuid4())

    @pytest.mark.anyio
    async def test_update_template(self, db_session, ixp):
        tpl = await _seed_template(db_session, ixp)
        data = RSTemplateUpdate(content="updated content")
        updated = await tpl_svc.update(db_session, ixp.id, tpl.id, data)
        assert updated.content == "updated content"

    @pytest.mark.anyio
    async def test_update_tracks_user_id(self, db_session, ixp, admin_user):
        tpl = await _seed_template(db_session, ixp)
        data = RSTemplateUpdate(description="edited")
        updated = await tpl_svc.update(db_session, ixp.id, tpl.id, data, user_id=admin_user.id)
        assert updated.updated_by_id == admin_user.id

    @pytest.mark.anyio
    async def test_delete_template(self, db_session, ixp):
        tpl = await _seed_template(db_session, ixp)
        await tpl_svc.delete(db_session, ixp.id, tpl.id)
        with pytest.raises(NotFoundError):
            await tpl_svc.get(db_session, ixp.id, tpl.id)

    @pytest.mark.anyio
    async def test_delete_protected_raises(self, db_session, ixp):
        tpl = await _seed_template(db_session, ixp, is_protected=True)
        with pytest.raises(ConflictError, match="protected"):
            await tpl_svc.delete(db_session, ixp.id, tpl.id)

    @pytest.mark.anyio
    async def test_delete_referenced_raises(self, db_session, ixp):
        await _seed_template(db_session, ixp, filename="base.j2", content="base")
        await _seed_template(
            db_session, ixp, filename="child.j2",
            content='{% include "base.j2" %}',
        )
        base = (await tpl_svc.list_templates(db_session, ixp.id))[0]
        with pytest.raises(ConflictError, match="referenced"):
            await tpl_svc.delete(db_session, ixp.id, base.id)

    @pytest.mark.anyio
    async def test_delete_from_import_detected(self, db_session, ixp):
        await _seed_template(db_session, ixp, filename="macros.j2", content="{% macro foo() %}{% endmacro %}")
        await _seed_template(
            db_session, ixp, filename="user.j2",
            content='{% from "macros.j2" import foo %}',
        )
        macros = (await tpl_svc.list_templates(db_session, ixp.id))[0]
        with pytest.raises(ConflictError, match="referenced"):
            await tpl_svc.delete(db_session, ixp.id, macros.id)

    def test_validate_syntax_valid(self):
        result = tpl_svc.validate_syntax("{% for x in items %}{{ x }}{% endfor %}")
        assert result.valid is True
        assert result.errors == []

    def test_validate_syntax_invalid(self):
        result = tpl_svc.validate_syntax("{% for x in %}")
        assert result.valid is False
        assert len(result.errors) == 1

    @pytest.mark.anyio
    async def test_get_all_templates_dict(self, db_session, ixp):
        await _seed_template(db_session, ixp, filename="a.j2", content="aaa")
        await _seed_template(db_session, ixp, filename="b.j2", content="bbb")
        result = await tpl_svc.get_all_templates(db_session, ixp.id)
        assert result == {"a.j2": "aaa", "b.j2": "bbb"}


class TestRSTemplateSecurity:
    def test_sandbox_blocks_class_access(self):
        """SandboxedEnvironment must block __class__ access"""
        result = tpl_svc.validate_syntax("{{ ''.__class__.__mro__ }}")
        assert result.valid is True  # parse succeeds, rendering would fail

        from jinja2 import DictLoader
        from jinja2.sandbox import SandboxedEnvironment, SecurityError

        env = SandboxedEnvironment(loader=DictLoader({"t.j2": "{{ ''.__class__.__mro__ }}"}))
        t = env.get_template("t.j2")
        with pytest.raises(SecurityError):
            t.render()

    def test_sandbox_blocks_import(self):
        from jinja2 import DictLoader, UndefinedError
        from jinja2.sandbox import SandboxedEnvironment, SecurityError

        env = SandboxedEnvironment(loader=DictLoader({"t.j2": "{{ __import__('os').system('ls') }}"}))
        t = env.get_template("t.j2")
        with pytest.raises((SecurityError, UndefinedError)):
            t.render()

    def test_content_max_length_enforced(self):
        with pytest.raises(PydanticValidationError):
            RSTemplateCreate(filename="huge.j2", content="x" * 524289)


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

async def _api_seed_template(
    client: AsyncClient, auth_headers: dict, **overrides: object,
) -> dict:
    payload = {
        "filename": "api-test.j2",
        "content": "hello {{ name }}",
        "description": "API test template",
    }
    payload.update(overrides)
    resp = await client.post("/api/v1/rs-templates", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    return resp.json()


class TestRSTemplateAPI:
    async def test_list_templates(
        self, client: AsyncClient, ixp: IXP, auth_headers: dict,
    ) -> None:
        resp = await client.get("/api/v1/rs-templates", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_create_template(
        self, client: AsyncClient, ixp: IXP, auth_headers: dict,
    ) -> None:
        data = await _api_seed_template(client, auth_headers, filename="create.j2")
        assert data["filename"] == "create.j2"
        assert data["content"] == "hello {{ name }}"
        assert data["is_protected"] is False

    async def test_get_template(
        self, client: AsyncClient, ixp: IXP, auth_headers: dict,
    ) -> None:
        created = await _api_seed_template(client, auth_headers, filename="get-test.j2")
        resp = await client.get(
            f"/api/v1/rs-templates/{created['id']}", headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["filename"] == "get-test.j2"

    async def test_update_template(
        self, client: AsyncClient, ixp: IXP, auth_headers: dict,
    ) -> None:
        created = await _api_seed_template(client, auth_headers, filename="patch-test.j2")
        resp = await client.patch(
            f"/api/v1/rs-templates/{created['id']}",
            json={"content": "updated content", "description": "patched"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["content"] == "updated content"
        assert body["description"] == "patched"
        assert body["updated_by_id"] is not None

    async def test_delete_template(
        self, client: AsyncClient, ixp: IXP, auth_headers: dict,
    ) -> None:
        created = await _api_seed_template(client, auth_headers, filename="del-test.j2")
        resp = await client.delete(
            f"/api/v1/rs-templates/{created['id']}", headers=auth_headers,
        )
        assert resp.status_code == 204

    async def test_delete_protected_fails(
        self, client: AsyncClient, ixp: IXP, auth_headers: dict,
        db_session: AsyncSession,
    ) -> None:
        tpl = RouteServerTemplate(
            ixp_id=ixp.id, filename="protected.j2", content="x", is_protected=True,
        )
        db_session.add(tpl)
        await db_session.flush()
        resp = await client.delete(
            f"/api/v1/rs-templates/{tpl.id}", headers=auth_headers,
        )
        assert resp.status_code == 409

    async def test_validate_syntax_valid(
        self, client: AsyncClient, auth_headers: dict,
    ) -> None:
        resp = await client.post(
            "/api/v1/rs-templates/validate",
            json={"content": "{% for x in items %}{{ x }}{% endfor %}"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is True
        assert body["errors"] == []

    async def test_validate_syntax_invalid(
        self, client: AsyncClient, auth_headers: dict,
    ) -> None:
        resp = await client.post(
            "/api/v1/rs-templates/validate",
            json={"content": "{% for x in %}"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is False
        assert len(body["errors"]) >= 1

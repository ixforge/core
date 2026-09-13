"""Tests for member logo upload/delete."""

import io
import os
import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.enums import MemberState
from ixforge.models.api_key import APIKey
from ixforge.models.ixp import IXP
from ixforge.models.member import Member
from ixforge.services.auth import hash_api_key


def _make_png_bytes() -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    img = Image.new("RGB", (100, 100), color=(255, 0, 0))
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_jpeg_bytes() -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    img = Image.new("RGB", (100, 100), color=(0, 255, 0))
    img.save(buf, format="JPEG")
    return buf.getvalue()


class TestMemberLogoAPI:
    async def test_upload_png_logo(
        self, client: AsyncClient, ixp: IXP, auth_headers: dict,
        db_session: AsyncSession, tmp_path, monkeypatch
    ) -> None:
        from ixforge.config import get_settings
        monkeypatch.setattr(get_settings(), "media_root", str(tmp_path))
        m = Member(ixp_id=ixp.id, name="ISP", short_name="I", asn=65010, state=MemberState.prospect)
        db_session.add(m)
        await db_session.flush()
        resp = await client.post(
            f"/api/v1/members/{m.id}/logo",
            files={"file": ("logo.png", _make_png_bytes(), "image/png")},
            headers=auth_headers,
        )
        assert resp.status_code == 204

    async def test_upload_jpeg_converts_to_png(
        self, client: AsyncClient, ixp: IXP, auth_headers: dict,
        db_session: AsyncSession, tmp_path, monkeypatch
    ) -> None:
        from ixforge.config import get_settings
        monkeypatch.setattr(get_settings(), "media_root", str(tmp_path))
        m = Member(ixp_id=ixp.id, name="ISP2", short_name="I2", asn=65011, state=MemberState.prospect)
        db_session.add(m)
        await db_session.flush()
        resp = await client.post(
            f"/api/v1/members/{m.id}/logo",
            files={"file": ("logo.jpg", _make_jpeg_bytes(), "image/jpeg")},
            headers=auth_headers,
        )
        assert resp.status_code == 204
        assert os.path.exists(str(tmp_path / "members" / str(m.id) / "logo.png"))

    async def test_upload_invalid_mime_rejected(
        self, client: AsyncClient, ixp: IXP, auth_headers: dict, db_session: AsyncSession
    ) -> None:
        m = Member(ixp_id=ixp.id, name="ISP3", short_name="I3", asn=65012, state=MemberState.prospect)
        db_session.add(m)
        await db_session.flush()
        resp = await client.post(
            f"/api/v1/members/{m.id}/logo",
            files={"file": ("mal.txt", b"hello", "text/plain")},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_delete_logo(
        self, client: AsyncClient, ixp: IXP, auth_headers: dict,
        db_session: AsyncSession, tmp_path, monkeypatch
    ) -> None:
        from ixforge.config import get_settings
        monkeypatch.setattr(get_settings(), "media_root", str(tmp_path))
        m = Member(ixp_id=ixp.id, name="ISP4", short_name="I4", asn=65013, state=MemberState.prospect)
        db_session.add(m)
        await db_session.flush()
        logo_dir = tmp_path / "members" / str(m.id)
        logo_dir.mkdir(parents=True)
        (logo_dir / "logo.png").write_bytes(_make_png_bytes())
        resp = await client.delete(f"/api/v1/members/{m.id}/logo", headers=auth_headers)
        assert resp.status_code == 204
        assert not os.path.exists(str(logo_dir / "logo.png"))


class TestMemberLogoRead:
    """El sitio publico sirve el logo desde su propio dominio pidiendoselo al Core,
    asi que el navegador del visitante nunca necesita alcanzar la red interna
    """

    async def _miembro(self, db_session, ixp, tmp_path, monkeypatch, asn, con_logo=True):
        from ixforge.config import get_settings
        monkeypatch.setattr(get_settings(), "media_root", str(tmp_path))
        m = Member(
            ixp_id=ixp.id, name=f"ISP {asn}", short_name=f"L{asn}"[:10],
            asn=asn, state=MemberState.active,
        )
        db_session.add(m)
        await db_session.flush()
        contenido = _make_png_bytes()
        if con_logo:
            carpeta = tmp_path / "members" / str(m.id)
            carpeta.mkdir(parents=True)
            (carpeta / "logo.png").write_bytes(contenido)
        return m, contenido

    async def test_devuelve_el_png(
        self, client: AsyncClient, ixp: IXP, auth_headers: dict,
        db_session: AsyncSession, tmp_path, monkeypatch
    ) -> None:
        m, contenido = await self._miembro(db_session, ixp, tmp_path, monkeypatch, 65020)

        resp = await client.get(f"/api/v1/members/{m.id}/logo", headers=auth_headers)

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        assert resp.content == contenido

    async def test_miembro_sin_logo_da_404(
        self, client: AsyncClient, ixp: IXP, auth_headers: dict,
        db_session: AsyncSession, tmp_path, monkeypatch
    ) -> None:
        m, _ = await self._miembro(db_session, ixp, tmp_path, monkeypatch, 65021, con_logo=False)

        resp = await client.get(f"/api/v1/members/{m.id}/logo", headers=auth_headers)

        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"

    async def test_miembro_inexistente_da_404(
        self, client: AsyncClient, ixp: IXP, auth_headers: dict, tmp_path, monkeypatch
    ) -> None:
        from ixforge.config import get_settings
        monkeypatch.setattr(get_settings(), "media_root", str(tmp_path))

        resp = await client.get(f"/api/v1/members/{uuid.uuid4()}/logo", headers=auth_headers)

        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"

    async def test_una_key_de_solo_lectura_de_miembros_lo_puede_leer(
        self, client: AsyncClient, ixp: IXP, admin_user, db_session: AsyncSession,
        tmp_path, monkeypatch
    ) -> None:
        """Es el caso de la key del sitio publico: members:read y nada mas"""
        m, contenido = await self._miembro(db_session, ixp, tmp_path, monkeypatch, 65022)
        raw = "ixf_logoread1234567890abcdef1234567890abcdef1234567890abcdef12345678"
        db_session.add(APIKey(
            id=uuid.uuid4(), key_hash=hash_api_key(raw), prefix=raw[:12], name="sitio",
            scopes=["members:read"], user_id=admin_user.id, is_active=True,
        ))
        await db_session.flush()

        resp = await client.get(f"/api/v1/members/{m.id}/logo", headers={"X-API-Key": raw})

        assert resp.status_code == 200
        assert resp.content == contenido

    async def test_sin_autenticacion_no_entrega_nada(
        self, client: AsyncClient, ixp: IXP, db_session: AsyncSession, tmp_path, monkeypatch
    ) -> None:
        m, _ = await self._miembro(db_session, ixp, tmp_path, monkeypatch, 65023)

        resp = await client.get(f"/api/v1/members/{m.id}/logo")

        assert resp.status_code == 401

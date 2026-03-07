"""Tests for member logo upload/delete."""

import io
import os

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.enums import MemberState
from ixforge.models.ixp import IXP
from ixforge.models.member import Member


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

"""Member logo upload/delete endpoints."""

import asyncio
import io
import uuid
from pathlib import Path

from fastapi import APIRouter, Response, UploadFile
from PIL import Image

from ixforge.api.deps import AdminUser, DBSession, IXPId
from ixforge.config import get_settings
from ixforge.exceptions import ValidationError
from ixforge.services.members import get as get_member

_ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}
_MAX_SIZE = 2 * 1024 * 1024  # 2MB

logo_router = APIRouter(tags=["members"])


def _logo_path(media_root: str, member_id: uuid.UUID) -> Path:
    return Path(media_root) / "members" / str(member_id) / "logo.png"


def _process_and_save(content: bytes, dest: Path) -> None:
    try:
        img = Image.open(io.BytesIO(content))
        img.verify()
        img = Image.open(io.BytesIO(content))  # re-open after verify
    except Exception as exc:
        raise ValueError("invalid image") from exc
    img = img.convert("RGBA") if img.mode in ("RGBA", "LA", "P") else img.convert("RGB")  # type: ignore[assignment]
    img.save(str(dest), format="PNG")


@logo_router.post("/members/{member_id}/logo", status_code=204)
async def upload_logo(
    member_id: uuid.UUID,
    file: UploadFile,
    db: DBSession,
    _admin: AdminUser,
    _ixp_id: IXPId,
) -> Response:
    await get_member(db, member_id)

    if file.content_type not in _ALLOWED_MIME:
        raise ValidationError(
            f"Unsupported file type: {file.content_type}. Allowed: {', '.join(sorted(_ALLOWED_MIME))}"
        )

    content = await file.read()
    if len(content) > _MAX_SIZE:
        raise ValidationError("File exceeds 2MB limit")

    settings = get_settings()
    dest = _logo_path(settings.media_root, member_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        await asyncio.to_thread(_process_and_save, content, dest)
    except ValueError as exc:
        raise ValidationError("El archivo no es una imagen válida") from exc

    return Response(status_code=204)


@logo_router.delete("/members/{member_id}/logo", status_code=204)
async def delete_logo(
    member_id: uuid.UUID,
    db: DBSession,
    _admin: AdminUser,
    _ixp_id: IXPId,
) -> Response:
    await get_member(db, member_id)
    settings = get_settings()
    dest = _logo_path(settings.media_root, member_id)
    if dest.exists():
        dest.unlink()
    return Response(status_code=204)

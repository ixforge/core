"""Member logo upload, download and delete endpoints."""

import asyncio
import io
import uuid
from pathlib import Path

from fastapi import APIRouter, Response, UploadFile
from fastapi.responses import FileResponse
from PIL import Image

from ixforge.api.deps import AdminUser, CurrentUser, DBSession, IXPId
from ixforge.config import get_settings
from ixforge.exceptions import NotFoundError, ValidationError
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


@logo_router.get("/members/{member_id}/logo", response_class=FileResponse)
async def download_logo(
    member_id: uuid.UUID,
    db: DBSession,
    _user: CurrentUser,
    ixp_id: IXPId,
) -> FileResponse:
    """El logo como PNG, para quien lo sirva desde su propio dominio

    El sitio publico lo pide aca y lo entrega desde su servidor: el navegador del
    visitante no alcanza la red donde vive el Core, y la URL de media que publica
    logo_url es la del portal
    """
    await get_member(db, ixp_id, member_id)
    dest = _logo_path(get_settings().media_root, member_id)
    if not await asyncio.to_thread(dest.is_file):
        raise NotFoundError("MemberLogo", str(member_id))
    return FileResponse(dest, media_type="image/png")


@logo_router.post("/members/{member_id}/logo", status_code=204)
async def upload_logo(
    member_id: uuid.UUID,
    file: UploadFile,
    db: DBSession,
    _admin: AdminUser,
    ixp_id: IXPId,
) -> Response:
    await get_member(db, ixp_id, member_id)

    if file.content_type not in _ALLOWED_MIME:
        raise ValidationError(
            f"Unsupported file type: {file.content_type}. Allowed: {', '.join(sorted(_ALLOWED_MIME))}"
        )

    content = await file.read(_MAX_SIZE + 1)
    if len(content) > _MAX_SIZE:
        raise ValidationError("File exceeds 2MB limit")

    settings = get_settings()
    dest = _logo_path(settings.media_root, member_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        await asyncio.to_thread(_process_and_save, content, dest)
    except ValueError as exc:
        raise ValidationError("The file is not a valid image") from exc

    return Response(status_code=204)


@logo_router.delete("/members/{member_id}/logo", status_code=204)
async def delete_logo(
    member_id: uuid.UUID,
    db: DBSession,
    _admin: AdminUser,
    ixp_id: IXPId,
) -> Response:
    await get_member(db, ixp_id, member_id)
    settings = get_settings()
    dest = _logo_path(settings.media_root, member_id)
    await asyncio.to_thread(_delete_if_exists, dest)
    return Response(status_code=204)


def _delete_if_exists(path: Path) -> None:
    if path.exists():
        path.unlink()

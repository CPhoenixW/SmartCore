from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth.security import require_authenticated_user_id
from app.db.session import get_db
from app.new_core import crud

router = APIRouter(prefix="/api/user", tags=["user-avatar"])

_AVATAR_DIR = Path("data/avatars")
_MAX_AVATAR_BYTES = 5 * 1024 * 1024
_MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".avif": "image/avif",
}
_HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1"}


def _detect_image_extension(content: bytes) -> str | None:
    if content.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return ".webp"
    if len(content) >= 12 and content[4:8] == b"ftyp":
        brand = content[8:12]
        if brand in {b"avif", b"avis"}:
            return ".avif"
        if brand in _HEIF_BRANDS:
            raise HTTPException(
                status_code=400,
                detail="HEIC/HEIF avatars are not supported by most browsers; export the image as JPEG, PNG, WebP, or AVIF",
            )
    return None


@router.post("/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    user_id: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    content = await file.read(_MAX_AVATAR_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="avatar file is empty")
    if len(content) > _MAX_AVATAR_BYTES:
        raise HTTPException(status_code=413, detail="avatar file must not exceed 5 MB")

    extension = _detect_image_extension(content)
    if extension is None:
        raise HTTPException(status_code=400, detail="avatar must be a valid JPEG, PNG, GIF, WebP, or AVIF image")

    _AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}{extension}"
    destination = _AVATAR_DIR / filename
    temporary = destination.with_suffix(f"{destination.suffix}.tmp")
    temporary.write_bytes(content)
    temporary.replace(destination)

    avatar_url = f"/api/user/avatar/{filename}"
    try:
        user = crud.getCurrentUser(db, userId=user_id)
        previous_url = str(user.get("avatarUrl") or "")
        crud.updateCurrentUser(db, userId=user_id, avatarUrl=avatar_url)
        if previous_url.startswith("/api/user/avatar/"):
            previous_path = _AVATAR_DIR / Path(previous_url).name
            if previous_path != destination:
                previous_path.unlink(missing_ok=True)
    except Exception:
        destination.unlink(missing_ok=True)
        raise

    return {"ok": True, "data": {"avatarUrl": avatar_url}}


@router.get("/avatar/{filename}", include_in_schema=False)
def read_avatar(filename: str) -> FileResponse:
    safe_name = Path(filename).name
    extension = Path(safe_name).suffix.lower()
    if safe_name != filename or extension not in _MEDIA_TYPES:
        raise HTTPException(status_code=404, detail="avatar not found")
    path = _AVATAR_DIR / safe_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="avatar not found")
    return FileResponse(path, media_type=_MEDIA_TYPES[extension])

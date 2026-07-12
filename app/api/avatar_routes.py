from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.new_core import crud

router = APIRouter(prefix="/api/user", tags=["user-avatar"])

_AVATAR_DIR = Path("data/avatars")
_MAX_AVATAR_BYTES = 5 * 1024 * 1024
_MIME_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


def _valid_image_signature(content: bytes, mime_type: str) -> bool:
    if mime_type == "image/jpeg":
        return content.startswith(b"\xff\xd8\xff")
    if mime_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if mime_type == "image/gif":
        return content.startswith((b"GIF87a", b"GIF89a"))
    if mime_type == "image/webp":
        return len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    return False


@router.post("/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    mime_type = (file.content_type or "").lower()
    extension = _MIME_EXTENSIONS.get(mime_type)
    if extension is None:
        raise HTTPException(status_code=400, detail="avatar must be JPEG, PNG, GIF, or WebP")

    content = await file.read(_MAX_AVATAR_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="avatar file is empty")
    if len(content) > _MAX_AVATAR_BYTES:
        raise HTTPException(status_code=413, detail="avatar file must not exceed 5 MB")
    if not _valid_image_signature(content, mime_type):
        raise HTTPException(status_code=400, detail="avatar file content does not match its image type")

    _AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}{extension}"
    destination = _AVATAR_DIR / filename
    temporary = destination.with_suffix(f"{destination.suffix}.tmp")
    temporary.write_bytes(content)
    temporary.replace(destination)

    avatar_url = f"/api/user/avatar/{filename}"
    try:
        user = crud.getCurrentUser(db)
        previous_url = str(user.get("avatarUrl") or "")
        crud.updateCurrentUser(db, avatarUrl=avatar_url)
        if previous_url.startswith("/api/user/avatar/"):
            previous_name = Path(previous_url).name
            previous_path = _AVATAR_DIR / previous_name
            if previous_path != destination:
                previous_path.unlink(missing_ok=True)
    except Exception:
        destination.unlink(missing_ok=True)
        raise

    return {"ok": True, "data": {"avatarUrl": avatar_url}}


@router.get("/avatar/{filename}", include_in_schema=False)
def read_avatar(filename: str) -> FileResponse:
    safe_name = Path(filename).name
    if safe_name != filename or Path(safe_name).suffix.lower() not in set(_MIME_EXTENSIONS.values()):
        raise HTTPException(status_code=404, detail="avatar not found")
    path = _AVATAR_DIR / safe_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="avatar not found")
    return FileResponse(path)

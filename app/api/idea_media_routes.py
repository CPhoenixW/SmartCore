from __future__ import annotations

import mimetypes
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth.security import require_authenticated_user_id
from app.config import Settings, get_settings
from app.db.session import get_db
from app.new_core import crud

router = APIRouter(prefix="/api/idea", tags=["idea-media"])
_ALLOWED = {"image/jpeg", "image/png", "image/webp", "application/pdf", "text/plain", "application/zip", "application/x-zip-compressed"}
_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "application/pdf": ".pdf", "text/plain": ".txt", "application/zip": ".zip", "application/x-zip-compressed": ".zip"}


@router.post("/uploads")
async def upload_idea_files(files: list[UploadFile] = File(...), userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict:
    if not files or len(files) > 10:
        raise HTTPException(status_code=400, detail="upload 1 to 10 files")
    results = []
    for file in files:
        mime = (file.content_type or "").lower()
        if mime not in _ALLOWED:
            raise HTTPException(status_code=415, detail="only JPG, PNG, WebP, PDF, TXT, and ZIP are supported")
        content = await file.read(settings.idea_media_max_bytes + 1)
        if not content or len(content) > settings.idea_media_max_bytes:
            raise HTTPException(status_code=413, detail="attachment is empty or exceeds 20 MB")
        name = Path(file.filename or "attachment").name[:300]
        destination = settings.idea_media_path / f"{uuid4().hex}{_EXT[mime]}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        try:
            row = crud.createIdeaUpload(db, userId=userId, fileName=name, mimeType=mime, storagePath=str(destination), sizeBytes=len(content))
            results.append({key: row[key] for key in ("uploadId", "fileName", "mimeType", "sizeBytes")})
        except Exception:
            destination.unlink(missing_ok=True)
            raise
    return {"ok": True, "data": results}


@router.get("/attachments/{attachmentId}", include_in_schema=False)
def download_idea_attachment(attachmentId: str, userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db)) -> FileResponse:
    try:
        row = crud.getIdeaAttachment(db, attachmentId, userId=userId)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="attachment not found") from exc
    path = Path(row.storagePath)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="attachment file not found")
    disposition = "inline" if row.mimeType.startswith("image/") else "attachment"
    return FileResponse(path, media_type=row.mimeType or mimetypes.guess_type(row.fileName)[0], filename=row.fileName, content_disposition_type=disposition)

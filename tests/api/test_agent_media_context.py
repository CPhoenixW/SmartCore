from __future__ import annotations

from app.server.db.session import SessionLocal
from app.server.new_core import crud


def test_agent_media_context_is_owner_scoped_and_returns_image(
    app_env, client, agent_headers, tmp_path
) -> None:
    image_path = tmp_path / "private.png"
    image_path.write_bytes(b"png-bytes")
    db = SessionLocal()
    try:
        crud.getCurrentUser(db)
        upload = crud.createIdeaUpload(
            db,
            userId="default",
            fileName="private.png",
            mimeType="image/png",
            storagePath=str(image_path),
            sizeBytes=image_path.stat().st_size,
        )
    finally:
        db.close()

    headers = agent_headers("default")
    context = client.get(
        "/agent/idea/media-context",
        params=[("uploadIds", upload["uploadId"])],
        headers=headers,
    )
    assert context.status_code == 200
    assert context.json()["data"]["attachments"][0]["uploadId"] == upload["uploadId"]

    image = client.get(f"/agent/idea/media-context/{upload['uploadId']}", headers=headers)
    assert image.status_code == 200
    assert image.headers["content-type"].startswith("image/png")
    assert image.content == b"png-bytes"

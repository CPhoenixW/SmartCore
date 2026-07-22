from fastapi.testclient import TestClient

from app.agent.scope import issue_agent_scope
from app.auth.security import create_session_token
from app.db.session import SessionLocal
from app.main import create_app
from app.new_core import crud


def test_web_scope_can_only_ocr_its_own_image_upload(app_env, monkeypatch, tmp_path) -> None:
    image_path = tmp_path / "image.png"
    image_path.write_bytes(b"image-bytes")
    client = TestClient(create_app())
    db = SessionLocal()
    try:
        upload = crud.createIdeaUpload(
            db,
            userId="default",
            fileName="diagram.png",
            mimeType="image/png",
            storagePath=str(image_path),
            sizeBytes=11,
        )
    finally:
        db.close()
    monkeypatch.setattr("app.agent.routes.analyze_image", lambda *_args, **_kwargs: "图中包含流程图")
    scope = issue_agent_scope(userId="default", purpose="web")
    headers = {"X-SmartCore-Agent-Token": "agent-secret", "X-SmartCore-Agent-Scope": scope}
    response = client.post("/agent/media/ocr", headers=headers, json={"uploadId": upload["uploadId"]})
    assert response.status_code == 200
    assert response.json()["data"]["text"] == "图中包含流程图"
    evidence = response.json()["data"]["ocrEvidence"]

    rejected = client.post(
        "/agent/idea/capture",
        headers=headers,
        json={
            "title": "流程图",
            "srcType": "media",
            "uploadIds": [upload["uploadId"]],
        },
    )
    assert rejected.json()["ok"] is False
    assert rejected.json()["errors"] == [
        "valid mediaImageOcr evidence required for every image"
    ]

    captured = client.post(
        "/agent/idea/capture",
        headers=headers,
        json={
            "title": "流程图",
            "description": "图中包含流程图",
            "srcType": "media",
            "uploadIds": [upload["uploadId"]],
            "ocrEvidence": {upload["uploadId"]: evidence},
        },
    )
    assert captured.json()["ok"] is True
    db = SessionLocal()
    try:
        ideas = crud.listIdeas(db, userId="default")
    finally:
        db.close()
    assert ideas[0]["attachments"][0]["fileName"] == "diagram.png"

    foreign_scope = issue_agent_scope(userId="other-user", purpose="web")
    denied = client.post(
        "/agent/media/ocr",
        headers={**headers, "X-SmartCore-Agent-Scope": foreign_scope},
        json={"uploadId": upload["uploadId"]},
    )
    assert denied.json()["ok"] is False
    assert denied.json()["errors"] == ["attachment not found"]


def test_document_capture_does_not_require_ocr_evidence(app_env, tmp_path) -> None:
    document_path = tmp_path / "notes.pdf"
    document_path.write_bytes(b"pdf")
    client = TestClient(create_app())
    db = SessionLocal()
    try:
        upload = crud.createIdeaUpload(
            db,
            userId="default",
            fileName="notes.pdf",
            mimeType="application/pdf",
            storagePath=str(document_path),
            sizeBytes=3,
        )
    finally:
        db.close()
    scope = issue_agent_scope(userId="default", purpose="web")
    response = client.post(
        "/agent/idea/capture",
        headers={"X-SmartCore-Agent-Token": "agent-secret", "X-SmartCore-Agent-Scope": scope},
        json={"title": "notes", "srcType": "media", "uploadIds": [upload["uploadId"]]},
    )
    assert response.json()["ok"] is True


def test_browser_cannot_bypass_image_ocr_with_direct_idea_create(app_env, tmp_path) -> None:
    image_path = tmp_path / "direct.png"
    image_path.write_bytes(b"image")
    client = TestClient(create_app())
    client.cookies.set("smartcore_session", create_session_token("default"))
    db = SessionLocal()
    try:
        upload = crud.createIdeaUpload(
            db,
            userId="default",
            fileName="direct.png",
            mimeType="image/png",
            storagePath=str(image_path),
            sizeBytes=5,
        )
    finally:
        db.close()
    response = client.post(
        "/api/idea",
        json={
            "title": "绕过 OCR",
            "description": "",
            "srcType": "media",
            "uploadIds": [upload["uploadId"]],
        },
    )
    assert response.status_code == 409
    assert "OCR cannot be skipped" in response.json()["detail"]

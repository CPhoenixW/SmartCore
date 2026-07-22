from fastapi.testclient import TestClient

from app.agent.scope import issue_agent_scope
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

    foreign_scope = issue_agent_scope(userId="other-user", purpose="web")
    denied = client.post(
        "/agent/media/ocr",
        headers={**headers, "X-SmartCore-Agent-Scope": foreign_scope},
        json={"uploadId": upload["uploadId"]},
    )
    assert denied.json()["ok"] is False
    assert denied.json()["errors"] == ["attachment not found"]

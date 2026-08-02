from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.server.agent.scope import issue_agent_scope
from app.server.auth.security import create_session_token
from app.server.db.session import SessionLocal, init_db
from app.server.main import create_app
from app.server.new_core import crud
from app.server.new_core.models import AppUser, IdeaMediaJob, IdeaUpload, nowIso

pytestmark = pytest.mark.api


def test_idea_attachment_url_matches_authorized_download_route() -> None:
    attachment = type(
        "Attachment",
        (),
        {
            "attachmentId": "att-1",
            "fileName": "x.jpg",
            "mimeType": "image/jpeg",
            "sizeBytes": 1,
            "createdAt": "now",
        },
    )()
    assert crud._attachmentDict(attachment)["url"] == "/api/idea/attachments/att-1"


def _signed_client(user_id: str = "default") -> TestClient:
    client = TestClient(create_app())
    client.cookies.set("smartcore_session", create_session_token(user_id))
    return client


def _upload(db, tmp_path: Path, *, name: str, mime: str, user_id: str = "default") -> dict:
    path = tmp_path / name
    path.write_bytes(name.encode())
    return crud.createIdeaUpload(
        db,
        userId=user_id,
        fileName=name,
        mimeType=mime,
        storagePath=str(path),
        sizeBytes=path.stat().st_size,
    )


def test_idea_edit_atomically_adds_and_removes_documents(app_env, tmp_path) -> None:
    client = _signed_client()
    db = SessionLocal()
    try:
        old_upload = _upload(db, tmp_path, name="old.txt", mime="text/plain")
        idea = crud.createIdea(
            db,
            title="Editable",
            uploadIds=[old_upload["uploadId"]],
            userId="default",
        )
        idea = next(
            item
            for item in crud.listIdeas(db, userId="default")
            if item["ideaId"] == idea["ideaId"]
        )
        new_upload = _upload(db, tmp_path, name="new.pdf", mime="application/pdf")
    finally:
        db.close()
    old_attachment = idea["attachments"][0]
    old_path = tmp_path / "old.txt"

    response = client.patch(
        f"/api/idea/{idea['ideaId']}",
        json={
            "expectedRevision": idea["revision"],
            "title": "Updated",
            "addUploadIds": [new_upload["uploadId"]],
            "removeAttachmentIds": [old_attachment["attachmentId"]],
        },
    )

    assert response.status_code == 200
    updated = response.json()["data"]
    assert updated["revision"] == idea["revision"] + 1
    assert [item["fileName"] for item in updated["attachments"]] == ["new.pdf"]
    assert old_path.exists() is False


def test_idea_edit_rejects_stale_and_foreign_requests(app_env) -> None:
    owner = _signed_client()
    db = SessionLocal()
    try:
        idea = crud.createIdea(db, title="Private", userId="default")
        now = nowIso()
        db.add(
            AppUser(
                userId="other",
                loginName="other",
                role="user",
                displayName="Other",
                language="zh",
                createdAt=now,
                updatedAt=now,
            )
        )
        db.commit()
    finally:
        db.close()

    stale = owner.patch(
        f"/api/idea/{idea['ideaId']}",
        json={"expectedRevision": idea["revision"] + 1, "title": "Stale"},
    )
    assert stale.status_code == 409
    assert (
        _signed_client("other")
        .patch(f"/api/idea/{idea['ideaId']}", json={"title": "Taken"})
        .status_code
        == 404
    )
    assert _signed_client("other").delete(f"/api/idea/{idea['ideaId']}").status_code == 404


def test_multimodal_media_job_is_required_for_edit(
    app_env, monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("OPENCLAW_EVENTS_ENDPOINT", "http://openclaw.local/events")
    monkeypatch.setenv("OPENCLAW_EVENTS_TOKEN", "events-secret")
    dispatched: list[dict] = []

    def fake_post(_url, **kwargs):
        dispatched.append(kwargs["json"])

        class Response:
            status_code = 202

            def raise_for_status(self):
                return None

        return Response()

    monkeypatch.setattr("app.server.api.routes.httpx.post", fake_post)
    client = _signed_client()
    db = SessionLocal()
    try:
        idea = crud.createIdea(db, title="Image edit", userId="default")
        upload = _upload(db, tmp_path, name="diagram.png", mime="image/png")
    finally:
        db.close()
    queued = client.post(
        "/api/idea/media-jobs",
        json={"ideaId": idea["ideaId"], "uploadId": upload["uploadId"]},
    )
    assert queued.status_code == 202
    job = queued.json()["data"]
    assert dispatched[0]["jobId"] == job["jobId"]
    assert job["stat"] == "processing"
    scope = issue_agent_scope(userId="default", purpose="web")
    headers = {
        "X-SmartCore-Agent-Token": "agent-secret",
        "X-SmartCore-Agent-Scope": scope,
    }
    completed = client.post(
        "/agent/idea/media-job/complete",
        headers=headers,
        json={
            "jobId": job["jobId"],
            "summary": "流程图展示了主要处理步骤。",
        },
    )
    assert completed.json()["ok"] is True
    assert client.get(f"/api/idea/media-jobs/{job['jobId']}").json()["data"]["stat"] == "ready"

    attached = client.patch(
        f"/api/idea/{idea['ideaId']}",
        json={
            "expectedRevision": idea["revision"],
            "addUploadIds": [upload["uploadId"]],
        },
    )
    assert attached.status_code == 200
    assert attached.json()["data"]["attachments"][0]["fileName"] == "diagram.png"
    db = SessionLocal()
    try:
        assert db.get(IdeaMediaJob, job["jobId"]).stat == "consumed"
    finally:
        db.close()


def test_failed_media_job_requires_explicit_retry(app_env, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPENCLAW_EVENTS_ENDPOINT", "http://openclaw.local/events")
    monkeypatch.setenv("OPENCLAW_EVENTS_TOKEN", "events-secret")
    dispatched: list[dict] = []

    def fake_post(_url, **kwargs):
        dispatched.append(kwargs["json"])

        class Response:
            def raise_for_status(self):
                return None

        return Response()

    monkeypatch.setattr("app.server.api.routes.httpx.post", fake_post)
    client = _signed_client()
    db = SessionLocal()
    try:
        idea = crud.createIdea(db, title="Retry image", userId="default")
        upload = _upload(db, tmp_path, name="retry.png", mime="image/png")
    finally:
        db.close()

    queued = client.post(
        "/api/idea/media-jobs",
        json={"ideaId": idea["ideaId"], "uploadId": upload["uploadId"]},
    ).json()["data"]
    scope = issue_agent_scope(userId="default", purpose="web")
    headers = {
        "X-SmartCore-Agent-Token": "agent-secret",
        "X-SmartCore-Agent-Scope": scope,
    }
    failed = client.post(
        "/agent/idea/media-job/fail",
        headers=headers,
        json={"jobId": queued["jobId"], "errorMessage": "temporary failure"},
    )
    assert failed.json()["data"]["stat"] == "failed"
    assert client.get(f"/api/idea/media-jobs/{queued['jobId']}").json()["data"]["stat"] == "failed"
    assert len(dispatched) == 1

    retried = client.post(f"/api/idea/media-jobs/{queued['jobId']}/retry")
    assert retried.status_code == 202
    assert retried.json()["data"]["stat"] == "processing"
    assert len(dispatched) == 2
    assert dispatched[1]["jobId"] == queued["jobId"]


def test_expired_temporary_media_is_removed_without_touching_attachments(app_env, tmp_path) -> None:
    init_db()
    db = SessionLocal()
    try:
        attached_upload = _upload(db, tmp_path, name="attached.txt", mime="text/plain")
        idea = crud.createIdea(
            db,
            title="Keep attachment",
            uploadIds=[attached_upload["uploadId"]],
            userId="default",
        )
        expired_upload = _upload(db, tmp_path, name="expired.txt", mime="text/plain")
        upload_row = db.get(IdeaUpload, expired_upload["uploadId"])
        assert upload_row is not None
        upload_row.createdAt = "2026-07-20T00:00:00+08:00"
        db.commit()

        result = crud.cleanupExpiredIdeaMedia(
            db,
            now="2026-07-23T12:00:00+08:00",
        )
        kept = next(
            item
            for item in crud.listIdeas(db, userId="default")
            if item["ideaId"] == idea["ideaId"]
        )
    finally:
        db.close()

    assert result == {"jobs": 0, "uploads": 1}
    assert (tmp_path / "expired.txt").exists() is False
    assert (tmp_path / "attached.txt").exists() is True
    assert kept["attachments"][0]["fileName"] == "attached.txt"


def test_multimodal_agent_can_only_capture_its_own_image_upload(app_env, tmp_path) -> None:
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
    scope = issue_agent_scope(userId="default", purpose="web")
    headers = {"X-SmartCore-Agent-Token": "agent-secret", "X-SmartCore-Agent-Scope": scope}
    foreign_scope = issue_agent_scope(userId="other-user", purpose="web")
    denied = client.post(
        "/agent/idea/capture",
        headers={**headers, "X-SmartCore-Agent-Scope": foreign_scope},
        json={
            "title": "流程图",
            "srcType": "media",
            "uploadIds": [upload["uploadId"]],
        },
    )
    assert denied.json()["ok"] is False
    assert denied.json()["errors"] == ["one or more attachments are unavailable"]

    captured = client.post(
        "/agent/idea/capture",
        headers=headers,
        json={
            "title": "流程图",
            "description": "图中包含流程图",
            "srcType": "media",
            "uploadIds": [upload["uploadId"]],
        },
    )
    assert captured.json()["ok"] is True
    db = SessionLocal()
    try:
        ideas = crud.listIdeas(db, userId="default")
    finally:
        db.close()
    assert ideas[0]["attachments"][0]["fileName"] == "diagram.png"


def test_retired_ocr_route_is_not_registered(app_env) -> None:
    client = TestClient(create_app())
    headers = {
        "X-SmartCore-Agent-Token": "agent-secret",
        "X-SmartCore-Agent-Scope": issue_agent_scope(userId="default", purpose="web"),
    }
    assert client.post("/agent/media/ocr", headers=headers, json={}).status_code == 404


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


def test_browser_image_create_must_use_multimodal_processing(app_env, tmp_path) -> None:
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
            "title": "直接图片",
            "description": "",
            "srcType": "media",
            "uploadIds": [upload["uploadId"]],
        },
    )
    assert response.status_code == 409
    assert "multimodal processing" in response.json()["detail"]

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.server.db.session import Base
from app.server.device import service
from app.server.device.routes import router
from app.server.new_core import models  # noqa: F401


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return Session(engine)


def test_device_router_exposes_heartbeat_and_photo_contract() -> None:
    paths = {route.path for route in router.routes}

    assert "/dev/heartbeat" in paths
    assert "/dev/photo/request" in paths
    assert "/dev/photo/{request_id}" in paths
    assert "/dev/photo/{request_id}/failed" in paths
    assert "/api/device/{device_id}/photoRequest" in paths
    assert "/api/device/photoRequest/{request_id}" in paths
    assert "/api/device/photoRequest/{request_id}/image" in paths


def test_heartbeat_and_async_photo_request_lifecycle() -> None:
    db = _session()
    try:
        state = service.record_heartbeat(
            db,
            device_id="pi",
            current_time="2026-07-07T21:30:10+08:00",
            present=True,
            persons=[{"name": "Phoenix", "confidence": 0.94}],
            state_confidence=0.91,
            state="working",
            extra_meta={"model": "face-v3"},
        )
        assert state["state"] == "working"
        assert state["meta"]["present"] is True
        assert state["meta"]["persons"][0]["name"] == "Phoenix"

        created = service.create_photo_request(
            db,
            device_id="pi",
            reason="integration test",
            ttl_seconds=300,
        )
        request_id = created["requestId"]
        pending = service.next_pending_photo_request(db, device_id="pi")
        assert pending is not None
        assert pending["requestId"] == request_id
        assert pending["stat"] == "pending"

        uploaded = service.complete_photo_request(
            db,
            request_id=request_id,
            device_id="pi",
            captured_at="2026-07-07T21:31:00+08:00",
            image_path="/tmp/test.jpg",
            mime_type="image/jpeg",
            image_size=128,
            recognition={"present": True},
        )
        assert uploaded["stat"] == "uploaded"
        assert uploaded["imageAvailable"] is True
        assert service.next_pending_photo_request(db, device_id="pi") is None
    finally:
        db.close()

#!/usr/bin/env python3
"""YOLO + 人脸识别，每 10 秒 POST /dev/heartbeat (v2)。"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2
from ultralytics import YOLO

from face_identity import (
    FaceIdentity,
    draw_identity,
    load_known_faces,
    match_face,
    create_face_detector,
    create_face_recognizer,
    missing_model_paths,
)

CAMERA = 0
PHOTO_COUNT = 2
CAPTURE_INTERVAL = 1.0
PERSON_RATIO = 1 / 3
CAPTURE_DIR = Path('captures')
OUTPUT_DIR = Path('output')
LOG_ROOT = Path('logs')
MODEL = 'yolo11n.pt'
CONF = 0.25
PHOENIX_ID = 'phoenix'
VALID_STATES = {'working', 'away', 'unknown', 'offline'}
HEARTBEAT_BACKOFF = (2, 5, 10, 30, 60)
TOKEN_HEADER = 'X-SmartCore-Device-Token'
ENV_PATHS = (Path('/etc/smartcore-pi.env'), Path('.smartcore.env'))
LOCAL_TZ = timezone(timedelta(hours=8))


def load_smartcore_env() -> None:
    for env_path in ENV_PATHS:
        if not env_path.exists():
            continue
        try:
            lines = env_path.read_text().splitlines()
        except OSError:
            # systemd EnvironmentFile 已注入时，/etc/smartcore-pi.env 可能不可直接读取
            continue
        for raw_line in lines:
            line = raw_line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip().strip('\'"'))


def server_url() -> str:
    return (
        os.environ.get('SMARTCORE_SERVER')
        or os.environ.get('SMARTCORE_BASE_URL')
        or ''
    ).rstrip('/')


def device_id() -> str:
    return os.environ.get('SMARTCORE_DEVICE_ID') or os.environ.get('SMARTCORE_DEV_ID', 'pi')


def device_token() -> str:
    return os.environ.get('SMARTCORE_DEVICE_TOKEN', '')


def http_timeout() -> float:
    return float(os.environ.get('SMARTCORE_POST_TIMEOUT', '5'))


def log_dir() -> Path:
    configured = os.environ.get('SMARTCORE_LOG_DIR')
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parent / LOG_ROOT


def heartbeat_seconds() -> float:
    return float(os.environ.get('SMARTCORE_HEARTBEAT_SECONDS', '10'))


def snapshot_seconds() -> float:
    return float(os.environ.get('SMARTCORE_SNAPSHOT_SECONDS', '60'))


def retention_seconds() -> float:
    hours = float(os.environ.get('SMARTCORE_RETENTION_HOURS', '24'))
    return hours * 3600


def iso_now() -> str:
    return datetime.now(LOCAL_TZ).isoformat(timespec='seconds')


def snapshot_stem(dt: datetime) -> str:
    return dt.strftime('%Y%m%dT%H%M%S') + dt.strftime('%z')


def auth_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {TOKEN_HEADER: device_token()}
    if extra:
        headers.update(extra)
    return headers


def face_bbox(identity: FaceIdentity) -> list[int]:
    x, y, w, h = identity.box
    return [x, y, x + w, y + h]


def person_entry(identity: FaceIdentity) -> dict:
    return {
        'personId': identity.name,
        'name': identity.name.capitalize(),
        'confidence': round(float(identity.score), 4),
        'bbox': face_bbox(identity),
    }


def preprocess(frame):
    return cv2.flip(frame, 0)


def capture_photos(cap: cv2.VideoCapture) -> tuple[list[Path], cv2.Mat | None]:
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    last_frame = None

    for _ in range(3):
        cap.read()

    for i in range(1, PHOTO_COUNT + 1):
        ok, frame = cap.read()
        if not ok:
            raise RuntimeError(f'第 {i} 张照片拍摄失败')

        processed = preprocess(frame)
        last_frame = processed
        path = CAPTURE_DIR / f'photo_{i}.jpg'
        cv2.imwrite(str(path), processed)
        paths.append(path)

        if i < PHOTO_COUNT:
            time.sleep(CAPTURE_INTERVAL)

    return paths, last_frame


def person_ratio(result) -> float:
    boxes = result.boxes
    if boxes is None or len(boxes) == 0:
        return 0.0

    h, w = result.orig_shape
    img_area = h * w
    max_ratio = 0.0

    for box in boxes:
        if int(box.cls[0]) != 0:
            continue
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        box_area = (x2 - x1) * (y2 - y1)
        max_ratio = max(max_ratio, box_area / img_area)

    return max_ratio


def judge_state(
    ratios: list[float],
    identities: list[str],
    phoenix_identity: FaceIdentity | None,
) -> dict:
    person_detected = bool(ratios) and any(r > PERSON_RATIO for r in ratios)
    present = person_detected

    if person_detected:
        if phoenix_identity is not None:
            return {
                'state': 'working',
                'detail': PHOENIX_ID,
                'identity': PHOENIX_ID,
                'present': present,
                'persons': [person_entry(phoenix_identity)],
                'stateConfidence': round(min(0.99, max(0.5, float(phoenix_identity.score))), 4),
                'reason': 'person_detected_and_known_face',
            }
        if identities:
            return {
                'state': 'unknown',
                'detail': 'unknown',
                'identity': 'unknown',
                'present': present,
                'persons': [],
                'stateConfidence': 0.6,
                'reason': 'person_detected_face_unknown',
            }
        return {
            'state': 'away',
            'detail': 'no_face',
            'identity': None,
            'present': present,
            'persons': [],
            'stateConfidence': 0.6,
            'reason': 'person_detected_but_no_face',
        }

    return {
        'state': 'away',
        'detail': 'absent',
        'identity': None,
        'present': False,
        'persons': [],
        'stateConfidence': 0.6,
        'reason': 'person_not_detected_enough',
    }


def process_round(
    model: YOLO,
    cap: cv2.VideoCapture,
    face_detector,
    face_recognizer,
    known_faces,
) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    paths, last_frame = capture_photos(cap)
    ratios: list[float] = []
    identities: list[str] = []
    phoenix_identity: FaceIdentity | None = None

    for path in paths:
        result = model.predict(str(path), conf=CONF, device='cpu', verbose=False)[0]
        ratio = person_ratio(result)
        ratios.append(ratio)

        image = cv2.imread(str(path))
        identity = None
        if image is not None and ratio > PERSON_RATIO:
            identity = match_face(image, face_detector, face_recognizer, known_faces)
            if identity is not None:
                identities.append(identity.name)
                if identity.name == PHOENIX_ID and (
                    phoenix_identity is None or identity.score > phoenix_identity.score
                ):
                    phoenix_identity = identity

        annotated = result.plot()
        annotated = draw_identity(annotated, identity)
        cv2.imwrite(str(OUTPUT_DIR / f'{path.stem}_result.jpg'), annotated)

    decision = judge_state(ratios, identities, phoenix_identity)
    decision['personRatio'] = round(max(ratios) if ratios else 0.0, 4)
    decision['faceEvidence'] = {
        'ratios': [round(r, 4) for r in ratios],
        'personFrames': sum(1 for r in ratios if r > PERSON_RATIO),
        'faceMatches': identities,
    }
    decision['frame'] = last_frame
    decision['capturedAt'] = iso_now()
    return decision


def heartbeat_payload(result: dict) -> dict:
    state = result['state'] if result['state'] in VALID_STATES else 'unknown'
    return {
        'devId': device_id(),
        'currentTime': iso_now(),
        'present': bool(result.get('present', False)),
        'persons': result.get('persons') or [],
        'stateConfidence': float(result.get('stateConfidence', 0.6)),
        'state': state,
        'meta': {
            'camera': f'cam{CAMERA}',
            'model': 'yolo11n+face',
            'logDir': str(log_dir()),
            'reason': result.get('reason'),
            'personRatio': result.get('personRatio'),
            'faceEvidence': result.get('faceEvidence'),
        },
    }


def post_heartbeat(result: dict) -> dict | None:
    base_url = server_url()
    token = device_token()
    if not base_url or not token:
        print('[heartbeat] 跳过上报: SMARTCORE_SERVER 或 SMARTCORE_DEVICE_TOKEN 未配置', flush=True)
        return None

    payload_obj = heartbeat_payload(result)
    payload = json.dumps(payload_obj).encode('utf-8')
    req = urllib.request.Request(
        f'{base_url}/dev/heartbeat',
        data=payload,
        headers=auth_headers({'Content-Type': 'application/json'}),
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=http_timeout()) as resp:
            body = resp.read().decode('utf-8')
            code = getattr(resp, 'status', '?')
        print(
            f'[heartbeat] success code={code} state={payload_obj["state"]} '
            f'present={payload_obj["present"]} persons={len(payload_obj["persons"])}',
            flush=True,
        )
        return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')
        print(
            f'[heartbeat] failed state={payload_obj["state"]} code={exc.code} err={detail}',
            file=sys.stderr,
            flush=True,
        )
        return None
    except (OSError, urllib.error.URLError) as exc:
        print(
            f'[heartbeat] failed state={payload_obj["state"]} err={exc}',
            file=sys.stderr,
            flush=True,
        )
        return None


def encode_multipart(
    fields: dict[str, str],
    files: dict[str, tuple[str, bytes, str]],
) -> tuple[bytes, str]:
    boundary = f'----SmartCore{uuid.uuid4().hex}'
    chunks: list[bytes] = []

    for name, value in fields.items():
        chunks.extend([
            f'--{boundary}'.encode(),
            f'Content-Disposition: form-data; name="{name}"'.encode(),
            b'',
            value.encode('utf-8'),
        ])

    for name, (filename, content, content_type) in files.items():
        chunks.extend([
            f'--{boundary}'.encode(),
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"'.encode(),
            f'Content-Type: {content_type}'.encode(),
            b'',
            content,
        ])

    chunks.extend([f'--{boundary}--'.encode(), b''])
    return b'\r\n'.join(chunks), boundary


def recognition_json(result: dict) -> dict:
    return {
        'present': bool(result.get('present', False)),
        'state': result.get('state'),
        'stateConfidence': result.get('stateConfidence'),
        'persons': result.get('persons') or [],
    }


def upload_photo(request_id: str, result: dict) -> bool:
    base_url = server_url()
    frame = result.get('frame')
    captured_at = result.get('capturedAt') or iso_now()

    if frame is None:
        return post_photo_failed(request_id, 'camera capture unavailable')

    ok, encoded = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    if not ok:
        return post_photo_failed(request_id, 'jpeg encode failed')

    fields = {
        'devId': device_id(),
        'capturedAt': captured_at,
        'recognition': json.dumps(recognition_json(result), ensure_ascii=False),
    }
    body, boundary = encode_multipart(
        fields,
        {'image': ('current.jpg', encoded.tobytes(), 'image/jpeg')},
    )
    req = urllib.request.Request(
        f'{base_url}/dev/photo/{request_id}',
        data=body,
        headers=auth_headers({'Content-Type': f'multipart/form-data; boundary={boundary}'}),
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=http_timeout()) as resp:
            resp.read()
            code = getattr(resp, 'status', '?')
        print(f'[photo] uploaded requestId={request_id} code={code}', flush=True)
        return True
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')
        print(f'[photo] upload failed requestId={request_id} code={exc.code} err={detail}', file=sys.stderr)
        return False
    except (OSError, urllib.error.URLError) as exc:
        print(f'[photo] upload failed requestId={request_id} err={exc}', file=sys.stderr)
        return False


def post_photo_failed(request_id: str, error: str) -> bool:
    base_url = server_url()
    payload = json.dumps({'devId': device_id(), 'error': error}).encode('utf-8')
    req = urllib.request.Request(
        f'{base_url}/dev/photo/{request_id}/failed',
        data=payload,
        headers=auth_headers({'Content-Type': 'application/json'}),
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=http_timeout()) as resp:
            resp.read()
        print(f'[photo] reported failed requestId={request_id} error={error}', flush=True)
        return True
    except (OSError, urllib.error.URLError, urllib.error.HTTPError) as exc:
        print(f'[photo] failed report error requestId={request_id} err={exc}', file=sys.stderr)
        return False


def handle_photo_request(response: dict | None, result: dict, completed_request_ids: set[str]) -> None:
    if not response:
        return
    photo_request = response.get('data', {}).get('photoRequest')
    if not photo_request:
        return

    request_id = photo_request.get('requestId')
    if not request_id or request_id in completed_request_ids:
        return

    completed_request_ids.add(request_id)
    upload_photo(request_id, result)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_bytes(data)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode('utf-8'))


def save_snapshot_and_json(result: dict) -> None:
    frame = result.get('frame')
    if frame is None:
        print('[snapshot] 跳过: 无可用帧', flush=True)
        return

    dt = datetime.now(LOCAL_TZ)
    day_dir = log_dir() / dt.strftime('%Y-%m-%d') / dt.strftime('%H')
    stem = snapshot_stem(dt)
    jpg_path = day_dir / f'{stem}.jpg'
    json_path = day_dir / f'{stem}.json'

    ok, encoded = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    if not ok:
        print('[snapshot] JPEG 编码失败', file=sys.stderr)
        return

    snapshot_doc = {
        'capturedAt': result.get('capturedAt') or iso_now(),
        'present': bool(result.get('present', False)),
        'state': result.get('state'),
        'stateConfidence': result.get('stateConfidence'),
        'persons': result.get('persons') or [],
        'camera': f'cam{CAMERA}',
        'model': 'yolo11n+face',
        'logDir': str(log_dir()),
    }
    atomic_write_bytes(jpg_path, encoded.tobytes())
    atomic_write_text(json_path, json.dumps(snapshot_doc, ensure_ascii=False, indent=2))
    print(f'[snapshot] saved {jpg_path.name}', flush=True)


def cleanup_old_logs() -> None:
    root = log_dir()
    if not root.exists():
        return

    cutoff = time.time() - retention_seconds()
    for path in sorted(root.rglob('*'), key=lambda p: len(p.parts), reverse=True):
        if not path.is_file():
            continue
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
        except OSError:
            continue

    for path in sorted(root.rglob('*'), key=lambda p: len(p.parts), reverse=True):
        if path.is_dir():
            try:
                path.rmdir()
            except OSError:
                pass


def main() -> int:
    load_smartcore_env()
    log_dir().mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(log_dir(), 0o700)
    except OSError:
        pass

    cap = cv2.VideoCapture(CAMERA)
    if not cap.isOpened():
        print(f'错误: 无法打开摄像头 /dev/video{CAMERA}', file=sys.stderr)
        return 1

    print(f'加载模型: {MODEL}')
    model = YOLO(MODEL)

    missing = missing_model_paths()
    if missing:
        print('错误: 缺少人脸模型文件:', file=sys.stderr)
        for path in missing:
            print(f'  {path}', file=sys.stderr)
        return 1

    print('加载人脸模型: YuNet + SFace')
    face_detector = create_face_detector()
    face_recognizer = create_face_recognizer()
    known_faces = load_known_faces(face_detector, face_recognizer)
    print(f'已加载 {len(known_faces)} 张已知人脸样本')
    print(
        f'协议 v2: 每 {heartbeat_seconds():.0f}s POST /dev/heartbeat, '
        f'每 {snapshot_seconds():.0f}s 本地快照, log={log_dir()}'
    )

    completed_request_ids: set[str] = set()
    heartbeat_failures = 0
    next_heartbeat = time.monotonic()
    next_snapshot = time.monotonic()
    next_cleanup = time.monotonic() + 600

    try:
        while True:
            now = time.monotonic()
            if now < next_heartbeat:
                time.sleep(min(0.5, next_heartbeat - now))
                continue

            start = time.monotonic()
            result = process_round(model, cap, face_detector, face_recognizer, known_faces)
            print(
                f"{time.strftime('%H:%M:%S')} state={result['state']} detail={result['detail']} "
                f"present={result['present']} ratio={result['personRatio']} reason={result['reason']}",
                flush=True,
            )

            if time.monotonic() >= next_snapshot:
                save_snapshot_and_json(result)
                next_snapshot += snapshot_seconds()

            if time.monotonic() >= next_cleanup:
                cleanup_old_logs()
                next_cleanup = time.monotonic() + 600

            response = post_heartbeat(result)
            handle_photo_request(response, result, completed_request_ids)

            if response is not None:
                heartbeat_failures = 0
                next_heartbeat += heartbeat_seconds()
            else:
                heartbeat_failures += 1
                backoff = HEARTBEAT_BACKOFF[min(heartbeat_failures - 1, len(HEARTBEAT_BACKOFF) - 1)]
                next_heartbeat = time.monotonic() + backoff

            elapsed = time.monotonic() - start
            if elapsed > heartbeat_seconds():
                next_heartbeat = time.monotonic() + heartbeat_seconds()
    except KeyboardInterrupt:
        print('\n已退出')
    finally:
        cap.release()

    return 0


if __name__ == '__main__':
    raise SystemExit(main())

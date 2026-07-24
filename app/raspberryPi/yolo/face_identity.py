"""Small OpenCV YuNet + SFace helper for identifying known faces."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


FACE_DETECT_MODEL = Path("models/face_detection_yunet_2023mar.onnx")
FACE_RECOGNITION_MODEL = Path("models/face_recognition_sface_2021dec.onnx")
KNOWN_FACE_DIR = Path("known_faces")
FACE_SCORE_THRESHOLD = 0.9
FACE_NMS_THRESHOLD = 0.3
FACE_TOP_K = 5000
FACE_MATCH_THRESHOLD = 0.363


@dataclass(frozen=True)
class FaceIdentity:
    name: str
    score: float
    box: tuple[int, int, int, int]


@dataclass(frozen=True)
class KnownFace:
    name: str
    feature: np.ndarray


def missing_model_paths() -> list[Path]:
    return [
        path
        for path in (FACE_DETECT_MODEL, FACE_RECOGNITION_MODEL)
        if not path.exists()
    ]


def create_face_detector():
    return cv2.FaceDetectorYN.create(
        str(FACE_DETECT_MODEL),
        "",
        (320, 320),
        FACE_SCORE_THRESHOLD,
        FACE_NMS_THRESHOLD,
        FACE_TOP_K,
    )


def create_face_recognizer():
    return cv2.FaceRecognizerSF.create(str(FACE_RECOGNITION_MODEL), "")


def detect_faces(image: np.ndarray, detector) -> np.ndarray:
    h, w = image.shape[:2]
    detector.setInputSize((w, h))
    _, faces = detector.detect(image)
    if faces is None:
        return np.empty((0, 15), dtype=np.float32)
    return faces


def largest_face(faces: np.ndarray) -> np.ndarray | None:
    if len(faces) == 0:
        return None
    areas = faces[:, 2] * faces[:, 3]
    return faces[int(np.argmax(areas))]


def extract_feature(image: np.ndarray, face: np.ndarray, recognizer) -> np.ndarray:
    aligned = recognizer.alignCrop(image, face)
    return recognizer.feature(aligned)


def iter_known_face_images() -> list[tuple[str, Path]]:
    images: list[tuple[str, Path]] = []
    if not KNOWN_FACE_DIR.exists():
        return images

    suffixes = {".jpg", ".jpeg", ".png", ".webp"}
    for path in sorted(KNOWN_FACE_DIR.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in suffixes:
            continue
        name = path.parent.name if path.parent != KNOWN_FACE_DIR else path.stem
        images.append((name, path))
    return images


def load_known_faces(detector, recognizer) -> list[KnownFace]:
    known: list[KnownFace] = []
    for name, path in iter_known_face_images():
        image = cv2.imread(str(path))
        if image is None:
            print(f"跳过无法读取的人脸样本: {path}")
            continue

        face = largest_face(detect_faces(image, detector))
        if face is None:
            print(f"跳过未检测到人脸的样本: {path}")
            continue

        known.append(KnownFace(name=name, feature=extract_feature(image, face, recognizer)))

    return known


def match_face(
    image: np.ndarray,
    detector,
    recognizer,
    known_faces: list[KnownFace],
) -> FaceIdentity | None:
    if not known_faces:
        return None

    face = largest_face(detect_faces(image, detector))
    if face is None:
        return None

    query_feature = extract_feature(image, face, recognizer)
    best_name = "unknown"
    best_score = -1.0

    for known in known_faces:
        score = recognizer.match(
            query_feature,
            known.feature,
            cv2.FaceRecognizerSF_FR_COSINE,
        )
        if score > best_score:
            best_score = float(score)
            best_name = known.name

    x, y, w, h = face[:4].astype(int).tolist()
    if best_score < FACE_MATCH_THRESHOLD:
        best_name = "unknown"

    return FaceIdentity(name=best_name, score=best_score, box=(x, y, w, h))


def draw_identity(image: np.ndarray, identity: FaceIdentity | None) -> np.ndarray:
    output = image.copy()
    if identity is None:
        return output

    x, y, w, h = identity.box
    label = f"{identity.name} {identity.score:.2f}"
    color = (0, 180, 0) if identity.name != "unknown" else (0, 165, 255)
    cv2.rectangle(output, (x, y), (x + w, y + h), color, 2)
    cv2.putText(
        output,
        label,
        (x, max(20, y - 8)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        color,
        2,
        cv2.LINE_AA,
    )
    return output

#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_DIR="${ROOT}/models"

mkdir -p "${MODEL_DIR}"

curl --fail --location --retry 3 \
  --output "${MODEL_DIR}/face_detection_yunet_2023mar.onnx" \
  "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
curl --fail --location --retry 3 \
  --output "${MODEL_DIR}/face_recognition_sface_2021dec.onnx" \
  "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"

# Ultralytics downloads this official weight on first use if it is absent.
cd "${ROOT}"
"${ROOT}/.venv/bin/python" -c 'from ultralytics import YOLO; YOLO("yolo11n.pt")'

cd "${MODEL_DIR}"
sha256sum --check SHA256SUMS

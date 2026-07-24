#!/usr/bin/env python3
"""最小 OpenCV 拍照脚本。"""

import sys
from pathlib import Path

import cv2

CAMERA = 0
OUTPUT = Path("captures/test.jpg")


def open_camera(index: int):
    cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
    if cap.isOpened():
        return cap
    cap.release()
    return cv2.VideoCapture(index)


def main() -> int:
    cap = open_camera(CAMERA)
    if not cap.isOpened():
        print(f"无法打开摄像头 /dev/video{CAMERA}", file=sys.stderr)
        return 1

    for _ in range(5):
        cap.read()

    ok, frame = cap.read()
    cap.release()
    if not ok:
        print("读取画面失败", file=sys.stderr)
        return 1

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(OUTPUT), frame)
    print(f"已保存: {OUTPUT.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

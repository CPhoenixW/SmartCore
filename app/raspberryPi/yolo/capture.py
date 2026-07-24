#!/usr/bin/env python3
"""最小 OpenCV 拍摄脚本：打开摄像头，按空格拍照，按 q 退出。"""

import os
import sys
from pathlib import Path

import cv2

CAMERA = 0
OUTPUT = Path("capture.jpg")


def camera_hint(device: int) -> None:
    dev = Path(f"/dev/video{device}")
    if not dev.exists():
        print(f"设备 {dev} 不存在，请检查摄像头是否已连接。", file=sys.stderr)
        return

    if not os.access(dev, os.R_OK | os.W_OK):
        print(f"无权限访问 {dev}（当前用户不在 video 组）。", file=sys.stderr)
        print("修复：sudo usermod -aG video $USER  然后重新登录或重启。", file=sys.stderr)


def open_camera(device: int) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(device)
    if cap.isOpened():
        return cap

    cap.release()
    cap = cv2.VideoCapture(f"/dev/video{device}")
    return cap


def main() -> int:
    cap = open_camera(CAMERA)
    if not cap.isOpened():
        print(f"无法打开摄像头 {CAMERA}", file=sys.stderr)
        camera_hint(CAMERA)
        return 1

    print("空格：拍照并保存  |  q：退出")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("读取画面失败", file=sys.stderr)
                return 1

            cv2.imshow("camera", frame)
            key = cv2.waitKey(1) & 0xFF

            if key == ord("q"):
                break
            if key == ord(" "):
                cv2.imwrite(str(OUTPUT), frame)
                print(f"已保存 {OUTPUT}")
    finally:
        cap.release()
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

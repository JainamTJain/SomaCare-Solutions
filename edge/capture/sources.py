"""Open a webcam or a video file. Callers must discard each frame."""

from __future__ import annotations

from pathlib import Path


def frames_from_webcam(index: int = 0):
    import cv2

    capture = cv2.VideoCapture(index)
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            yield frame
    finally:
        capture.release()


def frames_from_file(path: Path):
    import cv2

    capture = cv2.VideoCapture(str(path))
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            yield frame
    finally:
        capture.release()

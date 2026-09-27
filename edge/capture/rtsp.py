"""Read one local RTSP stream from a consumer infrared baby monitor.

OpenCV opens the video track only. The microphone is not opened, and this
module never writes a frame. Cloud hosts are refused so a camera that still
points at a vendor server is not treated as the home feed.
"""

from __future__ import annotations

CLOUD_HOSTS = ("tplinkcloud", "tapo.com", "amazonaws", "googleapis", "cloudfront")


def assert_local_rtsp(url: str) -> str:
    cleaned = (url or "").strip()
    if not cleaned.startswith(("rtsp://", "rtsps://")):
        raise ValueError("baby monitor url must be a local rtsp address")
    lowered = cleaned.lower()
    if any(host in lowered for host in CLOUD_HOSTS):
        raise ValueError("baby monitor must stay on the local network")
    return cleaned


class RtspBabyMonitor:
    """One camera. `opener` is for tests; production uses OpenCV."""

    def __init__(self, url: str, opener=None):
        self.url = assert_local_rtsp(url)
        self._opener = opener
        self._cap = None

    def read(self):
        """Return one video frame, or None. The caller discards it."""
        if self._cap is None:
            if self._opener is not None:
                self._cap = self._opener(self.url)
            else:
                import cv2

                # CAP_FFMPEG reads video. It does not open the audio track.
                self._cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
        ok, frame = self._cap.read()
        if not ok:
            return None
        return frame

    def close(self) -> None:
        if self._cap is not None and hasattr(self._cap, "release"):
            self._cap.release()
        self._cap = None

"""Visualization sinks for the traffic app."""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from urbAIn_traffic_app.core.draw_core import draw_overlays_on_frame
from urbAIn_testing_platform.visualization_bus import ComposedView
from urbAIn_testing_platform.visualization_sinks import MP4Sink, render_composed_view

logger = logging.getLogger("urbAIn_traffic_app.visualization.sinks")

__all__ = ["MP4Sink", "WebStreamSink", "render_composed_view"]


class WebStreamSink:
    """Keeps the latest JPEG frame for MJPEG streaming to the web UI."""

    def __init__(self, *, jpeg_quality: int = 80, max_fps: float = 15.0) -> None:
        self._quality = int(jpeg_quality)
        self._min_interval = 1.0 / max(max_fps, 1.0)
        self._lock = threading.Lock()
        self._jpeg: Optional[bytes] = None
        self._last_push = 0.0

    def __call__(self, view: ComposedView) -> None:
        now = time.monotonic()
        with self._lock:
            if now - self._last_push < self._min_interval:
                return
            self._last_push = now
        img = render_composed_view(view)
        ok, buf = cv2.imencode(
            ".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), self._quality],
        )
        if not ok:
            return
        with self._lock:
            self._jpeg = buf.tobytes()

    def get_jpeg(self) -> Optional[bytes]:
        with self._lock:
            return self._jpeg

    def close(self) -> None:
        with self._lock:
            self._jpeg = None


class ImageSink:
    """Write a single annotated image to disk."""

    def __init__(self, output_path: Path) -> None:
        self._path = Path(output_path)

    def save(self, frame: np.ndarray, overlays: list[tuple[str, dict]]) -> Path:
        img = draw_overlays_on_frame(frame, overlays)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(self._path), img)
        return self._path

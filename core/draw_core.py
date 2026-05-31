"""Unified bbox drawing (Vision Insight palette, BGR for OpenCV)."""
from __future__ import annotations

from typing import Optional

import cv2
import numpy as np

VEHICLE_COLOR = (0, 220, 0)
PLATE_COLOR = (255, 220, 0)
TEXT_COLOR = (0, 255, 255)
TEXT_BG = (0, 0, 0)


def norm_to_px(bbox: dict, w: int, h: int) -> tuple[int, int, int, int]:
    x1 = int(round(max(0.0, bbox["x"]) * w))
    y1 = int(round(max(0.0, bbox["y"]) * h))
    x2 = int(round(min(1.0, bbox["x"] + bbox["w"]) * w))
    y2 = int(round(min(1.0, bbox["y"] + bbox["h"]) * h))
    return x1, y1, max(x1 + 1, x2), max(y1 + 1, y2)


def draw_c15_payload(frame: np.ndarray, payload: dict) -> None:
    """Draw C15 vehicle/plate boxes and label onto ``frame`` in place."""
    h, w = frame.shape[:2]
    vb = payload.get("vehicle_bbox")
    if not isinstance(vb, dict):
        return
    vx1, vy1, vx2, vy2 = norm_to_px(vb, w, h)
    cv2.rectangle(frame, (vx1, vy1), (vx2, vy2), VEHICLE_COLOR, 2)

    pb = payload.get("plate_bbox")
    if isinstance(pb, dict):
        px1, py1, px2, py2 = norm_to_px(pb, w, h)
        cv2.rectangle(frame, (px1, py1), (px2, py2), PLATE_COLOR, 2)

    text = str(payload.get("plate_text") or "").strip()
    if not text:
        return
    conf = float(payload.get("plate_confidence") or 0.0)
    label = f"{text} ({conf:.2f})" if conf > 0 else text

    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = max(0.5, min(1.2, w / 1920.0))
    thick = max(1, int(round(scale * 2)))
    (tw, th), bl = cv2.getTextSize(label, font, scale, thick)
    tx = vx1
    ty = max(th + bl + 4, vy1 - 8)
    if ty - th - bl < 0:
        ty = vy2 + th + bl + 8
    cv2.rectangle(frame, (tx, ty - th - bl - 4), (tx + tw + 8, ty + 4), TEXT_BG, -1)
    cv2.putText(frame, label, (tx + 4, ty), font, scale, TEXT_COLOR, thick, cv2.LINE_AA)


def draw_overlays_on_frame(
    frame: np.ndarray,
    overlays: list[tuple[str, dict]],
) -> np.ndarray:
    """Return a copy of ``frame`` with all pipeline overlays drawn."""
    out = frame.copy()
    for pipeline_id, payload in overlays:
        if pipeline_id == "c15":
            draw_c15_payload(out, payload)
    return out

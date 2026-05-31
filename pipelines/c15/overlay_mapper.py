"""Map C15 native outputs to traffic-app contracts."""
from __future__ import annotations

from c15_lpr_pipeline import C15FrameOverlay, C15LPRResult

from urbAIn_traffic_app.core.pipeline_protocol import DetectionEvent, OverlayPayload


def overlay_from_c15(overlay: C15FrameOverlay) -> OverlayPayload:
    return OverlayPayload(
        pipeline_id="c15",
        camera_id=overlay.camera_id,
        sequence_number=int(overlay.sequence_number),
        payload={
            "vehicle_bbox": overlay.vehicle_bbox,
            "plate_bbox": overlay.plate_bbox,
            "plate_text": overlay.plate_text,
            "plate_confidence": overlay.plate_confidence,
            "track_id": overlay.track_id,
            "track_state": overlay.track_state,
        },
    )


def detection_from_c15(result: C15LPRResult) -> DetectionEvent:
    return DetectionEvent(
        pipeline_id="c15",
        camera_id=result.camera_id,
        label=result.plate_text or "",
        confidence=float(result.confidence),
        timestamp=result.timestamp,
        sequence_number=None,
        metadata={
            "track_id": result.track_id,
            "country_code": result.country_code,
            "is_track_final": result.is_track_final,
            "is_track_snapshot": result.is_track_snapshot,
            "enhanced": result.enhanced,
            "frame_id": result.frame_id,
            "object_id": result.object_id,
        },
    )

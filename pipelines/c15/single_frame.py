"""Offline still-image processing for C15."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import cv2

from m01_frame_preprocessor.types import Frame

from urbAIn_traffic_app.pipelines.c15._runtime import c15

from urbAIn_traffic_app.core.app_status import emit_status
from urbAIn_traffic_app.core.pipeline_protocol import RunContext
from urbAIn_traffic_app.core.run_store import RunStore
from urbAIn_traffic_app.core.visualization.sinks import ImageSink
from urbAIn_traffic_app.pipelines.c15.config_builder import build_config_for_source
from urbAIn_traffic_app.pipelines.c15.overlay_mapper import detection_from_c15


def _build_frame_from_image(image_path: Path, camera_id: str = "cam01") -> Frame:
    bgr = cv2.imread(str(image_path))
    if bgr is None:
        raise ValueError(f"could not read image: {image_path}")
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return Frame(
        frame_id=str(uuid.uuid4()),
        camera_id=camera_id,
        timestamp=ts,
        image=rgb,
        image_resized=rgb,
        width=w,
        height=h,
        sequence_number=1,
        is_gap=False,
        metadata={},
        letterbox=None,
    )


async def process_offline_image(
    ctx: RunContext,
    *,
    project_root: Path,
    store: RunStore,
) -> Path:
    if ctx.source.file_path is None:
        raise ValueError("offline image requires file_path")

    emit_status(
        ctx.on_status,
        phase="loading",
        message="Preparando configuración…",
        detail=str(ctx.source.file_path),
    )

    config_path = build_config_for_source(
        ctx.source,
        project_root=project_root,
        run_output_dir=ctx.output_dir,
    )

    emit_status(
        ctx.on_status,
        phase="loading",
        message="Cargando modelos C15…",
    )

    c15_mod = c15()
    config = c15_mod.load_config(str(config_path))
    output_queue = __import__("asyncio").Queue(maxsize=0)
    pipeline = c15_mod.C15LPRPipeline(config, output_queue)
    frame = _build_frame_from_image(ctx.source.file_path)

    emit_status(
        ctx.on_status,
        phase="processing",
        message="Ejecutando detección y OCR…",
        detail=f"{frame.width}×{frame.height} px",
    )

    outputs = pipeline.process_frame_sync("cam01", frame)

    overlays: list[tuple[str, dict]] = []
    for item in outputs:
        if isinstance(item, c15_mod.C15FrameOverlay):
            overlays.append(("c15", {
                "vehicle_bbox": item.vehicle_bbox,
                "plate_bbox": item.plate_bbox,
                "plate_text": item.plate_text,
                "plate_confidence": item.plate_confidence,
            }))
            store.write_overlay({
                "camera_id": item.camera_id,
                "sequence_number": item.sequence_number,
                "vehicle_bbox": item.vehicle_bbox,
                "plate_bbox": item.plate_bbox,
                "plate_text": item.plate_text,
                "plate_confidence": item.plate_confidence,
            })
        elif isinstance(item, c15_mod.C15LPRResult):
            event = detection_from_c15(item)
            store.write_detection(
                event,
                crop_b64=item.enhanced_crop_b64,
                extra={"is_track_final": item.is_track_final},
            )
            if ctx.on_detection:
                ctx.on_detection(event)

    emit_status(
        ctx.on_status,
        phase="processing",
        message="Guardando imagen anotada y logs…",
    )

    stem = ctx.source.file_path.stem
    out_path = ctx.output_dir / f"{stem}_annotated.jpg"
    sink = ImageSink(out_path)
    bgr = cv2.cvtColor(frame.image, cv2.COLOR_RGB2BGR)
    sink.save(bgr, overlays)

    return out_path

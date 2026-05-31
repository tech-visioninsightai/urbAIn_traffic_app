"""C15 LPR pipeline adapter for the traffic app."""
from __future__ import annotations

import asyncio
import logging
import shutil
import time
from pathlib import Path
from typing import Any, Optional

from c15_lpr_pipeline import (
    C15FrameOverlay,
    C15LPRPipeline,
    C15LPRResult,
    C15PipelineOutput,
    load_config,
)
from urbAIn_testing_platform.annotated_video import build_annotated_video_from_recorded
from urbAIn_testing_platform.frame_recorder import FrameRecorder
from urbAIn_testing_platform.visualization_bus import VisualizationBus
from urbAIn_testing_platform.visualization_sinks import MP4Sink

from urbAIn_traffic_app.core.app_status import emit_status
from urbAIn_traffic_app.core.pipeline_protocol import (
    MediaSource,
    RunContext,
    RunMode,
)
from urbAIn_traffic_app.core.run_store import RunStore
from urbAIn_traffic_app.core.visualization.sinks import WebStreamSink
from urbAIn_traffic_app.pipelines.c15.config_builder import build_config_for_source
from urbAIn_traffic_app.pipelines.c15.overlay_mapper import detection_from_c15, overlay_from_c15
from urbAIn_traffic_app.pipelines.c15.single_frame import process_offline_image

logger = logging.getLogger(__name__)

METRICS_EVERY_SEC = 5.0


class C15PipelineAdapter:
    pipeline_id = "c15"
    display_name = "C15 · LPR"

    def __init__(self) -> None:
        self._pipeline: Optional[C15LPRPipeline] = None
        self._output_queue: Optional[asyncio.Queue[C15PipelineOutput]] = None
        self._vis_bus: Optional[VisualizationBus] = None
        self._vis_sinks: list[Any] = []
        self._vis_frame_queue: Optional[asyncio.Queue] = None
        self._vis_drainer: Optional[asyncio.Task] = None
        self._main_task: Optional[asyncio.Task] = None
        self._stop_event: Optional[asyncio.Event] = None
        self._store: Optional[RunStore] = None
        self._web_sink: Optional[WebStreamSink] = None
        self._started_at = 0.0
        self._ctx: Optional[RunContext] = None
        self._project_root: Optional[Path] = None
        self._offline_stop_scheduled = False
        self._frame_recorder: Optional[FrameRecorder] = None

    def build_config_path(self, ctx: RunContext) -> str:
        if self._project_root is None:
            raise RuntimeError("project_root not set")
        path = build_config_for_source(
            ctx.source,
            project_root=self._project_root,
            run_output_dir=ctx.output_dir,
        )
        return str(path)

    async def start(self, ctx: RunContext) -> None:
        if self._main_task is not None:
            await self.stop()

        self._ctx = ctx
        self._started_at = time.monotonic()
        self._stop_event = asyncio.Event()
        is_online = ctx.mode == RunMode.ONLINE
        is_offline_video = ctx.mode == RunMode.OFFLINE_VIDEO

        if ctx.mode == RunMode.OFFLINE_IMAGE:
            self._main_task = asyncio.create_task(self._run_offline_image(ctx))
            return

        emit_status(
            ctx.on_status,
            phase="loading",
            message="Cargando configuración C15…",
            detail=str(ctx.source.file_path or ctx.source.camera_uri or ""),
        )

        config_path = self.build_config_path(ctx)
        config = load_config(config_path)
        self._output_queue = asyncio.Queue(maxsize=config.output.queue_maxsize)
        self._frame_recorder = None
        if config.pipeline.frame_overlay.capture_processed_frames:
            fps = float(config.cameras[0].fps_target or 15)
            self._frame_recorder = FrameRecorder(ctx.output_dir, fps=fps)

        self._pipeline = C15LPRPipeline(
            config,
            self._output_queue,
            frame_sink=self._frame_recorder,
        )

        self._vis_bus = None
        self._vis_sinks = []
        self._vis_frame_queue = None
        self._web_sink = WebStreamSink() if is_online else None
        # Offline: one MP4 via FrameRecorder + post mux (no live vis bus / MP4Sink).
        if config.pipeline.frame_overlay.enabled and not is_offline_video:
            self._vis_bus = VisualizationBus(window_frames=30)
            self._vis_frame_queue = asyncio.Queue(maxsize=8)
            self._pipeline.add_frame_subscriber(self._vis_frame_queue)
            rec_fps = float(config.cameras[0].fps_target or 15)
            mp4_sink = MP4Sink(ctx.output_dir, fps=rec_fps)
            self._vis_bus.add_sink(mp4_sink)
            self._vis_sinks.append(mp4_sink)
            if is_online and self._web_sink is not None:
                self._vis_bus.add_sink(self._web_sink)
                self._vis_sinks.append(self._web_sink)

        emit_status(
            ctx.on_status,
            phase="loading",
            message="Iniciando inferencia…",
            detail="M01 → M15 → M02 → M06 → M05",
        )

        await self._pipeline.start()

        if self._vis_bus is not None and self._vis_frame_queue is not None:
            self._vis_drainer = asyncio.create_task(
                self._drain_frames(self._vis_frame_queue, self._vis_bus, self._stop_event),
            )

        self._main_task = asyncio.create_task(self._drain_outputs(ctx))

        if ctx.mode == RunMode.OFFLINE_VIDEO:
            self._offline_stop_scheduled = False
            msg = "Procesando vídeo offline…"
            detail = (
                f"Archivo: {ctx.source.file_path.name if ctx.source.file_path else '?'}\n"
                "Una sola pasada por el vídeo. Al terminar se guardará en la carpeta de salida."
            )
        else:
            msg = "Transmisión en vivo activa"
            detail = str(ctx.source.camera_uri or "")

        emit_status(
            ctx.on_status,
            phase="processing",
            state="running",
            message=msg,
            detail=detail,
            mode=ctx.mode.value,
        )

    async def stop(self) -> None:
        completed = False
        if self._stop_event is not None:
            self._stop_event.set()

        if self._vis_drainer is not None:
            self._vis_drainer.cancel()
            try:
                await self._vis_drainer
            except asyncio.CancelledError:
                pass
            self._vis_drainer = None

        if self._main_task is not None:
            self._main_task.cancel()
            try:
                await self._main_task
            except asyncio.CancelledError:
                pass
            self._main_task = None

        if self._pipeline is not None:
            await self._pipeline.stop()
            if self._frame_recorder is not None:
                try:
                    self._frame_recorder.close()
                except Exception:
                    logger.warning("frame recorder close failed", exc_info=True)
                self._frame_recorder = None
            if self._vis_bus is not None:
                self._vis_bus.flush()
            for sink in self._vis_sinks:
                try:
                    sink.close()
                except Exception:
                    logger.warning("sink close failed", exc_info=True)
            self._finalize_annotated_video()
            if self._ctx and self._ctx.mode in (
                RunMode.OFFLINE_VIDEO,
                RunMode.OFFLINE_IMAGE,
                RunMode.ONLINE,
            ):
                artifacts = self._list_artifacts(self._ctx.output_dir)
                emit_status(
                    self._ctx.on_status,
                    phase="completed",
                    state="completed",
                    message="Procesamiento finalizado",
                    detail=f"Salida: {self._ctx.output_dir}",
                    output_dir=str(self._ctx.output_dir),
                    artifacts=artifacts,
                )
                completed = True
            self._pipeline = None

        self._vis_bus = None
        self._vis_sinks = []
        self._stop_event = None

        if self._ctx and self._ctx.on_status and not completed:
            emit_status(
                self._ctx.on_status,
                phase="idle",
                state="idle",
                message="Sesión detenida",
            )

    def _list_artifacts(self, out_dir: Path) -> list[str]:
        names = []
        for name in (
            "annotated.mp4",
            "live_annotated_cam01.mp4",
            "detections.jsonl",
            "overlays.jsonl",
            "tracks.json",
            "metrics.jsonl",
        ):
            if (out_dir / name).is_file():
                names.append(name)
        crops = out_dir / "crops"
        if crops.is_dir() and any(crops.iterdir()):
            names.append("crops/")
        for p in out_dir.glob("*_annotated.jpg"):
            names.append(p.name)
        return names

    @property
    def web_sink(self) -> Optional[WebStreamSink]:
        return self._web_sink

    def attach_project_root(self, root: Path) -> None:
        self._project_root = root

    def attach_store(self, store: RunStore) -> None:
        self._store = store

    async def _run_offline_image(self, ctx: RunContext) -> None:
        if self._project_root is None or self._store is None:
            raise RuntimeError("adapter not fully wired")
        emit_status(
            ctx.on_status,
            phase="processing",
            state="running",
            message="Procesando imagen offline…",
            detail=str(ctx.source.file_path or ""),
            mode="offline_image",
        )
        try:
            out = await process_offline_image(
                ctx,
                project_root=self._project_root,
                store=self._store,
            )
            artifacts = self._list_artifacts(ctx.output_dir)
            emit_status(
                ctx.on_status,
                phase="completed",
                state="completed",
                message="Imagen procesada",
                detail=f"Salida: {ctx.output_dir}",
                output_dir=str(ctx.output_dir),
                artifacts=artifacts,
                annotated_image=str(out),
            )
        except Exception as exc:
            logger.exception("offline image failed")
            emit_status(
                ctx.on_status,
                phase="error",
                state="error",
                message="Error al procesar la imagen",
                detail=str(exc),
            )

    def _offline_eof_reached(self) -> bool:
        if self._pipeline is None:
            return False
        cam = next(iter(self._pipeline.get_metrics().values()), {})
        if not cam.get("m01_playback_finished"):
            return False
        recv = int(cam.get("frames_received", 0))
        proc = int(cam.get("frames_processed", 0))
        return recv > 0 and proc >= recv

    async def _drain_frames(
        self,
        q: asyncio.Queue,
        bus: VisualizationBus,
        stop: asyncio.Event,
    ) -> None:
        while not stop.is_set():
            try:
                frame = await asyncio.wait_for(q.get(), timeout=0.25)
            except asyncio.TimeoutError:
                continue
            bus.ingest_frame(getattr(frame, "camera_id", "?"), frame)

    async def _drain_outputs(self, ctx: RunContext) -> None:
        assert self._output_queue is not None
        assert self._pipeline is not None
        assert self._stop_event is not None
        last_metrics = time.monotonic()

        while not self._stop_event.is_set():
            try:
                result = await asyncio.wait_for(self._output_queue.get(), timeout=0.25)
            except asyncio.TimeoutError:
                result = None

            if result is not None:
                await self._handle_output(result, ctx)

            if (
                not self._offline_stop_scheduled
                and ctx.mode == RunMode.OFFLINE_VIDEO
                and self._offline_eof_reached()
            ):
                self._offline_stop_scheduled = True
                emit_status(
                    ctx.on_status,
                    phase="muxing",
                    message="Vídeo terminado, guardando resultados…",
                    detail=str(ctx.output_dir),
                )
                asyncio.create_task(self.stop())

            now = time.monotonic()
            if self._store and now - last_metrics >= METRICS_EVERY_SEC:
                self._store.write_metrics(
                    self._pipeline.get_metrics(),
                    now - self._started_at,
                )
                last_metrics = now
                if ctx.on_metrics:
                    ctx.on_metrics(self._pipeline.get_metrics())

    async def _handle_output(self, result: C15PipelineOutput, ctx: RunContext) -> None:
        if isinstance(result, C15FrameOverlay):
            if self._store:
                self._store.write_overlay({
                    "camera_id": result.camera_id,
                    "frame_id": result.frame_id,
                    "timestamp": result.timestamp,
                    "sequence_number": result.sequence_number,
                    "video_position_sec": result.video_position_sec,
                    "media_time_sec": result.media_time_sec,
                    "track_state": result.track_state,
                    "object_id": result.object_id,
                    "track_id": result.track_id,
                    "vehicle_bbox": result.vehicle_bbox,
                    "plate_bbox": result.plate_bbox,
                    "plate_text": result.plate_text,
                    "plate_confidence": result.plate_confidence,
                })
            if self._vis_bus is not None:
                ov = overlay_from_c15(result)
                self._vis_bus.ingest_overlay(
                    ov.pipeline_id,
                    ov.camera_id,
                    ov.sequence_number,
                    ov.payload,
                )
            return

        if not isinstance(result, C15LPRResult):
            return

        event = detection_from_c15(result)
        should_log = (
            result.is_track_final
            or result.is_track_snapshot
            or (not result.is_track_final and not result.is_track_snapshot)
        )
        if should_log and self._store:
            self._store.write_detection(
                event,
                crop_b64=result.enhanced_crop_b64 if result.is_track_final else None,
                extra={
                    "is_track_final": result.is_track_final,
                    "is_track_snapshot": result.is_track_snapshot,
                    "country_code": result.country_code,
                },
            )
        if result.is_track_final and result.track_id and self._store:
            self._store.upsert_track(result.track_id, {
                "camera_id": result.camera_id,
                "plate_text": result.plate_text,
                "confidence": result.confidence,
                "timestamp": result.timestamp,
            })
        if ctx.on_detection and (result.is_track_final or not result.is_track_snapshot):
            ctx.on_detection(event)

    def _finalize_annotated_video(self) -> None:
        if self._ctx is None:
            return
        out_dir = self._ctx.output_dir
        emit_status(
            self._ctx.on_status,
            phase="muxing",
            message="Generando vídeo anotado…",
            detail=str(out_dir),
        )
        annotated = out_dir / "annotated.mp4"
        mp4_sinks = [s for s in self._vis_sinks if isinstance(s, MP4Sink)]
        if mp4_sinks:
            live = mp4_sinks[0].path_for("cam01")
            if live.is_file():
                shutil.copy2(live, annotated)
                return
        processed = out_dir / "processed_cam01.mp4"
        overlays = out_dir / "overlays.jsonl"
        if processed.is_file() and processed.stat().st_size < 1024:
            logger.warning("processed video too small or empty: %s", processed)
            return
        if processed.is_file() and overlays.is_file():
            try:
                ok = build_annotated_video_from_recorded(
                    processed,
                    overlays,
                    annotated,
                )
                if not ok:
                    logger.warning(
                        "annotated mux failed; leaving %s as processed-only artefact",
                        processed,
                    )
            except Exception:
                logger.warning("post mux failed", exc_info=True)

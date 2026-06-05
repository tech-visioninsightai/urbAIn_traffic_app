"""Pipeline session lifecycle (asyncio in dedicated thread)."""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from urbAIn_traffic_app.core.app_status import emit_status
from urbAIn_traffic_app.core.camera_live import prepare_online_camera
from urbAIn_traffic_app.core.pipeline_protocol import (
    DetectionEvent,
    MediaSource,
    RunContext,
    RunMode,
)
from urbAIn_traffic_app.core.pipeline_registry import registry
from urbAIn_traffic_app.core.run_store import RunStore
from urbAIn_traffic_app.core.visualization.sinks import WebStreamSink

from urbAIn_traffic_app.backend.paddle_preflight import check_paddle_ocr_ready
from urbAIn_traffic_app.pipelines.c15.adapter import C15PipelineAdapter

logger = logging.getLogger(__name__)


@dataclass
class SessionState:
    running: bool = False
    mode: Optional[str] = None
    pipeline_id: Optional[str] = None
    output_dir: Optional[str] = None
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    total_detections: int = 0
    metrics: dict = field(default_factory=dict)
    last_error: Optional[str] = None
    phase: str = "idle"
    message: str = "Inactivo"
    detail: str = ""
    progress: dict = field(default_factory=dict)


def _session_uptime(state: SessionState) -> Optional[float]:
    if not state.started_at:
        return None
    end = state.finished_at
    if end is None and state.running:
        end = time.monotonic()
    if end is None:
        return None
    return round(end - state.started_at, 1)


class SessionController:
    _start_lock = threading.Lock()

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.runs_root = project_root / "urbAIn_traffic_app" / "runs"
        self.runs_root.mkdir(parents=True, exist_ok=True)
        self.state = SessionState()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._adapter: Optional[C15PipelineAdapter] = None
        self._store: Optional[RunStore] = None
        self._event_hub = None
        self._static_jpeg: Optional[bytes] = None
        self._last_progress_frames: int = -1
        self._last_progress_msg: str = ""

    def set_event_hub(self, hub) -> None:
        self._event_hub = hub

    @property
    def web_sink(self) -> Optional[WebStreamSink]:
        if self._adapter is not None:
            return self._adapter.web_sink
        return None

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is not None:
            return self._loop

        ready = threading.Event()

        def _run() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            ready.set()
            loop.run_forever()

        self._thread = threading.Thread(target=_run, name="traffic-app-async", daemon=True)
        self._thread.start()
        ready.wait(timeout=5.0)
        if self._loop is None:
            raise RuntimeError("async loop failed to start")
        return self._loop

    def _run_coro(self, coro):
        loop = self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=120.0)

    def _new_run_dir(self, pipeline_id: str, mode: RunMode) -> Path:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = self.runs_root / f"{ts}_{pipeline_id}_{mode.value}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def start_session(
        self,
        *,
        pipeline_id: str,
        mode: str,
        camera_uri: Optional[str] = None,
        file_path: Optional[str] = None,
    ) -> dict[str, Any]:
        with self._start_lock:
            return self._start_session_locked(
                pipeline_id=pipeline_id,
                mode=mode,
                camera_uri=camera_uri,
                file_path=file_path,
            )

    def _start_session_locked(
        self,
        *,
        pipeline_id: str,
        mode: str,
        camera_uri: Optional[str] = None,
        file_path: Optional[str] = None,
    ) -> dict[str, Any]:
        if self.state.running:
            self.stop_session()

        run_mode = RunMode(mode)
        if run_mode in (RunMode.OFFLINE_VIDEO, RunMode.OFFLINE_IMAGE):
            if not file_path:
                raise ValueError("Falta file_path para el modo offline")
            media = Path(file_path)
            if not media.is_file():
                raise FileNotFoundError(f"Archivo no encontrado: {file_path}")

        if pipeline_id == "c15":
            paddle_ok, paddle_msg = check_paddle_ocr_ready()
            if not paddle_ok:
                raise ValueError(paddle_msg)

        connect_log: list[str] = []
        if run_mode == RunMode.ONLINE:
            try:
                camera_uri, connect_log = prepare_online_camera(camera_uri)
            except ConnectionError as exc:
                raise ValueError(str(exc)) from exc

        source = MediaSource(
            mode=run_mode,
            camera_uri=camera_uri,
            file_path=Path(file_path) if file_path else None,
        )
        out_dir = self._new_run_dir(pipeline_id, run_mode)
        store = RunStore(out_dir, project_root=self.project_root)
        store.reset()

        adapter = registry.create(pipeline_id)
        if isinstance(adapter, C15PipelineAdapter):
            adapter.attach_project_root(self.project_root)
            adapter.attach_store(store)

        def on_detection(event: DetectionEvent) -> None:
            self.state.total_detections += 1
            if self._event_hub:
                self._event_hub.publish({
                    "type": "detection",
                    "label": event.label,
                    "confidence": event.confidence,
                    "camera_id": event.camera_id,
                    "timestamp": event.timestamp,
                })

        def on_status(payload: dict) -> None:
            phase = str(payload.get("phase") or payload.get("state") or self.state.phase)
            self.state.phase = phase
            if "message" in payload:
                self.state.message = str(payload["message"])
            if "detail" in payload:
                self.state.detail = str(payload["detail"])
            if "progress" in payload and isinstance(payload["progress"], dict):
                self.state.progress = payload["progress"]
            if payload.get("state") in ("completed", "error") or payload.get("phase") in (
                "completed",
                "error",
            ):
                self.state.running = False
                if self.state.started_at and self.state.finished_at is None:
                    self.state.finished_at = time.monotonic()
            if payload.get("state") == "error" or payload.get("phase") == "error":
                self.state.last_error = str(payload.get("message") or "")
            if self._event_hub:
                out = dict(payload)
                out["uptime_sec"] = _session_uptime(self.state)
                out["uptime_frozen"] = (
                    not self.state.running and self.state.finished_at is not None
                )
                out["total_detections"] = self.state.total_detections
                out.setdefault("progress", self.state.progress)
                self._event_hub.publish({"type": "status", **out})

        def _metrics_detail(cam: dict) -> str:
            lines = [
                f"Frames proc.: {cam.get('frames_processed', 0)} · "
                f"recibidos: {cam.get('frames_received', 0)} · "
                f"matrículas: {self.state.total_detections}",
            ]
            m01_drop = int(cam.get("m01_frames_dropped") or 0)
            pipe_drop = int(cam.get("frames_dropped") or 0)
            failed = int(cam.get("frames_failed") or 0)
            if m01_drop or pipe_drop:
                lines.append(
                    f"Cola saturada — descartados decodificador: {m01_drop}, "
                    f"pipeline: {pipe_drop}"
                )
            if failed:
                lines.append(
                    f"Frames con error de inferencia: {failed} "
                    "(posible falta de memoria)"
                )
            return "\n".join(lines)

        def on_metrics(metrics: dict) -> None:
            self.state.metrics = metrics
            if not self.state.running:
                return
            cam = next(iter(metrics.values()), {}) if metrics else {}
            self.state.progress = {
                "frames_processed": cam.get("frames_processed", 0),
                "frames_received": cam.get("frames_received", 0),
                "plates_emitted": cam.get("plates_emitted", 0),
                "tracks_active": cam.get("tracks_active", 0),
                "m01_frames_dropped": cam.get("m01_frames_dropped", 0),
                "frames_dropped": cam.get("frames_dropped", 0),
            }
            if not self._event_hub:
                return
            if self.state.mode not in ("offline_video", "online", "offline_image"):
                return

            m01_drop = int(cam.get("m01_frames_dropped") or 0)
            pipe_drop = int(cam.get("frames_dropped") or 0)
            failed = int(cam.get("frames_failed") or 0)
            msg = "Procesando…"
            if failed:
                msg = "Procesando con errores (revisar memoria/GPU)…"
            elif m01_drop or pipe_drop:
                msg = "Procesando (cola saturada, se descartan frames)…"

            frames_processed = int(cam.get("frames_processed", 0))
            detail = _metrics_detail(cam)
            uptime = _session_uptime(self.state)
            payload_base = {
                "detail": detail,
                "progress": self.state.progress,
                "uptime_sec": uptime,
                "total_detections": self.state.total_detections,
                "uptime_frozen": False,
            }

            if frames_processed != self._last_progress_frames:
                self._last_progress_frames = frames_processed
                self._event_hub.publish({"type": "progress", **payload_base})

            if msg != self._last_progress_msg:
                self._last_progress_msg = msg
                self._event_hub.publish({
                    "type": "status",
                    "phase": "processing",
                    "message": msg,
                    **payload_base,
                })

        ctx = RunContext(
            pipeline_id=pipeline_id,
            mode=run_mode,
            source=source,
            output_dir=out_dir,
            on_detection=on_detection,
            on_status=on_status,
            on_metrics=on_metrics,
        )

        self._adapter = adapter
        self._store = store
        self._last_progress_frames = -1
        self._last_progress_msg = ""
        loading_detail = str(out_dir)
        loading_msg = "Cargando modelos y preparando salida…"
        if run_mode == RunMode.ONLINE:
            loading_msg = "Conectando cámara en vivo…"
            loading_detail = "\n".join(connect_log) if connect_log else "192.168.1.64"
        elif source.file_path:
            loading_detail = str(source.file_path)

        self.state = SessionState(
            running=True,
            mode=mode,
            pipeline_id=pipeline_id,
            output_dir=str(out_dir),
            started_at=time.monotonic(),
            finished_at=None,
            phase="loading",
            message=loading_msg,
            detail=loading_detail,
        )
        emit_status(
            on_status,
            phase="loading",
            message=loading_msg,
            detail=loading_detail,
            mode=mode,
        )

        async def _start() -> None:
            await adapter.start(ctx)

        self._run_coro(_start())
        return {"output_dir": str(out_dir), "state": "running"}

    def stop_session(self) -> dict[str, Any]:
        if self._adapter is not None:
            try:
                self._run_coro(self._adapter.stop())
            except Exception as exc:
                logger.warning("stop failed: %s", exc)
        self._adapter = None
        out = self.state.output_dir
        if self.state.started_at and self.state.finished_at is None:
            self.state.finished_at = time.monotonic()
        self.state.running = False
        if self.state.phase not in ("completed", "error"):
            self.state.mode = None
            self.state.phase = "idle"
            self.state.message = "Detenido"
            self.state.detail = ""
        return {"state": "idle", "output_dir": out}

    def stop_all(self) -> None:
        try:
            self.stop_session()
        except Exception:
            pass
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)

    def get_status(self) -> dict[str, Any]:
        uptime = _session_uptime(self.state)
        return {
            "running": self.state.running,
            "mode": self.state.mode,
            "pipeline_id": self.state.pipeline_id,
            "output_dir": self.state.output_dir,
            "uptime_sec": uptime,
            "uptime_frozen": not self.state.running and self.state.finished_at is not None,
            "total_detections": self.state.total_detections,
            "metrics": self.state.metrics,
            "phase": self.state.phase,
            "message": self.state.message,
            "detail": self.state.detail,
            "progress": self.state.progress,
            "last_error": self.state.last_error,
        }

    def get_latest_jpeg(self) -> Optional[bytes]:
        if self._static_jpeg:
            return self._static_jpeg
        sink = self.web_sink
        return sink.get_jpeg() if sink else None

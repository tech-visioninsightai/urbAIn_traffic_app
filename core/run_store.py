"""Persist pipeline run artefacts (JSONL schema compatible with testing platform)."""
from __future__ import annotations

import base64
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from urbAIn_traffic_app.core.pipeline_protocol import DetectionEvent

_SAFE_PLATE = re.compile(r"[^A-Za-z0-9]+")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunStore:
    def __init__(self, output_dir: Path, *, project_root: Path) -> None:
        self.output_dir = Path(output_dir)
        self.project_root = project_root
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.crops_dir = self.output_dir / "crops"
        self.crops_dir.mkdir(parents=True, exist_ok=True)
        self.detections_log = self.output_dir / "detections.jsonl"
        self.overlays_log = self.output_dir / "overlays.jsonl"
        self.tracks_json = self.output_dir / "tracks.json"
        self.metrics_log = self.output_dir / "metrics.jsonl"
        self.run_log = self.output_dir / "run.log"
        self._seq = 0
        self._total_emitted = 0

    def reset(self) -> None:
        for path in (
            self.tracks_json,
            self.detections_log,
            self.overlays_log,
            self.metrics_log,
        ):
            if path.exists():
                path.unlink()

    def _append_jsonl(self, path: Path, row: dict) -> None:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def write_detection(
        self,
        event: DetectionEvent,
        *,
        crop_b64: Optional[str] = None,
        extra: Optional[dict] = None,
    ) -> Optional[Path]:
        self._seq += 1
        self._total_emitted += 1
        crop_path = None
        if crop_b64:
            crop_path = self._save_crop(event.label, event.timestamp, crop_b64)
        row = {
            "seq": self._seq,
            "logged_at": _now_iso(),
            "camera_id": event.camera_id,
            "plate_text": event.label,
            "confidence": event.confidence,
            "timestamp": event.timestamp,
            "sequence_number": event.sequence_number,
            **(extra or {}),
            **event.metadata,
        }
        if crop_path:
            try:
                row["crop_path"] = str(crop_path.relative_to(self.project_root))
            except ValueError:
                row["crop_path"] = str(crop_path)
        self._append_jsonl(self.detections_log, row)
        return crop_path

    def _save_crop(self, plate: str, timestamp: str, b64: str) -> Optional[Path]:
        safe = _SAFE_PLATE.sub("_", plate or "unknown").strip("_") or "unknown"
        ts = timestamp.replace(":", "-").replace(".", "-")
        fname = f"{self._seq:06d}_{safe}_{ts}.jpg"
        path = self.crops_dir / fname
        try:
            path.write_bytes(base64.b64decode(b64))
            return path
        except Exception:
            return None

    def write_overlay(self, row: dict) -> None:
        self._append_jsonl(self.overlays_log, {"logged_at": _now_iso(), **row})

    def write_metrics(self, per_camera: dict, uptime_sec: float) -> None:
        self._append_jsonl(
            self.metrics_log,
            {
                "logged_at": _now_iso(),
                "uptime_sec": round(uptime_sec, 2),
                "total_emitted": self._total_emitted,
                "per_camera": per_camera,
            },
        )

    def upsert_track(self, track_id: str, data: dict) -> None:
        doc: dict[str, Any] = {"schema_version": 1, "tracks": []}
        if self.tracks_json.exists():
            try:
                doc = json.loads(self.tracks_json.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        by_id = {t["track_id"]: t for t in doc.get("tracks", []) if t.get("track_id")}
        by_id[track_id] = {**by_id.get(track_id, {}), **data, "track_id": track_id}
        doc["schema_version"] = 1
        doc["updated_at"] = _now_iso()
        doc["tracks"] = list(by_id.values())
        self.tracks_json.write_text(
            json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    @property
    def total_emitted(self) -> int:
        return self._total_emitted

"""Load artefacts from a completed run directory."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class RunLoader:
    def __init__(self, run_dir: Path) -> None:
        self.run_dir = Path(run_dir)

    def load_detections(self) -> list[dict]:
        path = self.run_dir / "detections.jsonl"
        if not path.is_file():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows

    def summary(self) -> dict[str, Any]:
        return {
            "path": str(self.run_dir),
            "detections": len(self.load_detections()),
            "annotated_mp4": (self.run_dir / "annotated.mp4").is_file(),
        }

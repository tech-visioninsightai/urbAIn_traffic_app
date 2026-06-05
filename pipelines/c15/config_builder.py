"""Build C15 YAML configs for traffic-app run modes."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from urbAIn_traffic_app.core.pipeline_protocol import MediaSource, RunMode

APP_DIR = Path(__file__).resolve().parents[2]
CONFIG_DIR = APP_DIR / "config"


def _resolve_model_paths(raw: dict, project_root: Path) -> dict:
    """Turn relative model paths into absolute paths."""
    out = deepcopy(raw)
    models = out.get("models") or {}
    for section in models.values():
        if not isinstance(section, dict):
            continue
        for key, val in list(section.items()):
            if key.endswith("_path") and isinstance(val, str) and val:
                p = Path(val)
                if not p.is_absolute():
                    section[key] = str((project_root / val).resolve())
    return out


def _write_temp_config(data: dict, output_dir: Path, name: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / name
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def build_config_for_source(
    source: MediaSource,
    *,
    project_root: Path,
    run_output_dir: Path,
) -> Path:
    if source.mode == RunMode.ONLINE:
        template = CONFIG_DIR / "config_live_camera.yaml"
    elif source.mode == RunMode.OFFLINE_IMAGE:
        template = CONFIG_DIR / "config_offline_image.yaml"
    else:
        template = CONFIG_DIR / "config_offline.yaml"

    raw: dict[str, Any] = yaml.safe_load(template.read_text(encoding="utf-8"))
    raw = _resolve_model_paths(raw, project_root)

    if source.mode == RunMode.ONLINE and source.camera_uri:
        raw["cameras"][0]["uri"] = source.camera_uri
    elif source.mode == RunMode.OFFLINE_VIDEO and source.file_path:
        resolved = source.file_path.resolve()
        raw["cameras"][0]["uri"] = str(resolved)
        raw["cameras"][0]["single_pass"] = True
        meta = raw["cameras"][0].get("metadata") or {}
        meta.setdefault("location", "offline_file")
        raw["cameras"][0]["metadata"] = meta

    return _write_temp_config(raw, run_output_dir, "runtime_config.yaml")

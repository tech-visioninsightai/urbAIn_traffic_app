"""Shared pipeline contracts for urbAIn Traffic App."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable


class RunMode(str, Enum):
    ONLINE = "online"
    OFFLINE_VIDEO = "offline_video"
    OFFLINE_IMAGE = "offline_image"


@dataclass
class MediaSource:
    """Input source for a run."""

    mode: RunMode
    camera_uri: Optional[str] = None
    file_path: Optional[Path] = None


@dataclass
class RunContext:
    """Runtime context passed to pipeline adapters."""

    pipeline_id: str
    mode: RunMode
    source: MediaSource
    output_dir: Path
    on_detection: Optional[Any] = None
    on_status: Optional[Any] = None
    on_metrics: Optional[Any] = None


@dataclass
class DetectionEvent:
    pipeline_id: str
    camera_id: str
    label: str
    confidence: float
    timestamp: str
    sequence_number: Optional[int] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class OverlayPayload:
    pipeline_id: str
    camera_id: str
    sequence_number: int
    payload: dict


@runtime_checkable
class PipelineAdapter(Protocol):
    pipeline_id: str
    display_name: str

    async def start(self, ctx: RunContext) -> None: ...

    async def stop(self) -> None: ...

    def build_config_path(self, ctx: RunContext) -> str: ...

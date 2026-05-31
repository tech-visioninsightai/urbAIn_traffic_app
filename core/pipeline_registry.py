"""Registry of available pipeline adapters."""
from __future__ import annotations

from typing import Type

from urbAIn_traffic_app.core.pipeline_protocol import PipelineAdapter


class PipelineRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, Type[PipelineAdapter]] = {}

    def register(self, pipeline_id: str, adapter_cls: Type[PipelineAdapter]) -> None:
        self._adapters[pipeline_id] = adapter_cls

    def create(self, pipeline_id: str) -> PipelineAdapter:
        cls = self._adapters.get(pipeline_id)
        if cls is None:
            raise KeyError(f"unknown pipeline: {pipeline_id}")
        return cls()

    def list_pipelines(self) -> list[dict]:
        return [
            {
                "id": pid,
                "display_name": cls.display_name,
                "enabled": pid == "c15",
            }
            for pid, cls in self._adapters.items()
        ]


registry = PipelineRegistry()

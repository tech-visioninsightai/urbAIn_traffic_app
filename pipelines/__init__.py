"""Register pipeline adapters."""
from urbAIn_traffic_app.core.pipeline_registry import registry
from urbAIn_traffic_app.pipelines.c15.adapter import C15PipelineAdapter

registry.register("c15", C15PipelineAdapter)

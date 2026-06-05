"""Lazy access to C15 (defers onnxruntime / M-module import until a run starts)."""
from __future__ import annotations

from typing import Any

_cached: Any = None


def c15() -> Any:
    """Return the :mod:`c15_lpr_pipeline` module (imported once per process)."""
    global _cached
    if _cached is None:
        import c15_lpr_pipeline as mod

        _cached = mod
    return _cached

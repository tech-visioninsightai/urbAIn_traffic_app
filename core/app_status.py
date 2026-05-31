"""Shared status payloads for the traffic app UI."""
from __future__ import annotations

from typing import Any, Callable, Optional

StatusCallback = Optional[Callable[[dict[str, Any]], None]]


def emit_status(
    callback: StatusCallback,
    *,
    phase: str,
    message: str,
    detail: str = "",
    **extra: Any,
) -> None:
    if callback is None:
        return
    payload: dict[str, Any] = {
        "phase": phase,
        "message": message,
        "detail": detail,
        **extra,
    }
    callback(payload)

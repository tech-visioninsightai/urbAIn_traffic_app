"""WebSocket broadcast hub for detection events."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class EventHub:
    """Fan-out events to browser WebSockets on the **uvicorn** event loop.

    Pipeline callbacks run on a different thread/loop; they must call
    :meth:`publish` (thread-safe) instead of awaiting :meth:`broadcast` directly.
  """

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._server_loop: Optional[asyncio.AbstractEventLoop] = None

    def set_server_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Bind the FastAPI/uvicorn loop (call once on app startup)."""
        self._server_loop = loop

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    def publish(self, payload: dict[str, Any]) -> None:
        """Schedule a broadcast from any thread (pipeline workers, sync HTTP)."""
        loop = self._server_loop
        if loop is None or loop.is_closed():
            return
        if not self._clients:
            return
        try:
            asyncio.run_coroutine_threadsafe(self.broadcast(payload), loop)
        except RuntimeError as exc:
            logger.debug("publish skipped: %s", exc)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        msg = json.dumps(payload, ensure_ascii=False)
        async with self._lock:
            if not self._clients:
                return
            dead: list[WebSocket] = []
            for ws in list(self._clients):
                try:
                    await ws.send_text(msg)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self._clients.discard(ws)

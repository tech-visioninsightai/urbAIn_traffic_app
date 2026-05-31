"""FastAPI application factory."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from urbAIn_traffic_app.backend.routes import runs, session, upload
from urbAIn_traffic_app.backend.session_controller import SessionController
from urbAIn_traffic_app.backend.streams import mjpeg
from urbAIn_traffic_app.backend.streams.ws_events import EventHub

APP_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = APP_DIR / "frontend"


def create_app(project_root: Path) -> FastAPI:
    import urbAIn_traffic_app.pipelines  # noqa: F401

    hub = EventHub()
    controller = SessionController(project_root)
    controller.set_event_hub(hub)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        hub.set_server_loop(asyncio.get_running_loop())
        yield

    app = FastAPI(title="Vision Insight AI - urbAIn - traffic", lifespan=lifespan)

    app.state.project_root = project_root
    app.state.session_controller = controller
    app.state.event_hub = hub

    app.include_router(session.router)
    app.include_router(upload.router)
    app.include_router(runs.router)
    app.include_router(mjpeg.router)

    @app.websocket("/ws/events")
    async def ws_events(ws: WebSocket) -> None:
        await hub.connect(ws)
        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            await hub.disconnect(ws)

    if FRONTEND_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

    return app

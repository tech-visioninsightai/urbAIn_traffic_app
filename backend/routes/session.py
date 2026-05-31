from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

router = APIRouter(prefix="/api/session")


class StartRequest(BaseModel):
    pipeline_id: str = "c15"
    mode: str = "online"
    camera_uri: str | None = None
    file_path: str | None = None


@router.get("/status")
def status(request: Request) -> dict:
    return request.app.state.session_controller.get_status()


@router.get("/pipelines")
def pipelines() -> dict:
    from urbAIn_traffic_app.core.pipeline_registry import registry
    import urbAIn_traffic_app.pipelines  # noqa: F401 — register adapters
    return {"pipelines": registry.list_pipelines()}


@router.post("/start")
def start(body: StartRequest, request: Request) -> dict:
    ctrl = request.app.state.session_controller
    try:
        return ctrl.start_session(
            pipeline_id=body.pipeline_id,
            mode=body.mode,
            camera_uri=body.camera_uri,
            file_path=body.file_path,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/snapshot")
def snapshot(request: Request) -> Response:
    jpeg = request.app.state.session_controller.get_latest_jpeg()
    if not jpeg:
        return Response(status_code=404)
    return Response(content=jpeg, media_type="image/jpeg")


@router.post("/stop")
def stop(request: Request) -> dict:
    return request.app.state.session_controller.stop_session()

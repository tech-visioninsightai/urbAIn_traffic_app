from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/runs")


@router.get("/")
def list_runs(request: Request) -> dict:
    runs_root = request.app.state.project_root / "urbAIn_traffic_app" / "runs"
    if not runs_root.is_dir():
        return {"runs": []}
    runs = sorted(
        [p.name for p in runs_root.iterdir() if p.is_dir()],
        reverse=True,
    )
    return {"runs": runs[:50]}

from __future__ import annotations

import re
import shutil
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

router = APIRouter(prefix="/api/upload")

UPLOAD_DIR_NAME = "uploads"
_SAFE_NAME = re.compile(r"[^\w.\-]", re.ASCII)


def _safe_filename(name: str) -> str:
    base = Path(name).name
    cleaned = _SAFE_NAME.sub("_", base).strip("._")
    return cleaned or "upload.bin"


@router.post("/file")
async def upload_file(request: Request, file: UploadFile = File(...)) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Nombre de archivo vacío")
    root = request.app.state.project_root
    upload_dir = root / "urbAIn_traffic_app" / UPLOAD_DIR_NAME
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / _safe_filename(file.filename)
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    if dest.stat().st_size <= 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Archivo vacío")
    return {"path": str(dest.resolve()), "filename": dest.name}

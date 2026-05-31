"""MJPEG stream from WebStreamSink."""
from __future__ import annotations

import asyncio
from typing import AsyncIterator, Optional

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter()


def _get_web_sink(request: Request):
    return request.app.state.session_controller.web_sink


@router.get("/stream/mjpeg")
async def mjpeg_stream(request: Request) -> StreamingResponse:
    controller = request.app.state.session_controller

    async def gen() -> AsyncIterator[bytes]:
        boundary = b"frame"
        while True:
            if await request.is_disconnected():
                break
            jpeg: Optional[bytes] = controller.get_latest_jpeg()
            if not jpeg:
                sink = controller.web_sink
                if sink is not None:
                    jpeg = sink.get_jpeg()
            if jpeg:
                yield (
                    b"--" + boundary + b"\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
                )
            await asyncio.sleep(0.066)

    return StreamingResponse(
        gen(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )

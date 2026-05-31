"""PyWebView desktop shell."""
from __future__ import annotations

import logging
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import uvicorn
import webview

logger = logging.getLogger(__name__)

HOST = "127.0.0.1"
PORT = 8765
STARTUP_TIMEOUT_SEC = 60.0


def _wait_for_server(host: str, port: int, timeout: float) -> bool:
    """Block until the HTTP server accepts connections and responds."""
    deadline = time.monotonic() + timeout
    status_url = f"http://{host}:{port}/api/session/status"
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                pass
            with urllib.request.urlopen(status_url, timeout=2.0) as resp:
                if resp.status == 200:
                    return True
        except (OSError, urllib.error.URLError, TimeoutError):
            time.sleep(0.15)
    return False


def _pick_port(host: str, preferred: int) -> int:
    """Return ``preferred`` if free, otherwise ask the OS for an ephemeral port."""
    try:
        with socket.create_connection((host, preferred), timeout=0.3):
            # Port already in use by another process.
            pass
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((host, 0))
            return int(sock.getsockname()[1])
    except OSError:
        return preferred


def launch(project_root: Path) -> None:
    sys.path.insert(0, str(project_root))

    from urbAIn_testing_platform.gpu_dll_path import setup_gpu_dll_paths, warmup_paddle_gpu

    setup_gpu_dll_paths()
    warmup_paddle_gpu()

    from urbAIn_traffic_app.backend.server import create_app

    app = create_app(project_root)
    port = _pick_port(HOST, PORT)
    serve_error: list[BaseException] = []

    config = uvicorn.Config(
        app,
        host=HOST,
        port=port,
        log_level="info",
        access_log=False,
    )
    server = uvicorn.Server(config)

    def _serve() -> None:
        try:
            server.run()
        except Exception as exc:
            serve_error.append(exc)
            logger.exception("Uvicorn server crashed")

    thread = threading.Thread(target=_serve, name="uvicorn", daemon=True)
    thread.start()

    if not _wait_for_server(HOST, port, STARTUP_TIMEOUT_SEC):
        err = serve_error[0] if serve_error else None
        msg = (
            f"No se pudo iniciar el servidor local en {HOST}:{port}."
            + (f"\n{err}" if err else "")
        )
        raise RuntimeError(msg)

    url = f"http://{HOST}:{port}/"
    logger.info("Traffic app ready at %s", url)

    def _on_window_closed() -> None:
        try:
            app.state.session_controller.stop_all()
        except Exception:
            logger.warning("shutdown failed", exc_info=True)
        server.should_exit = True

    window = webview.create_window(
        "Vision Insight AI - urbAIn - traffic",
        url,
        width=1280,
        height=800,
        min_size=(1024, 640),
        maximized=True,
        background_color="#060B18",
    )
    window.events.closed += _on_window_closed
    webview.start(debug=False)

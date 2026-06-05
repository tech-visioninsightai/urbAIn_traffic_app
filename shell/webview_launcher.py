"""Native desktop shell (pywebview + local FastAPI backend)."""
from __future__ import annotations

import logging
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any

import uvicorn
import webview

logger = logging.getLogger(__name__)

HOST = "127.0.0.1"
PORT = 8765
STARTUP_TIMEOUT_SEC = 60.0

_LOADING_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>urbAIn traffic</title>
<style>
  body { margin:0; height:100vh; display:flex; align-items:center; justify-content:center;
    background:#060B18; color:#E8EEF7; font-family:Segoe UI,sans-serif; }
  .box { text-align:center; }
  .spin { width:40px; height:40px; border:3px solid #2a3550; border-top-color:#5b8def;
    border-radius:50%; animation:spin 0.9s linear infinite; margin:0 auto 16px; }
  @keyframes spin { to { transform:rotate(360deg); } }
</style></head><body>
<div class="box"><div class="spin"></div><div>Iniciando urbAIn traffic…</div></div>
</body></html>"""

# Set by ``launch`` before ``webview.start``; read on window close.
_runtime: dict[str, Any] = {}


def _wait_for_server(host: str, port: int, timeout: float) -> bool:
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
    try:
        with socket.create_connection((host, preferred), timeout=0.3):
            pass
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((host, 0))
            return int(sock.getsockname()[1])
    except OSError:
        return preferred


def _configure_webview2_storage(project_root: Path) -> Path:
    storage = project_root / ".cache" / "pywebview"
    storage.mkdir(parents=True, exist_ok=True)
    # Writable profile avoids WebView2 init hangs (E_ACCESSDENIED) on some Windows setups.
    os.environ.setdefault("WEBVIEW2_USER_DATA_FOLDER", str(storage))
    return storage


def _start_backend(project_root: Path) -> tuple[Any, uvicorn.Server, int]:
    sys.path.insert(0, str(project_root))

    from urbAIn_testing_platform.gpu_dll_path import setup_gpu_dll_paths, warmup_paddle_gpu

    setup_gpu_dll_paths()
    threading.Thread(
        target=warmup_paddle_gpu,
        name="paddle-warmup",
        daemon=True,
    ).start()

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

    threading.Thread(target=_serve, name="uvicorn", daemon=True).start()

    if not _wait_for_server(HOST, port, STARTUP_TIMEOUT_SEC):
        err = serve_error[0] if serve_error else None
        raise RuntimeError(
            f"No se pudo iniciar el servidor local en {HOST}:{port}."
            + (f"\n{err}" if err else "")
        )

    return app, server, port


def _shutdown() -> None:
    app = _runtime.get("app")
    server = _runtime.get("server")
    if app is not None and server is not None:
        try:
            app.state.session_controller.stop_all()
        except Exception:
            logger.warning("shutdown failed", exc_info=True)
        server.should_exit = True


def _main_window() -> Any | None:
    """Window created in ``launch``; ``active_window()`` is unreliable on some builds."""
    win = _runtime.get("window")
    if win is not None:
        return win
    return webview.active_window()


def _show_error_in_window(message: str) -> None:
    window = _main_window()
    if window is None:
        return
    safe = message.replace("&", "&amp;").replace("<", "&lt;")
    window.load_html(
        f"<body style='background:#060B18;color:#E8EEF7;font-family:Segoe UI,sans-serif;"
        f"padding:24px'><h2>No se pudo iniciar</h2><pre>{safe}</pre></body>"
    )


def _backend_after_gui_started() -> None:
    """Runs on a worker thread once the native GUI loop is active."""
    root: Path = _runtime["project_root"]
    try:
        app, server, port = _start_backend(root)
        _runtime["app"] = app
        _runtime["server"] = server
        url = f"http://{HOST}:{port}/"
        logger.info("Traffic app ready at %s", url)

        window = _main_window()
        if window is None:
            raise RuntimeError("Ventana de escritorio no disponible")

        def _on_loaded() -> None:
            try:
                window.maximize()
            except Exception:
                logger.debug("maximize not supported", exc_info=True)

        window.events.loaded += _on_loaded
        window.load_url(url)
    except Exception as exc:
        logger.exception("backend startup failed")
        _show_error_in_window(str(exc))


def launch(project_root: Path) -> None:
    """Open the traffic UI in a native pywebview window (design default)."""
    storage = _configure_webview2_storage(project_root)
    _runtime.clear()
    _runtime["project_root"] = project_root

    window = webview.create_window(
        "Vision Insight AI - urbAIn - traffic",
        html=_LOADING_HTML,
        width=1280,
        height=800,
        min_size=(1024, 640),
        background_color="#060B18",
    )
    _runtime["window"] = window
    window.events.closed += lambda: _shutdown()

    print("Abriendo aplicación de escritorio (WebView2)…", flush=True)
    webview.start(
        _backend_after_gui_started,
        gui="edgechromium",
        storage_path=str(storage),
        debug=False,
    )


def launch_browser(project_root: Path) -> None:
    """Emergency fallback — not the product default."""
    app, server, port = _start_backend(project_root)
    url = f"http://{HOST}:{port}/"
    webbrowser.open(url)
    print(f"Modo navegador (solo diagnóstico): {url}", flush=True)
    print("Ctrl+C para salir.", flush=True)
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        _runtime["app"] = app
        _runtime["server"] = server
        _shutdown()

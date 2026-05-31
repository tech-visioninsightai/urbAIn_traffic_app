"""Live camera helpers: ping + RTSP URI from config."""
from __future__ import annotations

import logging
import platform
import subprocess
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote, urlparse

import yaml

logger = logging.getLogger(__name__)

DEFAULT_HOST = "192.168.1.64"
DEFAULT_PORT = 554
DEFAULT_USER = "admin"
DEFAULT_PASSWORD = "@powerofAI26%"
DEFAULT_STREAM_PATH = "/Streaming/Channels/101"

LIVE_CONFIG = Path(__file__).resolve().parents[1] / "config" / "config_live_camera.yaml"


def build_rtsp_uri(
    *,
    host: str,
    port: int = DEFAULT_PORT,
    username: str = DEFAULT_USER,
    password: str = DEFAULT_PASSWORD,
    stream_path: str = DEFAULT_STREAM_PATH,
) -> str:
    user = quote(username, safe="")
    pwd = quote(password, safe="")
    path = stream_path if stream_path.startswith("/") else f"/{stream_path}"
    return f"rtsp://{user}:{pwd}@{host}:{port}{path}"


def load_live_camera_block(config_path: Path = LIVE_CONFIG) -> dict[str, Any]:
    if not config_path.is_file():
        return {}
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    cameras = raw.get("cameras") or []
    return cameras[0] if cameras else {}


def resolve_online_camera_uri(override: Optional[str] = None) -> str:
    """Return RTSP URI for online mode (explicit override or config file)."""
    if override and override.strip():
        return override.strip()

    cam = load_live_camera_block()
    uri = str(cam.get("uri") or "").strip()
    if uri and "USER" not in uri and "PASS" not in uri and "STREAM_PATH" not in uri:
        return uri

    host = str(cam.get("host") or DEFAULT_HOST)
    port = int(cam.get("port") or DEFAULT_PORT)
    username = str(cam.get("username") or DEFAULT_USER)
    password = str(cam.get("password") or DEFAULT_PASSWORD)
    stream_path = str(cam.get("stream_path") or DEFAULT_STREAM_PATH)
    return build_rtsp_uri(
        host=host,
        port=port,
        username=username,
        password=password,
        stream_path=stream_path,
    )


def camera_host_from_uri(uri: str) -> str:
    parsed = urlparse(uri)
    return parsed.hostname or DEFAULT_HOST


def ping_host(host: str, *, timeout_sec: float = 2.0) -> tuple[bool, str]:
    """ICMP ping once. Returns (ok, detail message)."""
    host = host.strip()
    if not host:
        return False, "host vacío"

    system = platform.system().lower()
    if system == "windows":
        wait_ms = max(500, int(timeout_sec * 1000))
        cmd = ["ping", "-n", "1", "-w", str(wait_ms), host]
    else:
        wait = max(1, int(timeout_sec))
        cmd = ["ping", "-c", "1", "-W", str(wait), host]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec + 2.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)

    if result.returncode == 0:
        return True, f"{host} responde al ping"
    detail = (result.stdout or result.stderr or "").strip().splitlines()
    tail = detail[-1] if detail else f"ping falló (code={result.returncode})"
    return False, tail


def probe_rtsp_uri(uri: str, *, open_timeout_sec: float = 5.0) -> tuple[bool, str]:
    """Try opening RTSP with OpenCV."""
    try:
        import cv2  # noqa: WPS433
    except ImportError:
        return True, "OpenCV no disponible; se omite prueba RTSP"

    cap = cv2.VideoCapture(uri, cv2.CAP_FFMPEG)
    try:
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, int(open_timeout_sec * 1000))
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, int(open_timeout_sec * 1000))
    except Exception:
        pass
    if not cap.isOpened():
        cap.release()
        return False, "No se pudo abrir el stream RTSP"
    ok, _ = cap.read()
    cap.release()
    if ok:
        return True, "Stream RTSP disponible"
    return False, "RTSP abierto pero sin frames; se intentará conectar igualmente"


def prepare_online_camera(
    override_uri: Optional[str] = None,
    *,
    probe_stream: bool = True,
) -> tuple[str, list[str]]:
    """Ping host, resolve RTSP URI, optionally probe stream. Returns (uri, log lines)."""
    uri = resolve_online_camera_uri(override_uri)
    host = camera_host_from_uri(uri)
    logs: list[str] = [f"Ping a {host}…"]

    ok, ping_msg = ping_host(host)
    logs.append(ping_msg)
    if not ok:
        raise ConnectionError(f"No hay respuesta de la cámara ({host}): {ping_msg}")

    if probe_stream:
        logs.append("Comprobando stream RTSP…")
        stream_ok, stream_msg = probe_rtsp_uri(uri)
        logs.append(stream_msg if stream_ok else f"Aviso: {stream_msg}")

    parsed = urlparse(uri)
    logs.append(f"RTSP → {parsed.hostname}:{parsed.port or DEFAULT_PORT}{parsed.path or ''}")
    return uri, logs

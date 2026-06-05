"""Probe / fix MP4 playback rate for offline annotated output (traffic app only)."""
from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VideoTiming:
    fps: float | None
    frame_count: int | None
    duration_sec: float | None


def _ffprobe_duration(path: Path) -> float | None:
    if not shutil.which("ffprobe"):
        return None
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return None
    try:
        value = float((result.stdout or "").strip())
    except ValueError:
        return None
    return value if value > 0 else None


def probe_video_fps(path: Path) -> float | None:
    """Return container FPS from a local video file, or None if unknown."""
    timing = probe_video_timing(path)
    return timing.fps


def count_video_frames(path: Path) -> int:
    """Count frames (OpenCV; falls back to sequential read if metadata lies)."""
    try:
        import cv2
    except ImportError:
        return 0
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return 0
    reported = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if reported > 0:
        cap.release()
        return reported
    n = 0
    while True:
        ok, _ = cap.read()
        if not ok:
            break
        n += 1
    cap.release()
    return n


def probe_video_timing(path: Path) -> VideoTiming:
    duration = _ffprobe_duration(path)
    try:
        import cv2
    except ImportError:
        return VideoTiming(None, None, duration)

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return VideoTiming(None, None, duration)
    fps_raw = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    cap.release()

    fps = fps_raw if 1.0 < fps_raw <= 240.0 else None
    frame_count = frames if frames > 0 else None
    if duration is None and fps and frame_count:
        duration = frame_count / fps
    return VideoTiming(fps=fps, frame_count=frame_count, duration_sec=duration)


def remux_video_fps(video_path: Path, target_fps: float) -> bool:
    """Rewrite ``video_path`` so playback duration matches ``target_fps`` (same frame count)."""
    if target_fps <= 0:
        return False
    current = probe_video_fps(video_path)
    if current is not None and abs(current - target_fps) < 0.05:
        return True
    if not shutil.which("ffmpeg"):
        logger.warning(
            "ffmpeg not found; cannot set annotated FPS to %.2f (was %s)",
            target_fps,
            current,
        )
        return False

    tmp = video_path.with_name(video_path.stem + "._fpsfix.mp4")
    setpts = 1.0
    if current and current > 0:
        setpts = current / target_fps
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-an",
        "-vf",
        f"setpts={setpts:.6f}*PTS",
        "-r",
        f"{target_fps:.3f}",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(tmp),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        logger.warning(
            "FPS remux failed: %s",
            (result.stderr or result.stdout or "")[:400],
        )
        tmp.unlink(missing_ok=True)
        return False
    if not tmp.is_file() or tmp.stat().st_size <= 0:
        tmp.unlink(missing_ok=True)
        return False
    tmp.replace(video_path)
    logger.info(
        "Annotated video FPS adjusted %s -> %.3f (%s)",
        f"{current:.2f}" if current else "?",
        target_fps,
        video_path,
    )
    return True


def sync_annotated_duration(annotated: Path, reference: Path) -> bool:
    """Stretch/compress annotated playback to match ``reference`` wall-clock duration."""
    ref = probe_video_timing(reference)
    if not ref.duration_sec or ref.duration_sec <= 0:
        logger.warning("Could not probe reference duration: %s", reference)
        return False
    out_frames = count_video_frames(annotated)
    if out_frames <= 0:
        logger.warning("Annotated video has no frames: %s", annotated)
        return False
    target_fps = out_frames / ref.duration_sec
    logger.info(
        "Sync annotated duration: %d frames / %.3fs ref -> %.3f fps",
        out_frames,
        ref.duration_sec,
        target_fps,
    )
    return remux_video_fps(annotated, target_fps)

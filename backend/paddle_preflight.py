"""Paddle/OCR readiness check for the traffic app (no pipeline changes)."""
from __future__ import annotations

from urbAIn_testing_platform.gpu_dll_path import setup_gpu_dll_paths, warmup_paddle_gpu


def _looks_like_paddle_block(exc: BaseException) -> bool:
    text = str(exc).lower()
    return (
        "control de aplicaciones" in text
        or "application control" in text
        or "libpaddle" in text
        or "dll load failed" in text
        or "can not import paddle core" in text
    )


def _paddle_block_message(exc: BaseException) -> str:
    if _looks_like_paddle_block(exc):
        return (
            "Windows bloqueó la librería de Paddle (libpaddle.pyd), necesaria para OCR.\n\n"
            "Soluciones habituales:\n"
            "1. Seguridad de Windows > Proteccion contra amenazas > "
            "Administrar configuracion > Exclusiones: anade la carpeta de Python "
            "o el .venv del proyecto.\n"
            "2. Si tienes 'Control inteligente de aplicaciones' activo, desactivalo "
            "temporalmente para desarrollo o permite python.exe.\n"
            "3. Reinstala Paddle 3.3 (no 2.6) tras desbloquear:\n"
            "     pip uninstall -y paddlepaddle paddlepaddle-gpu paddleocr paddlex\n"
            "     pip install \"protobuf>=4.25.1,<6.34\"\n"
            "     pip install paddlepaddle-gpu==3.3.0 -i https://www.paddlepaddle.org.cn/packages/stable/cu129/\n"
            "     pip install paddleocr\n"
            "Ver urbAIn_traffic_app/requirements-gpu.txt\n"
            f"\nDetalle técnico: {exc}"
        )
    return f"No se pudo cargar Paddle OCR: {exc}"


def check_paddle_ocr_ready() -> tuple[bool, str]:
    """Verify Paddle can load before starting a C15 session."""
    setup_gpu_dll_paths()
    try:
        import paddle  # noqa: WPS433
    except ImportError as exc:
        if _looks_like_paddle_block(exc):
            return False, _paddle_block_message(exc)
        return (
            False,
            "No esta instalado paddlepaddle, o es una version antigua (2.x).\n"
            "Para urbAIn usa Paddle 3.3 GPU (cu129), no paddlepaddle-gpu 2.6 desde PyPI:\n"
            "  pip uninstall -y paddlepaddle paddlepaddle-gpu paddleocr paddlex\n"
            "  pip install \"protobuf>=4.25.1,<6.34\"\n"
            "  pip install paddlepaddle-gpu==3.3.0 -i https://www.paddlepaddle.org.cn/packages/stable/cu129/\n"
            "  pip install paddleocr\n"
            "Ver urbAIn_traffic_app/requirements-gpu.txt",
        )
    except OSError as exc:
        return False, _paddle_block_message(exc)
    except Exception as exc:  # noqa: BLE001
        return False, _paddle_block_message(exc)

    disable = getattr(paddle, "disable_static", None)
    if callable(disable):
        disable()

    if warmup_paddle_gpu():
        return True, "Paddle OCR listo."

    try:
        import numpy as np

        place = paddle.CUDAPlace(0) if paddle.is_compiled_with_cuda() else "cpu"
        x = paddle.to_tensor(np.zeros((1, 1), dtype="float32"), place=place)
        _ = float(x.sum().numpy())
        return True, "Paddle OCR listo."
    except Exception as exc:  # noqa: BLE001
        return False, _paddle_block_message(exc)

# urbAIn Traffic App

Desktop web UI for running the C15 LPR pipeline on offline video, images, or a live camera feed.

## Requirements

- Python 3.10+
- C15 orchestrator and module repos checked out alongside this package (see `launch.bat`)
- GPU optional; CPU fallback supported

## Run

Desktop app (pywebview + WebView2) from the parent project root (`urbAIn`):

```bat
urbAIn_traffic_app\launch.bat
```

Requires [Microsoft Edge WebView2 Runtime](https://go.microsoft.com/fwlink/p/?LinkId=2124703)
on Windows.

### Python GPU stack (C15 + OCR)

Install base deps first (`requirements.txt`), then the GPU stack. **Do not**
install `paddlepaddle-gpu` 2.x from PyPI — it downgrades `protobuf` and breaks
`onnx` / `onnxruntime`.

```powershell
pip install -r urbAIn_traffic_app/requirements.txt
pip uninstall -y paddlepaddle paddlepaddle-gpu paddleocr paddlex
pip install "protobuf>=4.25.1,<6.34"
pip install paddlepaddle-gpu==3.3.0 -i https://www.paddlepaddle.org.cn/packages/stable/cu129/
pip install paddleocr onnxruntime-gpu
python -c "from urbAIn_testing_platform.gpu_dll_path import check_paddle_ocr_ready; print(check_paddle_ocr_ready())"
```

If Windows blocks `libpaddle.pyd`, add a Defender exclusion for your Python
folder before reinstalling Paddle.

Or:

```bash
python -m urbAIn_traffic_app
```

Diagnostic only (system browser, not the product UI):

```bash
python -m urbAIn_traffic_app --browser
```

## Layout

- `backend/` — FastAPI server, session control, MJPEG/WebSocket streams
- `frontend/` — Static UI (live view, run browser, controls)
- `pipelines/c15/` — Adapter to the C15 orchestrator
- `config/` — Offline / live camera YAML presets

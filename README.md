# urbAIn Traffic App

Desktop web UI for running the C15 LPR pipeline on offline video, images, or a live camera feed.

## Requirements

- Python 3.10+
- C15 orchestrator and module repos checked out alongside this package (see `launch.bat`)
- GPU optional; CPU fallback supported

## Run

From the parent project root (DetectionAI):

```bat
urbAIn_traffic_app\launch.bat
```

Or:

```bash
python -m urbAIn_traffic_app
```

## Layout

- `backend/` — FastAPI server, session control, MJPEG/WebSocket streams
- `frontend/` — Static UI (live view, run browser, controls)
- `pipelines/c15/` — Adapter to the C15 orchestrator
- `config/` — Offline / live camera YAML presets

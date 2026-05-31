"""Entry point: python -m urbAIn_traffic_app"""
from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    try:
        from urbAIn_traffic_app.shell.webview_launcher import launch

        launch(root)
    except Exception as exc:
        print(f"Error al iniciar la app: {exc}", file=sys.stderr)
        try:
            import webview

            webview.create_window(
                "Vision Insight AI - urbAIn - traffic — Error",
                html=f"<body style='background:#060B18;color:#E8EEF7;font-family:sans-serif;padding:24px'><h2>No se pudo iniciar</h2><pre>{exc}</pre></body>",
                width=640,
                height=360,
            )
            webview.start(debug=False)
        except Exception:
            raise


if __name__ == "__main__":
    main()

"""Entry point: python -m urbAIn_traffic_app [--browser]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="urbAIn traffic desktop app")
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Solo diagnóstico: abrir en el navegador del sistema (no es el modo producto)",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    try:
        if args.browser:
            from urbAIn_traffic_app.shell.webview_launcher import launch_browser

            launch_browser(root)
        else:
            from urbAIn_traffic_app.shell.webview_launcher import launch

            launch(root)
    except Exception as exc:
        print(f"Error al iniciar la app: {exc}", file=sys.stderr)
        try:
            import webview

            webview.create_window(
                "Vision Insight AI - urbAIn - traffic — Error",
                html=(
                    "<body style='background:#060B18;color:#E8EEF7;"
                    "font-family:sans-serif;padding:24px'>"
                    f"<h2>No se pudo iniciar</h2><pre>{exc}</pre>"
                    "<p>Instala "
                    "<a href='https://go.microsoft.com/fwlink/p/?LinkId=2124703'>"
                    "WebView2 Runtime</a> si falta.</p></body>"
                ),
                width=640,
                height=400,
            )
            webview.start(debug=False, gui="edgechromium")
        except Exception:
            raise


if __name__ == "__main__":
    main()

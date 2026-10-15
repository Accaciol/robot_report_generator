"""Interface web local: python gui.py ou robot-report-gui."""
from __future__ import annotations

import os
import threading
import webbrowser

from werkzeug.serving import make_server

from core.web_app import create_app


def main() -> None:
    app = create_app()
    host = os.environ.get("ROBOT_REPORT_HOST", "127.0.0.1")
    port = int(os.environ.get("ROBOT_REPORT_PORT", "0"))
    public_origin = os.environ.get("ROBOT_REPORT_ORIGIN")
    server = make_server(host, port, app, threaded=True)
    server_port = server.server_port
    if public_origin:
        origin = public_origin
    elif host in ("127.0.0.1", "0.0.0.0"):
        origin = f"http://127.0.0.1:{server_port}"
    else:
        origin = f"http://{host}:{server_port}"
    app.config["LOCAL_ORIGIN"] = origin
    app.config["STOP_SERVER"] = server.shutdown
    url = f"{origin}/#token={app.config['SESSION_TOKEN']}"
    print(f"Interface local: {url}", flush=True)
    print("Use Encerrar na interface ou Ctrl+C neste terminal.", flush=True)
    if os.environ.get("ROBOT_REPORT_NO_BROWSER") != "1" and host == "127.0.0.1":
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.extensions["jobs"].close()
        app.extensions["imports"].close()
        server.server_close()


if __name__ == "__main__":
    main()

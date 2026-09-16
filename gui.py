"""Interface web local: python gui.py ou robot-report-gui."""
from __future__ import annotations

import threading
import webbrowser

from werkzeug.serving import make_server

from core.web_app import create_app


def main() -> None:
    app = create_app()
    server = make_server("127.0.0.1", 0, app, threaded=True)
    origin = f"http://127.0.0.1:{server.server_port}"
    app.config["LOCAL_ORIGIN"] = origin
    app.config["STOP_SERVER"] = server.shutdown
    url = f"{origin}/#token={app.config['SESSION_TOKEN']}"
    print(f"Interface local: {url}", flush=True)
    print("Use Encerrar na interface ou Ctrl+C neste terminal.", flush=True)
    threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.extensions["jobs"].close()
        server.server_close()


if __name__ == "__main__":
    main()

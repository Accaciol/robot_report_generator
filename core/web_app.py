"""Rotas autenticadas da interface local."""
from __future__ import annotations

import hmac
import os
import secrets
import tempfile
import threading
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, send_file

from core.web_jobs import JobManager


def _path(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Informe um caminho válido.")
    return Path(value).expanduser().resolve()


def _writable_directory(path):
    if not path.is_dir():
        raise ValueError(f"Pasta não encontrada: {path}")
    with tempfile.TemporaryFile(dir=path):
        pass


def create_app():
    app = Flask(__name__, template_folder="web/templates", static_folder="web/static")
    app.config.update(SESSION_TOKEN=secrets.token_urlsafe(32), LOCAL_ORIGIN="http://127.0.0.1:5000",
                      MAX_CONTENT_LENGTH=1024 * 1024, STOP_SERVER=lambda: None)
    jobs = JobManager()
    app.extensions["jobs"] = jobs

    def valid_token(value):
        return hmac.compare_digest((value or "").encode("utf-8"), app.config["SESSION_TOKEN"].encode("utf-8"))

    @app.before_request
    def protect():
        origin = app.config["LOCAL_ORIGIN"]
        if request.host_url.rstrip("/") != origin:
            abort(403)
        if request.headers.get("Origin") not in (None, origin):
            abort(403)
        if request.headers.get("Sec-Fetch-Site") == "cross-site":
            abort(403)
        if request.path.startswith("/api/"):
            if not valid_token(request.headers.get("X-Session-Token")):
                abort(403)
            if request.method == "POST" and request.headers.get("Origin") != origin:
                abort(403)
        elif request.path.startswith("/reports/"):
            if not valid_token(request.cookies.get("robot_session")):
                abort(403)

    @app.after_request
    def headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        if request.path.startswith("/reports/"):
            # Generated HTML may contain scripts. Isolate it from the local API.
            response.headers["Content-Security-Policy"] = "sandbox allow-scripts allow-downloads allow-popups"
        else:
            response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        return response

    @app.errorhandler(403)
    def forbidden(error):
        return jsonify(error="Acesso local não autorizado. Abra o endereço exibido no terminal."), 403

    @app.errorhandler(400)
    def bad_request(error):
        return jsonify(error="Requisição inválida."), 400

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.post("/api/session")
    def session():
        response = jsonify(home=str(Path.home()), destination=str(Path.home()),
                           history=str(Path.home() / "robot-report-history.json"))
        response.set_cookie("robot_session", app.config["SESSION_TOKEN"], httponly=True,
                            samesite="Strict", path="/reports/")
        return response

    @app.get("/api/folders")
    def folders():
        try:
            path = _path(request.args.get("path", str(Path.home())))
            children = sorted((p for p in path.iterdir() if p.is_dir()), key=lambda p: p.name.casefold())
            return jsonify(path=str(path), parent=str(path.parent),
                           has_output=(path / "output.xml").is_file(),
                           folders=[dict(name=p.name, path=str(p)) for p in children])
        except (OSError, ValueError) as exc:
            return jsonify(error=f"Não foi possível abrir a pasta: {exc}"), 400

    @app.get("/api/state")
    def state():
        return jsonify(jobs.snapshot())

    @app.post("/api/runs")
    def start():
        data = request.get_json()
        try:
            if not isinstance(data, dict) or not isinstance(data.get("folders"), list) or not data["folders"]:
                raise ValueError("Adicione pelo menos uma pasta de resultados.")
            paths = list(dict.fromkeys(_path(p) for p in data["folders"]))
            for path in paths:
                if not (path / "output.xml").is_file():
                    raise ValueError(f"output.xml não encontrado em: {path}")
            destination = _path(data.get("destination"))
            history = _path(data.get("history"))
            _writable_directory(destination)
            _writable_directory(history.parent)
            if history.exists() and (not history.is_file() or not os.access(history, os.W_OK)):
                raise ValueError("O arquivo de histórico não permite escrita.")
            return jsonify(run_id=jobs.start(paths, destination, history)), 202
        except (ValueError, OSError) as exc:
            return jsonify(error=str(exc)), 400
        except RuntimeError as exc:
            return jsonify(error=str(exc)), 409

    @app.post("/api/cancel")
    def cancel():
        data = request.get_json()
        if not isinstance(data, dict):
            abort(400)
        try:
            jobs.cancel(data.get("run_id"))
            return jsonify(ok=True), 202
        except RuntimeError as exc:
            return jsonify(error=str(exc)), 409

    @app.get("/reports/<ident>")
    def report(ident):
        with jobs.lock:
            path = jobs.reports.get(ident)
        if path is None or not path.is_file():
            abort(404)
        return send_file(path, mimetype="text/html", as_attachment=request.args.get("download") == "1")

    @app.post("/api/shutdown")
    def shutdown():
        with jobs.lock:
            jobs.closing = True
        def stop():
            jobs.close()
            app.config["STOP_SERVER"]()
        threading.Thread(target=stop, daemon=True).start()
        return jsonify(ok=True), 202

    return app

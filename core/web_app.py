"""Routes and HTTP security rules for the local and shared report pages."""
from __future__ import annotations

import hmac
import os
import secrets
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Any

from flask import Flask, Response, abort, jsonify, render_template, request, send_file

from core.catalog_overview import PERIODS, overview as build_overview
from core.database_admin import (
    cleanup_orphaned_artifacts as remove_orphans,
    orphaned_artifacts,
)
from core.import_service import DEFAULT_MAX_UPLOAD_BYTES, ImportService, _configured_limit
from core.report_renderer import ReportRenderer
from core.sqlite_store import SQLiteStore, default_database_path
from core.web_jobs import JobManager
from core.web_services import (catalog_overview, catalog_systems, list_history,
                               remove_history)


def create_app(config: dict[str, Any] | None = None) -> Flask:
    """Build the Flask app and attach its import and background-job services."""
    frontend_root = Path(__file__).resolve().parent.parent / "frontend" / "web"
    app = Flask(
        __name__,
        template_folder=str(frontend_root / "templates"),
        static_folder=str(frontend_root / "static"),
    )
    if config:
        app.config.update(config)
    database = Path(app.config.get("DATABASE", default_database_path()))
    upload_limit = _configured_limit(
        "ROBOT_REPORT_MAX_UPLOAD_BYTES",
        DEFAULT_MAX_UPLOAD_BYTES,
    )
    app.config.update(
        SESSION_TOKEN=secrets.token_urlsafe(32),
        INGEST_TOKEN=app.config.get("INGEST_TOKEN", os.environ.get("ROBOT_REPORT_INGEST_TOKEN", "")),
        LOCAL_ORIGIN="http://127.0.0.1:5000",
        DATABASE=database,
        MAX_CONTENT_LENGTH=upload_limit + 1024 * 1024,
    )
    jobs = JobManager()
    imports = ImportService(database)
    app.extensions["jobs"] = jobs
    app.extensions["imports"] = imports

    def valid_token(value: str | None) -> bool:
        return hmac.compare_digest((value or "").encode(), app.config["SESSION_TOKEN"].encode())

    def valid_ingest_token() -> bool:
        expected = str(app.config.get("INGEST_TOKEN", ""))
        supplied = request.headers.get("Authorization", "")
        if supplied.lower().startswith("bearer "):
            supplied = supplied[7:]
        return bool(expected) and hmac.compare_digest(supplied.encode(), expected.encode())

    @app.before_request
    def protect():
        if request.path.startswith("/api/automation/"):
            if not valid_ingest_token():
                abort(403)
            return
        public_path = (
            request.path == "/public"
            or request.path.startswith("/public/")
            or request.path in ("/static/public_catalog.js", "/static/public_catalog.css")
        )
        if public_path:
            # The shared catalog is intentionally read-only; all state changes stay local.
            if request.path == "/public/api/pdf":
                if request.method not in ("GET", "HEAD", "POST"):
                    abort(405)
                return
            if request.method not in ("GET", "HEAD"):
                abort(405)
            return
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
        elif request.path.startswith("/reports/") and not valid_token(
            request.cookies.get("robot_session")
        ):
            abort(403)

    @app.after_request
    def headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = (
            "SAMEORIGIN" if request.path.startswith("/public/reports/") else "DENY")
        is_embedded_report = request.path.startswith(("/reports/", "/public/reports/"))
        response.headers["Content-Security-Policy"] = (
            "sandbox allow-scripts allow-downloads allow-popups"
            if is_embedded_report
            else (
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
            )
        )
        return response

    @app.errorhandler(403)
    def forbidden(error):
        return jsonify(
            error="Acesso local não autorizado. Abra o endereço exibido no terminal."
        ), 403

    @app.errorhandler(400)
    def bad_request(error):
        return jsonify(error="Requisição inválida."), 400

    @app.errorhandler(413)
    def too_large(error):
        return jsonify(error="O ZIP excede o limite de upload configurado."), 413

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.get("/public")
    def public_catalog():
        return render_template("public_catalog.html", title="Relatórios Robot Framework")

    @app.get("/public/api/systems")
    def public_systems():
        entries = SQLiteStore(Path(app.config["DATABASE"])).systems()
        systems = [
            {
                "id": metadata["id"],
                "name": metadata["name"],
                "executions": len(history),
                "system_version": history[-1].system_version if history else "",
            }
            for metadata, history, _ in entries
            if history
        ]
        return jsonify(systems=systems)

    @app.get("/public/api/overview")
    def public_overview():
        period = request.args.get("period", "30")
        if period not in PERIODS:
            return jsonify(error="Período inválido."), 400
        entries = SQLiteStore(Path(app.config["DATABASE"])).systems()
        return jsonify(build_overview(entries, period))

    @app.get("/public/reports/<system_id>")
    def public_report(system_id):
        store = SQLiteStore(Path(app.config["DATABASE"]))
        try:
            metadata, history, directory = store.load(system_id)
            data = store.report_data(
                metadata,
                history,
                directory,
                "Relatório de Execução — Testes BDD",
            )
            html = ReportRenderer(directory / "results").render_html(data, main_max_width=1760)
        except ValueError as exc:
            abort(404, description=str(exc))
        return Response(html, mimetype="text/html", headers={"Cache-Control": "no-store"})

    @app.route("/public/api/pdf", methods=["GET", "POST"])
    def public_generate_custom_pdf():
        store = SQLiteStore(Path(app.config["DATABASE"]))
        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            system_ids = data.get("systems")
            sections = data.get("sections")
            title = data.get("title") or "Relatório de Testes Automatizados"
        else:
            system_ids_param = request.args.get("systems", "").strip()
            system_ids = [s.strip() for s in system_ids_param.split(",") if s.strip()] if system_ids_param else None
            sections_param = request.args.get("sections", "").strip()
            sections = [s.strip() for s in sections_param.split(",") if s.strip()] if sections_param else None
            title = request.args.get("title") or "Relatório de Testes Automatizados"

        from core.pdf_summary import collect_systems_data, render_custom_pdf
        try:
            systems = collect_systems_data(store, system_ids)
            if not systems:
                return jsonify(error="Nenhum sistema com histórico encontrado."), 404

            temp_dir = tempfile.TemporaryDirectory(prefix="robot-report-pdf-")
            pdf_path = Path(temp_dir.name) / "relatorio_testes.pdf"
            render_custom_pdf(systems, pdf_path, title=title, sections=sections)

            response = send_file(
                pdf_path,
                as_attachment=True,
                download_name="relatorio_testes.pdf",
                mimetype="application/pdf",
            )
            response.call_on_close(temp_dir.cleanup)
            return response
        except Exception as exc:
            return jsonify(error=f"Erro ao gerar PDF: {exc}"), 500

    @app.route("/api/reports/pdf/custom", methods=["GET", "POST"])
    def api_generate_custom_pdf():
        return public_generate_custom_pdf()

    @app.post("/api/session")
    def session():
        return jsonify(database=str(app.config["DATABASE"]))

    @app.get("/api/state")
    def state():
        return jsonify(jobs.snapshot())

    @app.get("/api/systems")
    def systems():
        return jsonify(systems=catalog_systems(Path(app.config["DATABASE"])))

    @app.get("/api/overview")
    def overview():
        return jsonify(
            catalog_overview(
                Path(app.config["DATABASE"]),
                request.args.get("period", "30"),
            )
        )

    @app.get("/api/history")
    def history_entries():
        try:
            entries = list_history(
                Path(app.config["DATABASE"]),
                request.args.get("system_id", ""),
            )
            return jsonify(entries=entries)
        except (OSError, ValueError) as exc:
            return jsonify(error=str(exc)), 400

    @app.post("/api/history/remove")
    def remove_history_entry():
        data = request.get_json()
        if not isinstance(data, dict):
            abort(400)
        try:
            with jobs.lock:
                if jobs.active or jobs.closing:
                    return jsonify(
                        error="Aguarde a geração terminar antes de remover uma execução."
                    ), 409
                remove_history(
                    Path(app.config["DATABASE"]),
                    data.get("system_id"),
                    data.get("execution_id"),
                )
            return jsonify(ok=True)
        except (OSError, ValueError, TypeError) as exc:
            return jsonify(error=str(exc)), 400

    @app.get("/api/artifacts/orphans")
    def list_orphaned_artifacts():
        paths = orphaned_artifacts(Path(app.config["DATABASE"]))
        return jsonify(count=len(paths), paths=paths)

    @app.post("/api/artifacts/cleanup")
    def cleanup_orphaned_artifacts():
        with jobs.lock:
            if jobs.active or jobs.closing or imports.pending:
                return jsonify(error="Finalize importações antes de limpar arquivos órfãos."), 409
            paths = remove_orphans(Path(app.config["DATABASE"]))
        return jsonify(removed=len(paths), paths=paths)

    @app.post("/api/imports/preview")
    def preview_import():
        upload = request.files.get("file")
        if upload is None or not upload.filename:
            return jsonify(error="Selecione um arquivo ZIP."), 400
        try:
            return jsonify(imports.prepare_upload(upload.stream, upload.filename))
        except (OSError, ValueError) as exc:
            return jsonify(error=str(exc)), 400

    @app.post("/api/automation/imports")
    def automation_import():
        """Accept and queue a Robot results ZIP in one authenticated request."""
        upload = request.files.get("file")
        if upload is None or not upload.filename:
            return jsonify(error="Envie o ZIP no campo 'file'."), 400
        system_id = request.form.get("system_id", "")
        name = request.form.get("system_name", "")
        version = request.form.get("system_version", "")
        try:
            SQLiteStore.validate_system_id(system_id)
            if not name.strip() or len(name) > 200:
                raise ValueError("Informe um nome de sistema válido (até 200 caracteres).")
            if not version.strip() or len(version) > 200:
                raise ValueError("Informe uma versão válida (até 200 caracteres).")
            prepared_data = imports.prepare_upload(upload.stream, upload.filename)
            if not prepared_data.get("execution_date"):
                imports.discard_upload(prepared_data["upload_id"])
                raise ValueError("O output.xml não contém a data de execução.")
            prepared = imports.consume_upload(prepared_data["upload_id"])
            source = {
                "path": prepared.results_dir,
                "archive_path": prepared.archive,
                "cleanup_dir": prepared.stage_dir,
                "system_id": system_id,
                "name": name.strip(),
                "system_version": version.strip(),
                # The parser returns a datetime object; the normal CLI derives
                # the canonical timestamp directly from output.xml.
                "execution_date": None,
            }
            with jobs.lock:
                if jobs.active or jobs.closing:
                    shutil.rmtree(prepared.stage_dir, ignore_errors=True)
                    return jsonify(error="Já existe uma importação ativa ou o servidor está encerrando."), 409
                run_id = jobs.start([source], Path(app.config["DATABASE"]))
            return jsonify(import_id=run_id, status_url=f"/api/automation/imports/{run_id}"), 202
        except RuntimeError as exc:
            return jsonify(error=str(exc)), 409
        except (OSError, ValueError, TypeError) as exc:
            return jsonify(error=str(exc)), 400

    @app.get("/api/automation/imports/<run_id>")
    def automation_import_status(run_id: str):
        status = jobs.status(run_id)
        if status is None:
            return jsonify(error="Importação inexistente ou expirada."), 404
        return jsonify(status)

    @app.post("/api/imports")
    def commit_import():
        data = request.get_json()
        if not isinstance(data, dict):
            abort(400)
        prepared = None
        try:
            system_id = data.get("system_id")
            name = data.get("system_name")
            version = data.get("system_version")
            SQLiteStore.validate_system_id(system_id)
            if not isinstance(name, str) or not name.strip():
                raise ValueError("Informe o nome do sistema e a versão do produto.")
            if not isinstance(version, str) or not version.strip():
                raise ValueError("Informe o nome do sistema e a versão do produto.")
            execution_date = data.get("execution_date")
            if not execution_date:
                raise ValueError("Informe a data e hora da execução.")
            prepared = imports.consume_upload(data.get("upload_id", ""))
            source = {
                "path": prepared.results_dir,
                "archive_path": prepared.archive,
                "cleanup_dir": prepared.stage_dir,
                "system_id": system_id,
                "name": name.strip(),
                "system_version": version.strip(),
                "execution_date": execution_date,
            }
            with jobs.lock:
                if jobs.active or jobs.closing:
                    raise RuntimeError("Já existe uma geração ativa ou o servidor está encerrando.")
                run_id = jobs.start([source], Path(app.config["DATABASE"]))
            return jsonify(run_id=run_id), 202
        except RuntimeError as exc:
            if prepared is not None:
                shutil.rmtree(prepared.stage_dir, ignore_errors=True)
            return jsonify(error=str(exc)), 409
        except (OSError, ValueError, TypeError) as exc:
            if prepared is not None:
                shutil.rmtree(prepared.stage_dir, ignore_errors=True)
            return jsonify(error=str(exc)), 400

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

    @app.post("/api/shutdown")
    def shutdown():
        with jobs.lock:
            jobs.closing = True

        def stop():
            jobs.close()
            imports.close()
            app.config["STOP_SERVER"]()

        threading.Thread(target=stop, daemon=True).start()
        return jsonify(ok=True), 202

    return app

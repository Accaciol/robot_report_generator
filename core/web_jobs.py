"""Fila sequencial de processos, independente das requisições HTTP."""
from __future__ import annotations

import copy
from dataclasses import asdict
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import uuid
from collections import deque
from datetime import datetime
from pathlib import Path

from core.azure_publish import publish_if_configured
from core.catalog import Catalog


class JobManager:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.cancelled = threading.Event()
        self.worker = None
        self.process = None
        self.closing = False
        self.run_id = None
        self.items = []
        self.logs = deque(maxlen=3000)
        self.errors = deque(maxlen=50)
        self.reports = {}
        self.summaries = {}
        self.pdf_lock = threading.Lock()
        self.active = False

    def snapshot(self):
        with self.lock:
            return dict(run_id=self.run_id, active=self.active,
                        cancelling=self.active and self.cancelled.is_set(),
                        items=copy.deepcopy(self.items), logs=list(self.logs),
                        errors=list(self.errors))

    @staticmethod
    def _report_name(folder, system_id=None):
        label = re.sub(r"[^A-Za-z0-9_-]+", "_", folder.name).strip("_")[:48] or "resultados"
        source_id = hashlib.sha256(os.fsencode(str(folder) + (system_id or ""))).hexdigest()[:12]
        app_prefix = f"{system_id}_" if system_id else ""
        return f"relatorio_{app_prefix}{label}_{source_id}.html"

    def start(self, folders, destination, history, catalog_dir=None):
        with self.lock:
            if self.active or self.closing:
                raise RuntimeError("Já existe uma execução ativa ou o servidor está encerrando.")
            self.run_id = uuid.uuid4().hex
            self.cancelled.clear()
            self.logs.clear()
            self.items = []
            for source in folders:
                folder = source["path"] if isinstance(source, dict) else source
                system_id = source.get("system_id") if isinstance(source, dict) else None
                system_name = source.get("name") if isinstance(source, dict) else None
                ident = uuid.uuid4().hex
                name = self._report_name(folder, system_id)
                self.items.append(dict(id=ident, folder=str(folder), status="waiting",
                                       report=str(destination / name), error=None,
                                       system_id=system_id, system_name=system_name))
            self.active = True
            self.worker = threading.Thread(target=self._run, args=(self.run_id, str(history), catalog_dir), daemon=True)
            self.worker.start()
            return self.run_id

    def _log(self, run_id, message):
        with self.lock:
            if run_id == self.run_id:
                self.logs.append(str(message)[-8000:])

    def record_error(self, run_id, folder, message, lines):
        with self.lock:
            self.errors.append(dict(
                timestamp=datetime.now().isoformat(timespec="seconds"),
                run_id=run_id,
                folder=str(folder),
                message=str(message),
                log="\n".join(lines)[-12000:],
            ))

    def _publish(self, item, staged_report, summary, run_id):
        final_report = Path(item["report"])
        os.replace(staged_report, final_report)
        for old_id, old_path in list(self.reports.items()):
            if old_path == final_report:
                self.reports.pop(old_id)
                self.summaries.pop(old_id, None)
        self.reports[item["id"]] = final_report
        self.summaries[item["id"]] = summary
        item["status"] = "completed"
        try:
            final_report.with_suffix(".pdf").unlink(missing_ok=True)
        except OSError as exc:
            self._log(run_id, f"Não foi possível remover o PDF anterior: {exc}")

    def _run(self, run_id, history, catalog_dir):
        summary_dir = None
        try:
            summary_dir = tempfile.TemporaryDirectory(prefix="robot-report-summary-")
            for item in self.items:
                summary_path = Path(summary_dir.name) / f"{item['id']}.json"
                item_history = history
                if item["system_id"]:
                    item_history = str(Path(summary_dir.name) / f"{item['id']}-history.json")
                    catalog = Catalog(catalog_dir)
                    try:
                        _, entries, _ = catalog.load(item["system_id"])
                    except ValueError as exc:
                        if "inexistente" not in str(exc):
                            raise
                        entries = []
                    Path(item_history).write_text(json.dumps([asdict(entry) for entry in entries],
                                                            ensure_ascii=False), encoding="utf-8")
                with tempfile.TemporaryDirectory(prefix=".robot-report-", dir=Path(item["report"]).parent) as stage_dir:
                    staged_report = Path(stage_dir) / "relatorio.html"
                    with self.lock:
                        if self.cancelled.is_set():
                            item["status"] = "cancelled"
                            continue
                        item["status"] = "running"
                        command = [sys.executable, "-u", str(Path(__file__).resolve().parent.parent / "main.py"),
                                   "--results-dir", item["folder"], "--history", item_history,
                                   "--report", str(staged_report), "--summary-json", str(summary_path)]
                        try:
                            # Holding the lock makes process creation atomic with cancellation.
                            self.process = subprocess.Popen(command, stdout=subprocess.PIPE,
                                                            stderr=subprocess.STDOUT, text=True,
                                                            encoding="utf-8", errors="replace",
                                                            env={**os.environ, "PYTHONIOENCODING": "utf-8"})
                            process = self.process
                        except OSError as exc:
                            item.update(status="failed", error=str(exc))
                            self._log(run_id, exc)
                            self.record_error(run_id, item["folder"], item["error"], [str(exc)])
                            continue
                    self._log(run_id, f"Gerando: {item['folder']}")
                    item_log = deque(maxlen=80)
                    try:
                        with process.stdout:
                            for line in process.stdout:
                                message = line.rstrip()
                                item_log.append(message[-1000:])
                                self._log(run_id, message)
                        code = process.wait()
                        prepared_summary = None
                        prepare_error = None
                        if code == 0 and staged_report.is_file() and not self.cancelled.is_set():
                            try:
                                prepared_summary = json.loads(summary_path.read_text(encoding="utf-8"))
                                if item["system_id"]:
                                    Catalog(catalog_dir).import_results(
                                        item["folder"], item["system_id"], item["system_name"])
                            except (OSError, ValueError, json.JSONDecodeError) as exc:
                                prepare_error = exc
                        with self.pdf_lock:
                            with self.lock:
                                if self.cancelled.is_set():
                                    item["status"] = "cancelled"
                                elif prepared_summary is not None:
                                    try:
                                        self._publish(item, staged_report, prepared_summary, run_id)
                                    except OSError as exc:
                                        item.update(status="failed", error=f"Relatório indisponível: {exc}")
                                elif prepare_error is not None:
                                    item.update(status="failed", error=f"Relatório indisponível: {prepare_error}")
                                else:
                                    item.update(status="failed", error=f"Geração falhou (código {code}). Consulte o log.")
                                if item["status"] == "failed":
                                    self.record_error(run_id, item["folder"], item["error"], item_log)
                                self.process = None
                        if item["status"] == "completed" and item["system_id"]:
                            try:
                                if publish_if_configured(catalog_dir):
                                    self._log(run_id, "Site atualizado no Azure Static Web Apps.")
                            except (OSError, RuntimeError, ValueError) as exc:
                                self._log(run_id, f"Falha na publicação: {exc}")
                                self.record_error(run_id, item["folder"],
                                                  f"Falha na publicação: {exc}", [str(exc)])
                    finally:
                        if process.poll() is None:
                            process.kill()
                            process.wait()
        except Exception as exc:
            self._log(run_id, f"Erro de processamento: {exc}")
            with self.lock:
                for item in self.items:
                    if item["status"] in ("waiting", "running"):
                        item.update(status="failed", error=str(exc))
                        self.record_error(run_id, item["folder"], item["error"], [str(exc)])
        finally:
            if summary_dir is not None:
                summary_dir.cleanup()
            with self.lock:
                self.process = None
                self.active = False

    def cancel(self, run_id):
        with self.lock:
            if run_id != self.run_id:
                raise RuntimeError("A execução informada não é a execução atual.")
            self.cancelled.set()
            process = self.process
            for item in self.items:
                if item["status"] == "waiting":
                    item["status"] = "cancelled"
            if process is not None and process.poll() is None:
                try:
                    process.terminate()
                except OSError:
                    pass
                threading.Thread(target=self._reap, args=(process,), daemon=True).start()

    @staticmethod
    def _reap(process):
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except OSError:
                pass
            process.wait()

    def close(self):
        with self.lock:
            self.closing = True
            self.cancel(self.run_id)
            worker = self.worker
        if worker:
            worker.join()

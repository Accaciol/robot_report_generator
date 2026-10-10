"""Fila sequencial de processos, independente das requisições HTTP."""
from __future__ import annotations

import copy
import os
import shutil
import subprocess
import sys
import threading
import uuid
from collections import deque
from datetime import datetime
from pathlib import Path

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
        self.active = False

    def snapshot(self):
        with self.lock:
            return dict(run_id=self.run_id, active=self.active,
                        cancelling=self.active and self.cancelled.is_set(),
                        items=copy.deepcopy(self.items), logs=list(self.logs),
                        errors=list(self.errors))

    def start(self, folders, database):
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
                system_version = source.get("system_version", "não informada") if isinstance(source, dict) else "não informada"
                execution_date = source.get("execution_date") if isinstance(source, dict) else None
                archive_path = source.get("archive_path") if isinstance(source, dict) else None
                cleanup_dir = source.get("cleanup_dir") if isinstance(source, dict) else None
                ident = uuid.uuid4().hex
                self.items.append(dict(id=ident, folder=str(folder), status="waiting",
                                       report_url=f"/public?system={system_id}" if system_id else "/public",
                                       error=None,
                                       system_id=system_id, system_name=system_name,
                                       system_version=system_version, execution_date=execution_date,
                                       archive_path=str(archive_path) if archive_path else None,
                                       cleanup_dir=str(cleanup_dir) if cleanup_dir else None))
            self.active = True
            self.worker = threading.Thread(target=self._run, args=(self.run_id, str(database)), daemon=True)
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

    def _run_item(self, run_id: str, item: dict, database: str) -> None:
        command = [sys.executable, "-u", str(Path(__file__).resolve().parent.parent / "main.py"),
                   "--results-dir", item["folder"], "--database", database,
                   "--system-id", item["system_id"], "--system-name", item["system_name"],
                   "--system-version", item["system_version"], "--no-report"]
        if item["execution_date"]:
            command.extend(["--execution-date", item["execution_date"]])
        if item["archive_path"]:
            command.extend(["--archive-zip", item["archive_path"]])
        with self.lock:
            if self.cancelled.is_set():
                item["status"] = "cancelled"
                return
            item["status"] = "running"
            try:
                self.process = subprocess.Popen(command, stdout=subprocess.PIPE,
                                                stderr=subprocess.STDOUT, text=True,
                                                encoding="utf-8", errors="replace",
                                                env={**os.environ, "PYTHONIOENCODING": "utf-8"})
                process = self.process
            except OSError as exc:
                item.update(status="failed", error=str(exc))
                self._log(run_id, exc)
                self.record_error(run_id, item["folder"], item["error"], [str(exc)])
                return

        self._log(run_id, f"Importando: {item['folder']}")
        item_log = deque(maxlen=80)
        try:
            with process.stdout:
                for line in process.stdout:
                    message = line.rstrip()
                    item_log.append(message[-1000:])
                    self._log(run_id, message)
            code = process.wait()
            with self.lock:
                if self.cancelled.is_set():
                    item["status"] = "cancelled"
                elif code == 0:
                    item["status"] = "completed"
                else:
                    item.update(status="failed", error=f"Importação falhou (código {code}). Consulte o log.")
                if item["status"] == "failed":
                    self.record_error(run_id, item["folder"], item["error"], item_log)
                self.process = None
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()

    def _run(self, run_id, database):
        try:
            for item in self.items:
                try:
                    self._run_item(run_id, item, database)
                finally:
                    cleanup_dir = item.get("cleanup_dir")
                    if cleanup_dir:
                        shutil.rmtree(cleanup_dir, ignore_errors=True)
        except Exception as exc:
            self._log(run_id, f"Erro de processamento: {exc}")
            with self.lock:
                for item in self.items:
                    if item["status"] in ("waiting", "running"):
                        item.update(status="failed", error=str(exc))
                        self.record_error(run_id, item["folder"], item["error"], [str(exc)])
        finally:
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

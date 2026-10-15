"""Run imports sequentially outside the request/response lifecycle."""
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
from typing import Any, Iterable


class JobManager:
    """Coordinate one cancellable import queue and expose its current state."""

    def __init__(self) -> None:
        # RLock permits helper methods to record logs/errors while already locked.
        self.lock = threading.RLock()
        self.cancelled = threading.Event()
        self.worker: threading.Thread | None = None
        self.process: subprocess.Popen | None = None
        self.closing = False
        self.run_id: str | None = None
        self.items: list[dict[str, Any]] = []
        self.logs: deque[str] = deque(maxlen=3000)
        self.errors: deque[dict[str, str]] = deque(maxlen=50)
        self.active = False

    def snapshot(self) -> dict[str, Any]:
        """Return a detached view so API callers cannot mutate live job state."""
        with self.lock:
            return {
                "run_id": self.run_id,
                "active": self.active,
                "cancelling": self.active and self.cancelled.is_set(),
                "items": copy.deepcopy(self.items),
                "logs": list(self.logs),
                "errors": list(self.errors),
            }

    @staticmethod
    def _make_item(source: Path | dict[str, Any]) -> dict[str, Any]:
        """Normalize both folder-only jobs and metadata-rich ZIP imports."""
        if isinstance(source, dict):
            folder = source["path"]
            system_id = source.get("system_id")
            system_name = source.get("name")
            system_version = source.get("system_version", "não informada")
            execution_date = source.get("execution_date")
            archive_path = source.get("archive_path")
            cleanup_dir = source.get("cleanup_dir")
        else:
            folder = source
            system_id = system_name = execution_date = archive_path = cleanup_dir = None
            system_version = "não informada"

        return {
            "id": uuid.uuid4().hex,
            "folder": str(folder),
            "status": "waiting",
            "report_url": f"/public?system={system_id}" if system_id else "/public",
            "error": None,
            "system_id": system_id,
            "system_name": system_name,
            "system_version": system_version,
            "execution_date": execution_date,
            "archive_path": str(archive_path) if archive_path else None,
            "cleanup_dir": str(cleanup_dir) if cleanup_dir else None,
        }

    def start(self, sources: Iterable[Path | dict[str, Any]], database: Path | str) -> str:
        """Start a new sequential import queue and return its identifier."""
        with self.lock:
            if self.active or self.closing:
                raise RuntimeError("Já existe uma execução ativa ou o servidor está encerrando.")

            self.run_id = uuid.uuid4().hex
            self.cancelled.clear()
            self.logs.clear()
            self.items = [self._make_item(source) for source in sources]
            self.active = True
            self.worker = threading.Thread(
                target=self._run,
                args=(self.run_id, str(database)),
                daemon=True,
            )
            self.worker.start()
            return self.run_id

    def _log(self, run_id: str, message: object) -> None:
        with self.lock:
            if run_id == self.run_id:
                self.logs.append(str(message)[-8000:])

    def record_error(
        self,
        run_id: str,
        folder: str | Path,
        message: object,
        lines: Iterable[str],
    ) -> None:
        """Keep concise error context in memory for the current server session."""
        with self.lock:
            self.errors.append({
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "run_id": run_id,
                "folder": str(folder),
                "message": str(message),
                "log": "\n".join(lines)[-12000:],
            })

    @staticmethod
    def _command_for(item: dict[str, Any], database: str) -> list[str]:
        """Build the CLI invocation so web imports share the normal CLI path."""
        project_root = Path(__file__).resolve().parent.parent
        command = [
            sys.executable,
            "-u",
            str(project_root / "main.py"),
            "--results-dir",
            item["folder"],
            "--database",
            database,
            "--system-id",
            item["system_id"],
            "--system-name",
            item["system_name"],
            "--system-version",
            item["system_version"],
            "--no-report",
        ]
        if item["execution_date"]:
            command.extend(["--execution-date", item["execution_date"]])
        if item["archive_path"]:
            command.extend(["--archive-zip", item["archive_path"]])
        return command

    def _run_item(self, run_id: str, item: dict[str, Any], database: str) -> None:
        command = self._command_for(item, database)
        with self.lock:
            if self.cancelled.is_set():
                item["status"] = "cancelled"
                return

            item["status"] = "running"
            try:
                self.process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                )
                process = self.process
            except OSError as exc:
                item.update(status="failed", error=str(exc))
                self._log(run_id, exc)
                self.record_error(run_id, item["folder"], item["error"], [str(exc)])
                return

        self._log(run_id, f"Importando: {item['folder']}")
        item_log: deque[str] = deque(maxlen=80)
        try:
            # Drain stdout continuously so a full OS pipe cannot stall the CLI.
            with process.stdout:
                for line in process.stdout:
                    message = line.rstrip()
                    item_log.append(message[-1000:])
                    self._log(run_id, message)

            return_code = process.wait()
            with self.lock:
                if self.cancelled.is_set():
                    item["status"] = "cancelled"
                elif return_code == 0:
                    item["status"] = "completed"
                else:
                    item.update(
                        status="failed",
                        error=f"Importação falhou (código {return_code}). Consulte o log.",
                    )

                if item["status"] == "failed":
                    self.record_error(run_id, item["folder"], item["error"], item_log)
                self.process = None
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()

    def _run(self, run_id: str, database: str) -> None:
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

    def cancel(self, run_id: str | None) -> None:
        """Stop the active child process and mark queued work as cancelled."""
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
    def _reap(process: subprocess.Popen) -> None:
        """Wait briefly for graceful shutdown, then force-stop the child."""
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except OSError:
                pass
            process.wait()

    def close(self) -> None:
        """Cancel pending work and wait for the worker before server shutdown."""
        with self.lock:
            self.closing = True
            self.cancel(self.run_id)
            worker = self.worker
        if worker:
            worker.join()

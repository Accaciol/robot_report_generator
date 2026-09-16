"""Fila sequencial de processos, independente das requisições HTTP."""
from __future__ import annotations

import copy
import os
import subprocess
import sys
import threading
import uuid
from collections import deque
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
        self.reports = {}
        self.active = False

    def snapshot(self):
        with self.lock:
            return dict(run_id=self.run_id, active=self.active,
                        cancelling=self.active and self.cancelled.is_set(),
                        items=copy.deepcopy(self.items), logs=list(self.logs))

    def start(self, folders, destination, history):
        with self.lock:
            if self.active or self.closing:
                raise RuntimeError("Já existe uma execução ativa ou o servidor está encerrando.")
            self.run_id = uuid.uuid4().hex
            self.cancelled.clear()
            self.logs.clear()
            self.items = []
            for index, folder in enumerate(folders, 1):
                ident = uuid.uuid4().hex
                name = f"relatorio_{index:02d}_{folder.name}_{ident[:8]}.html"
                self.items.append(dict(id=ident, folder=str(folder), status="waiting",
                                       report=str(destination / name), error=None))
            self.active = True
            self.worker = threading.Thread(target=self._run, args=(self.run_id, str(history)), daemon=True)
            self.worker.start()
            return self.run_id

    def _log(self, run_id, message):
        with self.lock:
            if run_id == self.run_id:
                self.logs.append(str(message)[-8000:])

    def _run(self, run_id, history):
        try:
            for item in self.items:
                with self.lock:
                    if self.cancelled.is_set():
                        item["status"] = "cancelled"
                        continue
                    item["status"] = "running"
                    command = [sys.executable, "-u", str(Path(__file__).resolve().parent.parent / "main.py"),
                               "--results-dir", item["folder"], "--history", history,
                               "--report", item["report"]]
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
                        continue
                self._log(run_id, f"Gerando: {item['folder']}")
                try:
                    with process.stdout:
                        for line in process.stdout:
                            self._log(run_id, line.rstrip())
                    code = process.wait()
                    with self.lock:
                        if self.cancelled.is_set():
                            item["status"] = "cancelled"
                        elif code == 0 and Path(item["report"]).is_file():
                            item["status"] = "completed"
                            self.reports[item["id"]] = Path(item["report"])
                        else:
                            item.update(status="failed", error=f"Geração falhou (código {code}). Consulte o log.")
                        self.process = None
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

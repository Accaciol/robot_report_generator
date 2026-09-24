"""Catálogo versionável: resumos ilimitados e um conjunto de evidências por sistema."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile

from core.history_manager import HistoryManager
from core.xml_parser import RobotOutputParser
from models import ExecutionStats, HistoryEntry, ReportData


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value) -> None:
    with path.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        import os
        os.fsync(stream.fileno())


def _timestamp(value) -> str:
    # Datas ausentes não dependem da hora de importação: a ordem é reproduzível.
    normalized = HistoryManager._timestamp(value) if value else "1970-01-01T00:00:00"
    try:
        date = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Data de execução inválida: {normalized}") from exc
    if date.tzinfo:
        date = date.astimezone(timezone.utc).replace(tzinfo=None)
    return date.isoformat(timespec="microseconds")


def _sort(history: list[HistoryEntry]) -> None:
    history.sort(key=lambda entry: (_timestamp(entry.timestamp), entry.execution_id))


class Catalog:
    def __init__(self, root: Path | str):
        self.root = Path(root).expanduser().resolve()

    @staticmethod
    def validate_id(system_id: str) -> None:
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", system_id):
            raise ValueError("Identificador do sistema: use letras minúsculas, números e hífens.")

    def _directory(self, system_id: str) -> Path:
        self.validate_id(system_id)
        path = self.root / system_id
        if path.is_symlink():
            raise ValueError("A pasta do sistema não pode ser um link simbólico.")
        # Uma interrupção entre as renomeações ainda permite ler o último estado.
        backup = self.root / f".{system_id}.backup"
        return path if path.exists() else backup if backup.exists() else path

    @contextmanager
    def _writer(self):
        self.root.mkdir(parents=True, exist_ok=True)
        with (self.root / ".catalog.lock").open("a+b") as lock:
            lock.seek(0)
            if not lock.read(1):
                lock.write(b"0")
                lock.flush()
            lock.seek(0)
            import os
            if os.name == "nt":
                import msvcrt
                acquire = lambda: msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                release = lambda: msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                acquire = lambda: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                release = lambda: fcntl.flock(lock, fcntl.LOCK_UN)
            try:
                acquire()
            except OSError as exc:
                raise ValueError("Outra atualização do catálogo está em andamento.") from exc
            try:
                yield
            finally:
                release()

    def load(self, system_id: str) -> tuple[dict, list[HistoryEntry], Path]:
        directory = self._directory(system_id)
        if not directory.is_dir():
            raise ValueError(f"Sistema inexistente: {system_id}")
        try:
            metadata = _read_json(directory / "system.json")
            history = [HistoryEntry(**entry) for entry in _read_json(directory / "history.json")]
            if metadata["schema_version"] != 1 or metadata["id"] != system_id:
                raise ValueError("Identificação ou versão de catálogo inválida.")
            if not isinstance(metadata["name"], str) or not metadata["name"].strip():
                raise ValueError("Nome do sistema inválido.")
            ids = [entry.execution_id for entry in history]
            if any(not entry_id for entry_id in ids) or len(ids) != len(set(ids)):
                raise ValueError("Identificadores de execução ausentes ou duplicados.")
            if metadata["current_execution_id"] is not None and metadata["current_execution_id"] not in ids:
                raise ValueError("Referência de evidências sem execução correspondente.")
            _sort(history)
            if metadata["current_execution_id"] is not None and metadata["current_execution_id"] != history[-1].execution_id:
                raise ValueError("As evidências devem pertencer à execução mais recente.")
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Catálogo inválido para {system_id}: {exc}") from exc
        return metadata, history, directory

    def systems(self) -> list[tuple[dict, list[HistoryEntry], Path]]:
        if not self.root.is_dir():
            raise ValueError(f"Catálogo não encontrado: {self.root}")
        ids = {path.name for path in self.root.iterdir() if path.is_dir() and not path.name.startswith(".")}
        ids.update(path.name[1:-7] for path in self.root.glob(".*.backup") if path.is_dir())
        return sorted((self.load(system_id) for system_id in ids),
                      key=lambda item: (item[0]["name"].casefold(), item[0]["id"]))

    def _commit(self, system_id: str, staged: Path) -> None:
        """Troca o diretório preparado; restaura o anterior se a promoção falhar."""
        destination = self.root / system_id
        backup = self.root / f".{system_id}.backup"
        if backup.exists():
            if destination.exists():
                shutil.rmtree(backup)
            else:
                backup.rename(destination)
        if destination.exists():
            destination.rename(backup)
        try:
            staged.rename(destination)
        except OSError:
            if backup.exists():
                backup.rename(destination)
            raise
        # A promoção concluiu a transação. Se a limpeza falhar, a próxima escrita
        # remove o backup; leitores sempre preferem o diretório já promovido.
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)

    def import_results(self, source: Path | str, system_id: str, name: str | None = None,
                       legacy_history: Path | None = None) -> str:
        self.validate_id(system_id)
        source = Path(source).expanduser().resolve()
        if source == self.root or source in self.root.parents or self.root in source.parents:
            raise ValueError("A origem não pode se sobrepor ao catálogo. Copie-a para uma pasta externa.")
        if not (source / "output.xml").is_file():
            raise ValueError("A pasta de origem precisa conter output.xml.")
        if name is not None and not name.strip():
            raise ValueError("O nome do sistema não pode estar vazio.")
        with self._writer(), tempfile.TemporaryDirectory(prefix=".stage-", dir=self.root) as temporary:
            staged = Path(temporary) / "system"
            staged.mkdir()
            incoming = Path(temporary) / "incoming"
            shutil.copytree(source, incoming)
            parser = RobotOutputParser(str(incoming / "output.xml"))
            suites, stats = parser.parse()
            execution_id = hashlib.sha256((incoming / "output.xml").read_bytes()).hexdigest()
            timestamp = _timestamp(parser.execution_start)
            entry = HistoryEntry(timestamp=timestamp, total=stats.total, passed=stats.passed,
                                 failed=stats.failed, skipped=stats.skipped,
                                 elapsed_s=round(stats.elapsed_s, 2), pass_rate=stats.pass_rate,
                                 version=f"{timestamp[:19]} · {execution_id[:8]}",
                                 tests=HistoryManager._test_snapshots(suites), execution_id=execution_id)
            existing = self._directory(system_id)
            if legacy_history is not None and existing.exists():
                raise ValueError("Migração requer um identificador de sistema ainda não cadastrado.")
            if existing.exists():
                metadata, history, _ = self.load(system_id)
            else:
                metadata = {"schema_version": 1, "id": system_id, "name": name or system_id,
                            "current_execution_id": None}
                history = []
            if name is not None:
                metadata["name"] = name.strip()
            if legacy_history is not None:
                raw = _read_json(legacy_history)
                if not isinstance(raw, list):
                    raise ValueError("Histórico legado deve ser uma lista de execuções.")
                for index, value in enumerate(raw):
                    old = HistoryEntry(**value)
                    old.timestamp = _timestamp(old.timestamp)
                    # O histórico antigo não tem hashes. Só a correspondência exata
                    # de data (até segundos), métricas e snapshots identifica o XML.
                    if (old.timestamp[:19] == entry.timestamp[:19]
                            and all(getattr(old, key) == getattr(entry, key) for key in
                                    ("total", "passed", "failed", "skipped", "elapsed_s", "tests"))):
                        continue
                    payload = json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
                    old.execution_id = "legacy-" + hashlib.sha256(str(index).encode() + payload).hexdigest()
                    history.append(old)
            if not any(old.execution_id == execution_id for old in history):
                history.append(entry)
            _sort(history)
            if history[-1].execution_id == execution_id:
                for filename in ("log.html", "report.html"):
                    path = incoming / filename
                    if path.is_file():
                        path.unlink()
                incoming.rename(staged / "current")
                metadata["current_execution_id"] = execution_id
            elif metadata["current_execution_id"]:
                shutil.copytree(existing / "current", staged / "current")
            _write_json(staged / "system.json", metadata)
            _write_json(staged / "history.json", [asdict(item) for item in history])
            self._commit(system_id, staged)
        return execution_id

    def remove(self, system_id: str, execution_id: str) -> None:
        self.validate_id(system_id)
        with self._writer():
            metadata, history, directory = self.load(system_id)
            remaining = [entry for entry in history if entry.execution_id != execution_id]
            if len(remaining) == len(history):
                raise ValueError(f"Execução inexistente em {system_id}: {execution_id}")
            with tempfile.TemporaryDirectory(prefix=".stage-", dir=self.root) as temporary:
                staged = Path(temporary) / "system"
                staged.mkdir()
                if metadata["current_execution_id"] == execution_id:
                    metadata["current_execution_id"] = None
                elif metadata["current_execution_id"]:
                    shutil.copytree(directory / "current", staged / "current")
                _write_json(staged / "system.json", metadata)
                _write_json(staged / "history.json", [asdict(entry) for entry in remaining])
                self._commit(system_id, staged)

    def report_data(self, metadata: dict, history: list[HistoryEntry], directory: Path,
                    title: str, issue_url: str = "") -> ReportData:
        latest = history[-1] if history else None
        stats = ExecutionStats(**{key: getattr(latest, key) for key in
                                 ("total", "passed", "failed", "skipped", "elapsed_s")}) if latest else ExecutionStats()
        suites, errors, environment = [], [], {}
        current_id = metadata["current_execution_id"]
        if current_id:
            xml = directory / "current" / "output.xml"
            if not xml.is_file() or hashlib.sha256(xml.read_bytes()).hexdigest() != current_id:
                raise ValueError(f"Outputs de {metadata['id']} ausentes ou alterados; reimporte a execução.")
            parser = RobotOutputParser(str(xml))
            suites, _ = parser.parse()
            errors, environment = parser.errors, parser.environment
        return ReportData(stats=stats, suites=suites, history=history,
                          title=f"{title} — {metadata['name']}",
                          generated_at=datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                          version=latest.version if latest else "sem execuções",
                          errors=errors, environment=environment,
                          flaky_tests=HistoryManager.detect_flaky_tests(history),
                          delta_stats=HistoryManager.compute_delta_stats(stats, history),
                          issue_url_pattern=issue_url, detailed_execution_id=current_id or "")

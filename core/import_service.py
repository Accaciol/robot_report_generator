"""Safe ZIP/folder ingestion shared by the web interface and CLI."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import threading
import time
import zipfile
from typing import Any, BinaryIO

from core.sqlite_store import SQLiteStore
from core.xml_parser import RobotOutputParser


DEFAULT_MAX_UPLOAD_BYTES = 500 * 1024 * 1024
DEFAULT_MAX_UNPACKED_BYTES = 1024 * 1024 * 1024
MAX_ZIP_MEMBERS = 10_000
PENDING_TTL_SECONDS = 30 * 60


def _is_directory(member: zipfile.ZipInfo) -> bool:
    mode = member.external_attr >> 16
    dos_attributes = member.external_attr & 0xFFFF
    return member.is_dir() or stat.S_ISDIR(mode) or bool(dos_attributes & 0x10)


def _configured_limit(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, default))
    except ValueError as exc:
        raise ValueError(f"Configuração inválida: {name}") from exc
    if value <= 0:
        raise ValueError(f"Configuração inválida: {name}")
    return value


def extract_archive(
    archive: Path,
    destination: Path,
    max_upload_bytes: int | None = None,
    max_unpacked_bytes: int | None = None,
) -> None:
    """Validate ZIP contents before extracting files into the staging folder."""
    upload_limit = max_upload_bytes or _configured_limit(
        "ROBOT_REPORT_MAX_UPLOAD_BYTES",
        DEFAULT_MAX_UPLOAD_BYTES,
    )
    unpacked_limit = max_unpacked_bytes or _configured_limit(
        "ROBOT_REPORT_MAX_UNPACKED_BYTES", DEFAULT_MAX_UNPACKED_BYTES)
    if not archive.is_file():
        raise ValueError("Arquivo ZIP não encontrado.")
    if archive.stat().st_size > upload_limit:
            size_limit_mib = upload_limit // (1024 * 1024)
            raise ValueError(f"ZIP excede o limite de {size_limit_mib} MiB.")
    try:
        with zipfile.ZipFile(archive) as bundle:
            members = bundle.infolist()
            if len(members) > MAX_ZIP_MEMBERS:
                raise ValueError("ZIP contém arquivos demais.")
            seen: set[str] = set()
            total_size = 0
            for member in members:
                name = member.filename
                path = PurePosixPath(name)
                parts = name.rstrip("/").split("/")
                if (
                    not name
                    or "\\" in name
                    or path.is_absolute()
                    or any(part in ("", ".", "..") for part in parts)
                    or (path.parts and ":" in path.parts[0])
                ):
                    raise ValueError(f"Caminho inseguro no ZIP: {name}")
                normalized = str(path)
                if normalized in seen:
                    raise ValueError(f"Caminho duplicado no ZIP: {name}")
                seen.add(normalized)
                mode = member.external_attr >> 16
                is_directory = _is_directory(member)
                if stat.S_IFMT(mode) and not (
                    stat.S_ISREG(mode) or stat.S_ISDIR(mode)
                ):
                    raise ValueError(f"Tipo de arquivo não permitido no ZIP: {name}")
                if not is_directory:
                    total_size += member.file_size
                    if total_size > unpacked_limit:
                        raise ValueError("Conteúdo descompactado excede o limite configurado.")
            root_output = any(
                member.filename == "output.xml" and not _is_directory(member)
                for member in members
            )
            strip_prefix = None
            if not root_output:
                candidates = {
                    member.filename[:-len("/output.xml")]
                    for member in members
                    if member.filename.endswith("/output.xml")
                    and member.filename.count("/") == 1
                    and not _is_directory(member)
                }
                candidates = {
                    prefix for prefix in candidates
                    if all(
                        member.filename.rstrip("/") == prefix
                        or member.filename.startswith(prefix + "/")
                        for member in members
                    )
                }
                if len(candidates) == 1:
                    strip_prefix = candidates.pop()
            if not root_output and strip_prefix is None:
                raise ValueError(
                    "O ZIP deve conter output.xml na raiz ou dentro de uma única pasta."
                )
            destination.mkdir(parents=True, exist_ok=True)
            for member in members:
                member_name = member.filename
                if strip_prefix is not None:
                    if member_name.rstrip("/") == strip_prefix:
                        continue
                    member_name = member_name[len(strip_prefix) + 1:]
                target = destination.joinpath(*PurePosixPath(member_name).parts)
                if _is_directory(member):
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with bundle.open(member) as source, target.open("wb") as output:
                        shutil.copyfileobj(source, output, length=1024 * 1024)
    except zipfile.BadZipFile as exc:
        raise ValueError("ZIP inválido ou corrompido.") from exc


def _archive_directory(source: Path, archive: Path) -> None:
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(source.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"Link simbólico não permitido nos resultados: {path}")
            if path.is_file():
                bundle.write(path, path.relative_to(source).as_posix())


def _execution_fingerprint(output_xml: Path) -> str:
    """Use the XML content as a stable deduplication key for a run."""
    return hashlib.sha256(output_xml.read_bytes()).hexdigest()


@dataclass
class PreparedImport:
    """A validated upload waiting for the user to confirm its metadata."""

    upload_id: str
    stage_dir: Path
    archive: Path
    results_dir: Path
    parser: RobotOutputParser
    created_at: float


class ImportService:
    """Own temporary uploads and pass confirmed imports to SQLite storage."""

    def __init__(self, database: Path | str | None = None) -> None:
        self.store = SQLiteStore(database)
        self.pending: dict[str, PreparedImport] = {}
        self.lock = threading.RLock()

    def _new_stage(self) -> Path:
        # Staging shares the artifacts filesystem so the final move is atomic.
        return Path(tempfile.mkdtemp(prefix=".pending-", dir=self.store.artifacts_root))

    def _cleanup_expired(self) -> None:
        cutoff = time.time() - PENDING_TTL_SECONDS
        for upload_id, item in list(self.pending.items()):
            if item.created_at < cutoff:
                shutil.rmtree(item.stage_dir, ignore_errors=True)
                self.pending.pop(upload_id, None)

    def prepare_upload(self, stream: BinaryIO, filename: str = "results.zip") -> dict[str, Any]:
        del filename  # The server chooses storage paths; client filenames are never trusted.
        with self.lock:
            self._cleanup_expired()
            stage = self._new_stage()
            archive = stage / "original.zip"
            total = 0
            limit = _configured_limit("ROBOT_REPORT_MAX_UPLOAD_BYTES", DEFAULT_MAX_UPLOAD_BYTES)
            try:
                with archive.open("wb") as output:
                    while chunk := stream.read(1024 * 1024):
                        total += len(chunk)
                        if total > limit:
                            size_limit_mib = limit // (1024 * 1024)
                            raise ValueError(
                                f"ZIP excede o limite de {size_limit_mib} MiB."
                            )
                        output.write(chunk)
                results_dir = stage / "results"
                extract_archive(archive, results_dir)
                parser = RobotOutputParser(str(results_dir / "output.xml"))
                suites, stats = parser.parse()
                upload_id = hashlib.sha256(
                    os.urandom(32) + str(time.time_ns()).encode()
                ).hexdigest()
                prepared = PreparedImport(
                    upload_id,
                    stage,
                    archive,
                    results_dir,
                    parser,
                    time.time(),
                )
                self.pending[upload_id] = prepared
                files = [path for path in results_dir.rglob("*") if path.is_file()]
                evidence_count = sum(path.name != "output.xml" for path in files)
                return {
                    "upload_id": upload_id,
                    "execution_date": parser.execution_start,
                    **parser.system_metadata,
                    "archive_members": len(files),
                    "evidence_files": evidence_count,
                    "output_xml": "output.xml",
                    "total": stats.total,
                    "passed": stats.passed,
                    "failed": stats.failed,
                    "skipped": stats.skipped,
                    "errors": parser.errors,
                }
            except Exception:
                shutil.rmtree(stage, ignore_errors=True)
                raise

    def commit_upload(
        self,
        upload_id: str,
        system_id: str,
        system_name: str,
        system_version: str,
        execution_date: str | None = None,
    ) -> dict[str, Any]:
        with self.lock:
            self._cleanup_expired()
            prepared = self.pending.get(upload_id)
            if prepared is None:
                raise ValueError("Upload expirado ou inexistente. Envie o ZIP novamente.")
            timestamp = execution_date or prepared.parser.execution_start
            if not timestamp:
                raise ValueError(
                    "Informe a data e hora da execução; o XML não contém essa informação."
                )
            suites, stats = prepared.parser.parse()
            execution_id = _execution_fingerprint(prepared.results_dir / "output.xml")
            try:
                inserted, history = self.store.add_execution(
                    system_id,
                    system_name,
                    system_version,
                    timestamp,
                    suites,
                    stats,
                    execution_id,
                    staged_bundle=prepared.stage_dir,
                )
                return {
                    "inserted": inserted,
                    "execution_id": execution_id,
                    "history": history,
                    "system_id": system_id,
                    "system_version": system_version,
                    "execution_date": timestamp,
                    "parser": prepared.parser,
                    "suites": suites,
                    "stats": stats,
                    "results_dir": self.store.artifacts_root / system_id / execution_id / "results",
                    "archive": prepared.archive,
                }
            finally:
                self.pending.pop(upload_id, None)
                if prepared.stage_dir.exists():
                    shutil.rmtree(prepared.stage_dir, ignore_errors=True)

    def consume_upload(self, upload_id: str) -> PreparedImport:
        """Transfer a staged upload to the background worker."""
        with self.lock:
            self._cleanup_expired()
            prepared = self.pending.pop(upload_id, None)
            if prepared is None:
                raise ValueError("Upload expirado ou inexistente. Envie o ZIP novamente.")
            return prepared

    def import_source(
        self,
        source: Path | str,
        system_id: str,
        system_name: str,
        system_version: str,
        execution_date: str | None = None,
        archive_source: Path | str | None = None,
        output_xml: Path | str | None = None,
    ) -> dict[str, Any]:
        source = Path(source).expanduser().resolve()
        stage = self._new_stage()
        archive = stage / "original.zip"
        results_dir = stage / "results"
        try:
            if source.is_file():
                shutil.copyfile(source, archive)
                extract_archive(archive, results_dir)
            elif source.is_dir():
                selected_xml = (
                    Path(output_xml).expanduser().resolve()
                    if output_xml
                    else source / "output.xml"
                )
                if not selected_xml.is_file():
                    raise ValueError("A pasta de origem precisa conter output.xml.")
                shutil.copytree(source, results_dir)
                if selected_xml != results_dir / "output.xml":
                    shutil.copyfile(selected_xml, results_dir / "output.xml")
                if archive_source is not None:
                    shutil.copyfile(Path(archive_source), archive)
                else:
                    _archive_directory(results_dir, archive)
            else:
                raise ValueError("Informe uma pasta de resultados ou arquivo ZIP.")
            parser = RobotOutputParser(str(results_dir / "output.xml"))
            suites, stats = parser.parse()
            timestamp = execution_date or parser.execution_start
            if not timestamp:
                raise ValueError(
                    "Informe a data e hora da execução; o XML não contém essa informação."
                )
            execution_id = _execution_fingerprint(results_dir / "output.xml")
            inserted, history = self.store.add_execution(
                system_id,
                system_name,
                system_version,
                timestamp,
                suites,
                stats,
                execution_id,
                staged_bundle=stage,
            )
            return {
                "inserted": inserted,
                "execution_id": execution_id,
                "history": history,
                "system_id": system_id,
                "system_version": system_version,
                "execution_date": timestamp,
                "parser": parser,
                "suites": suites,
                "stats": stats,
                "results_dir": self.store.artifacts_root / system_id / execution_id / "results",
            }
        finally:
            if stage.exists():
                shutil.rmtree(stage, ignore_errors=True)

    def close(self) -> None:
        with self.lock:
            for item in self.pending.values():
                shutil.rmtree(item.stage_dir, ignore_errors=True)
            self.pending.clear()

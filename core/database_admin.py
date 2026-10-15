"""Backup, restoration, and artifact maintenance for the report database."""
from __future__ import annotations

import shutil
import sqlite3
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from core.sqlite_store import SQLiteStore


def _validate_archive_member(name: str, mode: int, seen: set[str]) -> PurePosixPath:
    """Reject paths that could escape staging or be extracted more than once."""
    path = PurePosixPath(name)
    invalid_path = (
        not name
        or "\\" in name
        or path.is_absolute()
        or any(part in ("", ".", "..") for part in path.parts)
        or name in seen
    )
    invalid_type = stat.S_IFMT(mode) and not (
        stat.S_ISREG(mode) or stat.S_ISDIR(mode)
    )
    if invalid_path or invalid_type:
        raise ValueError("O pacote de backup contém um caminho ou arquivo inválido.")
    return path


def create_full_backup(database: Path | str, destination: Path | str) -> Path:
    """Write a ZIP containing a consistent SQLite snapshot and stored artifacts."""
    store = SQLiteStore(database)
    output = Path(destination)
    output.parent.mkdir(parents=True, exist_ok=True)
    database_copy = output.parent / "report_history.sqlite3"
    try:
        store.backup_to(database_copy)
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(database_copy, "report_history.sqlite3")
            for path in sorted(store.artifacts_root.rglob("*")):
                if any(part.startswith(".pending-") for part in path.parts):
                    continue
                if path.is_file() and not path.is_symlink():
                    relative = Path("executions") / path.relative_to(store.artifacts_root)
                    archive.write(path, relative.as_posix())
    finally:
        database_copy.unlink(missing_ok=True)
    return output


def restore_full_backup(database: Path | str, archive_path: Path | str) -> int:
    """Validate and restore a full backup; roll back the artifact tree on failure."""
    database = Path(database).expanduser().resolve()
    store = SQLiteStore(database)
    archive_path = Path(archive_path)
    staging = Path(tempfile.mkdtemp(prefix=".restore-", dir=database.parent))
    try:
        database_copy = staging / "report_history.sqlite3"
        artifact_copy = staging / "executions"
        artifact_copy.mkdir()
        unpacked = 0
        seen = set()
        try:
            with zipfile.ZipFile(archive_path) as archive:
                for member in archive.infolist():
                    name = member.filename
                    path = PurePosixPath(name)
                    mode = member.external_attr >> 16
                    path = _validate_archive_member(name, mode, seen)
                    seen.add(name)
                    unpacked += member.file_size
                    if unpacked > 2 * 1024 * 1024 * 1024:
                        raise ValueError("O backup descompactado excede 2 GiB.")
                    if name == "report_history.sqlite3":
                        target = database_copy
                    elif path.parts and path.parts[0] == "executions":
                        target = staging.joinpath(*path.parts)
                    else:
                        raise ValueError(
                            "O pacote não corresponde ao formato de backup do Robot Reports."
                        )
                    if member.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(member) as source, target.open("wb") as output:
                            shutil.copyfileobj(source, output)
        except zipfile.BadZipFile as exc:
            raise ValueError("O arquivo selecionado não é um ZIP válido.") from exc

        if not database_copy.is_file():
            raise ValueError("O pacote não contém o banco report_history.sqlite3.")

        # Validate the SQLite file before replacing anything on disk.
        validation = sqlite3.connect(f"file:{database_copy}?mode=ro", uri=True)
        try:
            integrity = validation.execute("PRAGMA integrity_check").fetchone()[0]
            tables = {row[0] for row in validation.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            version = validation.execute("PRAGMA user_version").fetchone()[0]
            if (integrity != "ok" or version not in (1, SQLiteStore.SCHEMA_VERSION)
                    or not {"systems", "executions", "test_snapshots"}.issubset(tables)):
                raise ValueError("O banco dentro do backup não é válido para o Robot Reports.")
        finally:
            validation.close()

        database_rollback = staging / "previous.sqlite3"
        store.backup_to(database_rollback)
        artifacts_rollback = staging / "previous-executions"
        if store.artifacts_root.exists():
            store.artifacts_root.replace(artifacts_rollback)
        try:
            artifact_copy.replace(store.artifacts_root)
            store.restore_from(database_copy)
        except Exception:
            if store.artifacts_root.exists():
                shutil.rmtree(store.artifacts_root, ignore_errors=True)
            if artifacts_rollback.exists():
                artifacts_rollback.replace(store.artifacts_root)
            store.restore_from(database_rollback)
            raise
        return len(store.systems())
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def orphaned_artifacts(database: Path | str) -> list[str]:
    return SQLiteStore(database).cleanup_orphaned_artifacts()


def cleanup_orphaned_artifacts(database: Path | str) -> list[str]:
    return SQLiteStore(database).cleanup_orphaned_artifacts(delete=True)

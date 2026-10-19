"""Artifact maintenance for the report database."""
from __future__ import annotations

from pathlib import Path, PurePosixPath

from core.sqlite_store import SQLiteStore


def orphaned_artifacts(database: Path | str) -> list[str]:
    return SQLiteStore(database).cleanup_orphaned_artifacts()


def cleanup_orphaned_artifacts(database: Path | str) -> list[str]:
    return SQLiteStore(database).cleanup_orphaned_artifacts(delete=True)

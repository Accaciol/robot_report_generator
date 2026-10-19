"""Application services used by the local web interface.

These functions validate and prepare data without depending on Flask request or
response objects. Keeping that boundary makes the rules easier to reuse from
the command line and easier to review independently from HTTP handling.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from core.catalog_overview import overview
from core.sqlite_store import SQLiteStore


def catalog_systems(database: Path) -> list[dict[str, str | int]]:
    """Return the fields needed by system selectors in the local interface."""
    entries = SQLiteStore(database).systems()
    return [
        {
            "id": metadata["id"],
            "name": metadata["name"],
            "executions": len(history),
            "system_version": history[-1].system_version if history else "",
        }
        for metadata, history, _ in entries
    ]


def catalog_overview(database: Path, period: str) -> dict[str, Any]:
    """Build aggregate metrics for the requested reporting period."""
    return overview(SQLiteStore(database).systems(), period)


def list_history(database: Path, system_id: str) -> list[dict[str, Any]]:
    """Return searchable execution summaries for one system."""
    _, entries, _ = SQLiteStore(database).load(system_id)
    return [
        {
            "index": index,
            "execution_id": entry.execution_id,
            "timestamp": entry.timestamp,
            "version": entry.version,
            "system_version": entry.system_version,
            "total": entry.total,
            "passed": entry.passed,
            "failed": entry.failed,
            "skipped": entry.skipped,
            "pass_rate": entry.pass_rate,
        }
        for index, entry in enumerate(entries)
    ]


def remove_history(database: Path, system_id: str, execution_id: str) -> None:
    """Remove an execution and its stored artifacts when present."""
    SQLiteStore(database).remove_execution(system_id, execution_id)

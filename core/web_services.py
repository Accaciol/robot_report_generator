"""Application services used by the local web interface.

These functions validate and prepare data without depending on Flask request or
response objects. Keeping that boundary makes the rules easier to reuse from
the command line and easier to review independently from HTTP handling.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from core.catalog_overview import overview
from core.sqlite_store import SQLiteStore


def resolve_path(value: object) -> Path:
    """Expand a user-supplied path and reject empty or non-string values."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Informe um caminho válido.")
    return Path(value).expanduser().resolve()


def require_writable_directory(path: Path) -> None:
    """Raise a clear error when the destination cannot accept report files."""
    if not path.is_dir():
        raise ValueError(f"Pasta não encontrada: {path}")
    with tempfile.TemporaryFile(dir=path):
        pass


def list_folders(path: Path) -> dict[str, Any]:
    """Return child folders in a stable, case-insensitive order."""
    children = sorted(
        (child for child in path.iterdir() if child.is_dir()),
        key=lambda child: child.name.casefold(),
    )
    return {
        "path": str(path),
        "parent": str(path.parent),
        "has_output": (path / "output.xml").is_file(),
        "folders": [{"name": child.name, "path": str(child)} for child in children],
    }


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


def validate_run_request(data: object) -> tuple[list[dict[str, Any]], Path]:
    """Validate a batch import request and return normalized source records."""
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("folders"), list)
        or not data["folders"]
    ):
        raise ValueError("Adicione pelo menos uma pasta de resultados.")

    system_id = data.get("system_id")
    SQLiteStore.validate_system_id(system_id)
    system_name = data.get("system_name")
    system_version = data.get("system_version")
    if not isinstance(system_name, str) or not system_name.strip():
        raise ValueError("Informe o nome do sistema.")
    if not isinstance(system_version, str) or not system_version.strip():
        raise ValueError("Informe a versão do produto.")

    sources = []
    seen_paths = set()
    for item in data["folders"]:
        value = item.get("path") if isinstance(item, dict) else item
        path = resolve_path(value)
        if not (path / "output.xml").is_file():
            raise ValueError(f"output.xml não encontrado em: {path}")
        # A repeated folder should be imported once, even if selected more than once.
        if path in seen_paths:
            continue
        seen_paths.add(path)
        sources.append(
            {
                "path": path,
                "system_id": system_id,
                "system_name": system_name.strip(),
                "system_version": system_version.strip(),
                "execution_date": None,
            }
        )

    destination = resolve_path(data.get("destination"))
    require_writable_directory(destination)
    return sources, destination

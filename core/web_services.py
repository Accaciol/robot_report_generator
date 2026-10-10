"""HTTP-independent operations for local report imports and catalog queries."""
from __future__ import annotations

import tempfile
from pathlib import Path

from core.catalog_overview import overview
from core.sqlite_store import SQLiteStore


def resolve_path(value: object) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Informe um caminho válido.")
    return Path(value).expanduser().resolve()


def require_writable_directory(path: Path) -> None:
    if not path.is_dir():
        raise ValueError(f"Pasta não encontrada: {path}")
    with tempfile.TemporaryFile(dir=path):
        pass


def list_folders(path: Path) -> dict[str, object]:
    children = sorted((child for child in path.iterdir() if child.is_dir()),
                      key=lambda child: child.name.casefold())
    return {"path": str(path), "parent": str(path.parent),
            "has_output": (path / "output.xml").is_file(),
            "folders": [{"name": child.name, "path": str(child)} for child in children]}


def catalog_systems(database: Path) -> list[dict[str, str | int]]:
    entries = SQLiteStore(database).systems()
    return [{"id": metadata["id"], "name": metadata["name"], "executions": len(history),
             "system_version": history[-1].system_version if history else ""}
            for metadata, history, _ in entries]


def catalog_overview(database: Path, period: str) -> dict[str, object]:
    return overview(SQLiteStore(database).systems(), period)


def list_history(database: Path, system_id: str) -> list[dict[str, int | float | str]]:
    _, entries, _ = SQLiteStore(database).load(system_id)
    return [dict(index=index, execution_id=entry.execution_id, timestamp=entry.timestamp,
                 version=entry.version, system_version=entry.system_version,
                 total=entry.total, passed=entry.passed, failed=entry.failed,
                 skipped=entry.skipped, pass_rate=entry.pass_rate)
            for index, entry in enumerate(entries)]


def remove_history(database: Path, system_id: str, execution_id: str) -> None:
    SQLiteStore(database).remove_execution(system_id, execution_id)


def validate_run_request(data: object) -> tuple[list[dict], Path]:
    if not isinstance(data, dict) or not isinstance(data.get("folders"), list) or not data["folders"]:
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
    seen = set()
    for value in data["folders"]:
        path = resolve_path(value.get("path") if isinstance(value, dict) else value)
        if not (path / "output.xml").is_file():
            raise ValueError(f"output.xml não encontrado em: {path}")
        if path not in seen:
            sources.append({"path": path, "system_id": system_id, "system_name": system_name.strip(),
                            "system_version": system_version.strip(), "execution_date": None})
            seen.add(path)
    destination = resolve_path(data.get("destination"))
    require_writable_directory(destination)
    return sources, destination

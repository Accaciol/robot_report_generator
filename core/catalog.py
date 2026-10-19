"""SQLite-backed compatibility facade for catalog operations."""
from __future__ import annotations

from pathlib import Path

from core.import_service import ImportService
from core.sqlite_store import SQLiteStore
from models import HistoryEntry, ReportData


class Catalog:
    """Expose catalog operations while storing all persistent data in SQLite."""

    def __init__(self, root: Path | str):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.database = self.root / "report_history.sqlite3"
        self.store = SQLiteStore(self.database)

    @staticmethod
    def validate_id(system_id: str) -> None:
        SQLiteStore.validate_system_id(system_id)

    def load(self, system_id: str):
        return self.store.load(system_id)

    def systems(self):
        return self.store.systems()

    def import_results(
        self,
        source: Path | str,
        system_id: str,
        name: str | None = None,
    ) -> str:
        self.validate_id(system_id)
        display_name = (name or system_id).strip()
        result = ImportService(self.database).import_source(
            source, system_id, display_name, "não informada"
        )
        return str(result["execution_id"])

    def remove(self, system_id: str, execution_id: str) -> None:
        self.store.remove_execution(system_id, execution_id)

    def report_data(
        self,
        metadata: dict,
        history: list[HistoryEntry],
        directory: Path,
        title: str,
        issue_url: str = "",
    ) -> ReportData:
        current_metadata, current_history, current_directory = self.store.load(metadata["id"])
        return self.store.report_data(
            current_metadata, current_history, current_directory, title, issue_url
        )

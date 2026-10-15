"""SQLite-backed compatibility facade for catalog operations."""
from __future__ import annotations

import json
from pathlib import Path

from core.history_manager import HistoryManager
from core.import_service import ImportService
from core.sqlite_store import SQLiteStore
from core.xml_parser import RobotOutputParser
from models import HistoryEntry, ReportData


class Catalog:
    """Expose catalog operations while storing all persistent data in SQLite.

    ``root`` remains a directory for compatibility with older callers. Existing
    JSON catalogs can be migrated explicitly with :meth:`migrate_legacy`.
    """

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
        legacy_history: Path | None = None,
    ) -> str:
        self.validate_id(system_id)
        display_name = (name or system_id).strip()
        if legacy_history is not None:
            entries = self._read_legacy_history(legacy_history)
            output = Path(source) / "output.xml"
            if output.is_file():
                parser = RobotOutputParser(str(output))
                suites, stats = parser.parse()
                timestamp = HistoryManager._timestamp(parser.execution_start)
                snapshots = HistoryManager._test_snapshots(suites)
                entries = [entry for entry in entries if not (
                    HistoryManager._timestamp(entry.timestamp)[:19] == timestamp[:19]
                    and (entry.total, entry.passed, entry.failed, entry.skipped,
                         round(entry.elapsed_s, 2), entry.tests)
                    == (stats.total, stats.passed, stats.failed, stats.skipped,
                        round(stats.elapsed_s, 2), snapshots)
                )]
            self.store.import_history_entries(system_id, display_name, entries)
        result = ImportService(self.database).import_source(
            source, system_id, display_name, "não informada"
        )
        return str(result["execution_id"])

    def migrate_legacy(self, system_id: str | None = None) -> int:
        """Copy legacy per-system JSON catalogs into SQLite without deleting them."""
        folders = ([self.root / system_id] if system_id else
                   [item for item in self.root.iterdir()
                    if item.is_dir() and not item.name.startswith(".")])
        migrated = 0
        for folder in folders:
            metadata_path = folder / "system.json"
            history_path = folder / "history.json"
            if not metadata_path.is_file() or not history_path.is_file():
                continue
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            current = folder / "current"
            if (current / "output.xml").is_file():
                before = len(self.store.history(str(metadata["id"]))) if self._has_system(
                    str(metadata["id"])
                ) else 0
                self.import_results(current, str(metadata["id"]), str(metadata["name"]), history_path)
                migrated += len(self.store.history(str(metadata["id"]))) - before
            else:
                legacy_entries = self._read_legacy_history(history_path)
                migrated += self.store.import_history_entries(
                    str(metadata["id"]), str(metadata["name"]), legacy_entries
                )
        return migrated

    def _has_system(self, system_id: str) -> bool:
        return any(metadata["id"] == system_id for metadata, _, _ in self.store.systems())

    @staticmethod
    def _read_legacy_history(path: Path | str) -> list[HistoryEntry]:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError("Histórico legado deve ser uma lista de execuções.")
        return [HistoryEntry(**item) for item in raw]

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

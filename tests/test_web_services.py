import tempfile
import unittest
from pathlib import Path

from core.import_service import ImportService
from core.sqlite_store import SQLiteStore
from core.web_services import (
    catalog_overview,
    catalog_systems,
    list_history,
    remove_history,
)


ROOT = Path(__file__).resolve().parent.parent


class TestWebServices(unittest.TestCase):
    def test_catalog_views_and_history_removal_use_sqlite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "reports.sqlite3"
            source = root / "results"
            source.mkdir()
            (source / "output.xml").write_bytes((ROOT / "example/output.xml").read_bytes())
            result = ImportService(database).import_source(source, "portal", "Portal", "2.4")

            systems = catalog_systems(database)
            self.assertEqual(systems, [{
                "id": "portal", "name": "Portal", "executions": 1, "system_version": "2.4"
            }])
            history = list_history(database, "portal")
            self.assertEqual(history[0]["execution_id"], result["execution_id"])
            self.assertEqual(catalog_overview(database, "all")["latest"]["total"], 2)

            remove_history(database, "portal", result["execution_id"])
            self.assertEqual(list_history(database, "portal"), [])
            self.assertEqual(SQLiteStore(database).systems()[0][1], [])

    def test_history_lookup_and_removal_reject_unknown_system_or_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "reports.sqlite3"
            with self.assertRaises(ValueError):
                list_history(database, "missing")
            with self.assertRaises(ValueError):
                remove_history(database, "portal", "missing")


if __name__ == "__main__":
    unittest.main()

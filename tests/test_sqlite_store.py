import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from core.import_service import ImportService
from core.sqlite_store import SQLiteStore

ROOT = Path(__file__).resolve().parent.parent


class TestSQLiteImports(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.store = SQLiteStore(self.base / "history.sqlite3")
        self.service = ImportService(self.base / "history.sqlite3")

    def tearDown(self):
        self.service.close()
        self.temp.cleanup()

    def make_zip(self, name="results.zip", xml=None):
        path = self.base / name
        content = xml or (ROOT / "example/output.xml").read_bytes()
        with zipfile.ZipFile(path, "w") as bundle:
            bundle.writestr("output.xml", content)
            bundle.writestr("screenshots/shot.txt", "evidence")
        return path

    def test_sqlite_persists_metrics_and_retains_only_latest_artifacts(self):
        older = self.make_zip("older.zip")
        first = self.service.import_source(older, "portal", "Portal", "1.0", "2025-01-01T10:00:00")
        first_entry = next(row for row in self.store.history("portal") if row.execution_id == first["execution_id"])
        self.assertEqual(first_entry.total, 2)
        self.assertTrue((self.base / "executions/portal" / first["execution_id"] / "original.zip").is_file())

        newer = self.make_zip("newer.zip", (ROOT / "example/output.xml").read_bytes() + b"\n<!-- distinct -->")
        second = self.service.import_source(newer, "portal", "Portal", "2.0", "2025-02-01T10:00:00")
        metadata, history, current = self.store.load("portal")
        self.assertEqual(metadata["current_execution_id"], second["execution_id"])
        self.assertTrue((current / "original.zip").is_file())
        self.assertFalse((self.base / "executions/portal" / first["execution_id"]).exists())
        self.assertEqual(len(history), 2)

    def test_zip_rejects_paths_and_requires_root_output(self):
        path = self.base / "unsafe.zip"
        with zipfile.ZipFile(path, "w") as bundle:
            bundle.writestr("../output.xml", "bad")
        with self.assertRaisesRegex(ValueError, "inseguro"):
            self.service.prepare_upload(io.BytesIO(path.read_bytes()))

    def test_same_xml_is_deduplicated(self):
        source = self.make_zip()
        first = self.service.import_source(source, "portal", "Portal", "1", "2025-01-01T00:00:00")
        second = self.service.import_source(source, "portal", "Portal", "1", "2025-01-01T00:00:00")
        self.assertTrue(first["inserted"])
        self.assertFalse(second["inserted"])
        self.assertEqual(len(self.store.history("portal")), 1)

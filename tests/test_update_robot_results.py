import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from core.sqlite_store import SQLiteStore


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "update_robot_results.py"


class TestUpdateRobotResults(unittest.TestCase):
    def test_import_list_and_remove_sqlite_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "catalog.sqlite3"
            results = root / "results"
            results.mkdir()
            output_xml = ROOT / "example" / "output.xml"
            (results / "output.xml").write_bytes(output_xml.read_bytes())
            execution_id = hashlib.sha256(output_xml.read_bytes()).hexdigest()
            base = [sys.executable, str(SCRIPT), "--database", str(database)]

            imported = subprocess.run(
                base + [str(results), "--system", "portal", "--name", "Portal", "--version", "2.4"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(imported.returncode, 0, imported.stderr)
            self.assertIn(execution_id, imported.stdout)
            self.assertEqual(len(SQLiteStore(database).history("portal")), 1)

            listed = subprocess.run(
                base + ["--list", "--system", "portal"], capture_output=True, text=True
            )
            self.assertEqual(listed.returncode, 0, listed.stderr)
            self.assertIn("Portal", listed.stdout)
            self.assertIn(execution_id, listed.stdout)

            removed = subprocess.run(
                base + ["--system", "portal", "--remove", execution_id],
                capture_output=True,
                text=True,
            )
            self.assertEqual(removed.returncode, 0, removed.stderr)
            self.assertEqual(SQLiteStore(database).history("portal"), [])

    def test_import_requires_name_and_version(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            results = root / "results"
            results.mkdir()
            (results / "output.xml").write_bytes((ROOT / "example/output.xml").read_bytes())
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(results), "--system", "portal",
                 "--database", str(root / "db.sqlite3")],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("Importação exige --name e --version", result.stderr)


if __name__ == "__main__":
    unittest.main()

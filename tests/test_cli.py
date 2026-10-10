import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


class TestCli(unittest.TestCase):
    def setUp(self):
        self.project_root = Path(__file__).resolve().parent.parent
        self.main_script = self.project_root / "main.py"
        self.example_dir = self.project_root / "example"

    def test_cli_help(self):
        res = subprocess.run(
            [sys.executable, str(self.main_script), "--help"],
            capture_output=True,
            text=True,
            cwd=str(self.project_root),
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("--fail-on-error", res.stdout)
        self.assertIn("--title", res.stdout)
        self.assertIn("--no-history", res.stdout)
        self.assertIn("--zip", res.stdout)

    def test_cli_generate_success_exit_code_zero(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_report = Path(tmp_dir) / "relatorio.html"
            res = subprocess.run(
                [
                    sys.executable,
                    str(self.main_script),
                    "--results-dir",
                    str(self.example_dir),
                    "--report",
                    str(out_report),
                    "--no-history",
                ],
                capture_output=True,
                text=True,
                cwd=str(self.project_root),
            )
            self.assertEqual(res.returncode, 0)
            self.assertTrue(out_report.is_file())

    def test_cli_fail_on_error_flag(self):
        # example/output.xml contains 1 failed test. With --fail-on-error, returncode must be 1
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_report = Path(tmp_dir) / "relatorio.html"
            res = subprocess.run(
                [
                    sys.executable,
                    str(self.main_script),
                    "--results-dir",
                    str(self.example_dir),
                    "--report",
                    str(out_report),
                    "--no-history",
                    "--fail-on-error",
                ],
                capture_output=True,
                text=True,
                cwd=str(self.project_root),
            )
            self.assertEqual(res.returncode, 1)

    def test_cli_issue_url_flag(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_report = Path(tmp_dir) / "relatorio.html"
            res = subprocess.run(
                [
                    sys.executable,
                    str(self.main_script),
                    "--results-dir",
                    str(self.example_dir),
                    "--report",
                    str(out_report),
                    "--no-history",
                    "--issue-url",
                    "https://jira.empresa.com/browse/{id}",
                ],
                capture_output=True,
                text=True,
                cwd=str(self.project_root),
            )
            self.assertEqual(res.returncode, 0)
            self.assertTrue(out_report.is_file())

    def test_reused_xml_generates_html_without_duplicate_history(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            original = root / "original"
            original.mkdir()
            shutil.copyfile(self.example_dir / "output.xml", original / "output.xml")
            changed = root / "changed"
            changed.mkdir()
            (changed / "output.xml").write_bytes((original / "output.xml").read_bytes() + b"\n")
            database = root / "history.sqlite3"

            def generate(source, name):
                report = root / name
                result = subprocess.run(
                    [sys.executable, str(self.main_script), "--results-dir", str(source),
                     "--database", str(database), "--system-id", "cli-test",
                     "--system-name", "CLI Test", "--system-version", "1.0",
                     "--report", str(report)],
                    capture_output=True, text=True, cwd=str(self.project_root),
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(report.is_file())
                return report

            generate(original, "first.html")
            generate(changed, "changed.html")
            repeated = generate(original, "repeated.html")
            import sqlite3
            with sqlite3.connect(database) as connection:
                entries = connection.execute("SELECT execution_id FROM executions ORDER BY timestamp").fetchall()
            self.assertEqual(len(entries), 2)
            ids = {entry[0] for entry in entries}
            self.assertIn(hashlib.sha256((original / "output.xml").read_bytes()).hexdigest(), ids)
            self.assertEqual(len(ids), 2)
            self.assertRegex(repeated.read_text(encoding="utf-8"), r"var detailedVersion = \d+;")

    def test_cli_accepts_zip_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive, report = root / "results.zip", root / "report.html"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.write(self.example_dir / "output.xml", "output.xml")
            result = subprocess.run([sys.executable, str(self.main_script), "--zip", str(archive),
                                     "--no-history", "--report", str(report)], capture_output=True,
                                    text=True, cwd=str(self.project_root))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(report.is_file())


if __name__ == "__main__":
    unittest.main()

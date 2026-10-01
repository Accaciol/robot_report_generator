import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
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
            history_path = root / "history.json"

            def generate(source, name):
                report = root / name
                result = subprocess.run(
                    [sys.executable, str(self.main_script), "--results-dir", str(source),
                     "--history", str(history_path), "--report", str(report)],
                    capture_output=True, text=True, cwd=str(self.project_root),
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(report.is_file())
                return report

            generate(original, "first.html")
            generate(changed, "changed.html")
            repeated = generate(original, "repeated.html")
            entries = json.loads(history_path.read_text(encoding="utf-8"))
            self.assertEqual(len(entries), 2)
            self.assertEqual(entries[0]["execution_id"], hashlib.sha256(
                (original / "output.xml").read_bytes()).hexdigest())
            self.assertNotEqual(entries[0]["execution_id"], entries[1]["execution_id"])
            self.assertIn("var detailedVersion = 0;", repeated.read_text(encoding="utf-8"))
            self.assertIn("var currentVersion = 0 >= 0 ? 0", repeated.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

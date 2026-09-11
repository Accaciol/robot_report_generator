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


if __name__ == "__main__":
    unittest.main()

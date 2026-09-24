import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from core.catalog import Catalog
from core.catalog_report import render_catalog


ROOT = Path(__file__).resolve().parent.parent


def make_results(root, day=10, failed=True, marker="", image=b"image"):
    source = root / f"source-{day}-{marker}"
    source.mkdir(exist_ok=True)
    xml = (ROOT / "example/output.xml").read_text().replace("2026-09-10", f"2026-09-{day:02d}")
    if not failed:
        xml = xml.replace('status="FAIL"', 'status="PASS"')
    xml = xml.replace("Navegando até /login", f"Navegando até /login {marker} &lt;img src=\"screen.png\"&gt;")
    (source / "output.xml").write_text(xml)
    (source / "screen.png").write_bytes(image)
    return source


def tree_bytes(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*")
            if p.is_file() and p.name != ".catalog.lock"}


class TestCatalog(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.catalog = Catalog(self.root / "systems")

    def test_isolation_deduplication_order_and_evidence_replacement(self):
        older = make_results(self.root, 10, marker="older")
        newer = make_results(self.root, 12, failed=False, marker="newer")
        new_id = self.catalog.import_results(newer, "alpha", "Alpha")
        (self.catalog.root / "alpha/current/stale.png").write_bytes(b"old")
        old_id = self.catalog.import_results(older, "alpha")
        self.catalog.import_results(older, "beta", "Beta")
        self.catalog.import_results(newer, "alpha")
        metadata, history, path = self.catalog.load("alpha")
        self.assertEqual([e.execution_id for e in history], [old_id, new_id])
        self.assertEqual(metadata["current_execution_id"], new_id)
        self.assertFalse((path / "current/stale.png").exists())
        self.assertEqual((path / "current/output.xml").read_bytes(), (newer / "output.xml").read_bytes())
        self.assertEqual([e.failed for e in history], [1, 0])
        self.assertEqual(len(self.catalog.load("beta")[1]), 1)
        self.assertEqual(history[0].tests[0]["stable_id"], self.catalog.load("beta")[1][0].tests[0]["stable_id"])

    def test_no_automatic_history_limit(self):
        for number in range(32):
            self.catalog.import_results(make_results(self.root, marker=str(number)), "alpha")
        self.assertEqual(len(self.catalog.load("alpha")[1]), 32)

    def test_equal_dates_have_same_order_regardless_of_import_order(self):
        first = make_results(self.root, marker="first")
        second = make_results(self.root, marker="second")
        self.catalog.import_results(first, "alpha")
        self.catalog.import_results(second, "alpha")
        self.catalog.import_results(second, "beta")
        self.catalog.import_results(first, "beta")
        alpha, alpha_history, _ = self.catalog.load("alpha")
        beta, beta_history, _ = self.catalog.load("beta")
        self.assertEqual([e.execution_id for e in alpha_history], [e.execution_id for e in beta_history])
        self.assertEqual(alpha["current_execution_id"], beta["current_execution_id"])

    def test_concurrent_writer_is_rejected(self):
        source = make_results(self.root)
        self.catalog.import_results(source, "alpha")
        before = tree_bytes(self.catalog.root)
        with self.catalog._writer():
            with self.assertRaisesRegex(ValueError, "andamento"):
                self.catalog.import_results(source, "alpha")
        self.assertEqual(tree_bytes(self.catalog.root), before)

    def test_remove_old_current_and_last(self):
        old_id = self.catalog.import_results(make_results(self.root, 10), "alpha")
        middle_id = self.catalog.import_results(make_results(self.root, 11), "alpha")
        current_id = self.catalog.import_results(make_results(self.root, 12), "alpha")
        self.catalog.import_results(make_results(self.root, 13), "beta")
        beta_before = tree_bytes(self.catalog.root / "beta")
        self.catalog.remove("alpha", old_id)
        self.assertTrue((self.catalog.root / "alpha/current/output.xml").exists())
        self.catalog.remove("alpha", current_id)
        metadata, history, path = self.catalog.load("alpha")
        self.assertIsNone(metadata["current_execution_id"])
        self.assertEqual(history[-1].execution_id, middle_id)
        self.assertFalse((path / "current").exists())
        data = self.catalog.report_data(metadata, history, path, "Report")
        self.assertEqual(data.detailed_execution_id, "")
        self.assertEqual(data.suites, [])
        self.catalog.remove("alpha", middle_id)
        self.assertEqual(self.catalog.load("alpha")[1], [])
        self.assertEqual(tree_bytes(self.catalog.root / "beta"), beta_before)

    def test_invalid_input_and_ids_do_not_modify_data(self):
        source = make_results(self.root)
        self.catalog.import_results(source, "alpha")
        before = tree_bytes(self.catalog.root)
        (source / "output.xml").write_text("not XML")
        with self.assertRaises(ValueError):
            self.catalog.import_results(source, "alpha")
        for system_id, execution_id in [("alpha", "unknown"), ("missing", "unknown"), ("../escape", "x")]:
            with self.assertRaises(ValueError):
                self.catalog.remove(system_id, execution_id)
        self.assertEqual(tree_bytes(self.catalog.root), before)

    def test_copy_and_json_write_failures_preserve_previous_data(self):
        source = make_results(self.root)
        self.catalog.import_results(source, "alpha")
        before = tree_bytes(self.catalog.root)
        for target in ("core.catalog.shutil.copytree", "core.catalog._write_json"):
            with patch(target, side_effect=OSError("disk failure")):
                with self.assertRaises(OSError):
                    self.catalog.import_results(source, "alpha")
            self.assertEqual(tree_bytes(self.catalog.root), before)
        with patch("core.catalog._write_json", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                self.catalog.remove("alpha", self.catalog.load("alpha")[1][0].execution_id)
        self.assertEqual(tree_bytes(self.catalog.root), before)

    def test_promotion_failure_rolls_back_directory(self):
        source = make_results(self.root)
        self.catalog.import_results(source, "alpha")
        before = tree_bytes(self.catalog.root)
        original = Path.rename
        def fail_promotion(path, destination):
            if path.name == "system":
                raise OSError("promotion failed")
            return original(path, destination)
        with patch.object(Path, "rename", fail_promotion):
            with self.assertRaises(OSError):
                self.catalog.import_results(source, "alpha", "Changed name")
        self.assertEqual(tree_bytes(self.catalog.root), before)

    def test_interrupted_swap_can_be_read_and_recovered(self):
        source = make_results(self.root)
        self.catalog.import_results(source, "alpha")
        (self.catalog.root / "alpha").rename(self.catalog.root / ".alpha.backup")
        self.assertEqual(self.catalog.systems()[0][0]["id"], "alpha")
        self.catalog.import_results(source, "alpha")
        self.assertTrue((self.catalog.root / "alpha").is_dir())
        self.assertFalse((self.catalog.root / ".alpha.backup").exists())

    def test_explicit_legacy_migration(self):
        source = make_results(self.root, 12)
        legacy = self.root / "legacy.json"
        legacy.write_bytes((ROOT / "example/history.json").read_bytes())
        self.catalog.import_results(source, "migrated", "Legado", legacy)
        metadata, history, _ = self.catalog.load("migrated")
        self.assertTrue(any(entry.execution_id.startswith("legacy-") for entry in history))
        self.assertTrue(metadata["current_execution_id"])
        before = tree_bytes(self.catalog.root)
        with self.assertRaises(ValueError):
            self.catalog.import_results(source, "migrated", legacy_history=legacy)
        self.assertEqual(tree_bytes(self.catalog.root), before)

    def test_migration_does_not_duplicate_exact_legacy_match(self):
        source = make_results(self.root)
        self.catalog.import_results(source, "original")
        legacy = self.root / "legacy.json"
        raw = json.loads((self.catalog.root / "original/history.json").read_text())
        del raw[0]["execution_id"]
        legacy.write_text(json.dumps(raw))
        self.catalog.import_results(source, "migrated", legacy_history=legacy)
        self.assertEqual(len(self.catalog.load("migrated")[1]), 1)

    def test_corrupt_catalog_is_not_silently_reset(self):
        source = make_results(self.root)
        self.catalog.import_results(source, "alpha")
        (self.catalog.root / "alpha/history.json").write_text("bad json")
        before = tree_bytes(self.catalog.root)
        with self.assertRaises(ValueError):
            self.catalog.import_results(source, "alpha")
        self.assertEqual(tree_bytes(self.catalog.root), before)

    def test_render_is_read_only_and_handles_empty_systems(self):
        source = make_results(self.root)
        entry_id = self.catalog.import_results(source, "beta", "Beta")
        self.catalog.import_results(source, "alpha", 'Alpha </script><script>alert("x")</script>')
        self.catalog.remove("beta", entry_id)
        before = tree_bytes(self.catalog.root)
        report = self.root / "report.html"
        self.assertTrue(render_catalog(str(self.catalog.root), str(report), "Reports"))
        self.assertEqual(tree_bytes(self.catalog.root), before)
        html = report.read_text()
        self.assertIn('id="systemSelect"', html)
        self.assertNotIn('Alpha </script><script>', html)
        self.assertIn('"id": "beta"', html)
        self.assertIn('"html": null', html)

    def test_changed_current_xml_fails_render_without_overwriting_report(self):
        source = make_results(self.root)
        self.catalog.import_results(source, "alpha")
        report = self.root / "report.html"
        report.write_text("previous report")
        (self.catalog.root / "alpha/current/output.xml").write_text("changed")
        with self.assertRaises(ValueError):
            render_catalog(str(self.catalog.root), str(report), "Reports")
        self.assertEqual(report.read_text(), "previous report")

    def test_cli_import_list_remove_and_generate(self):
        source = make_results(self.root)
        script = ROOT / "scripts/update_robot_results.py"
        base = [sys.executable, str(script), "--catalog-dir", str(self.catalog.root)]
        result = subprocess.run(base + [str(source), "--system", "alpha", "--name", "Alpha"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        entry_id = hashlib.sha256((source / "output.xml").read_bytes()).hexdigest()
        result = subprocess.run(base + ["--list"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(entry_id, result.stdout)
        before = tree_bytes(self.catalog.root)
        result = subprocess.run([sys.executable, str(ROOT / "main.py"), "--catalog-dir", str(self.catalog.root),
                                 "--report", str(self.root / "report.html"), "--fail-on-error"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertTrue((self.root / "report.html").exists())
        self.assertEqual(tree_bytes(self.catalog.root), before)
        result = subprocess.run(base + ["--system", "alpha", "--remove", entry_id], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run([sys.executable, str(ROOT / "main.py"), "--catalog-dir", str(self.catalog.root),
                                 "--report", str(self.root / "report.html")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(entry_id, (self.root / "report.html").read_text())

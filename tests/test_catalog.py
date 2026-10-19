from pathlib import Path
import tempfile
import unittest

from core.catalog import Catalog
from core.catalog_report import render_catalog


ROOT = Path(__file__).resolve().parent.parent


def make_results(root, day=10, failed=True, marker="", image=b"image"):
    source = root / f"source-{day}-{marker}"
    source.mkdir(exist_ok=True)
    xml = (ROOT / "example/output.xml").read_text(encoding="utf-8")
    xml = xml.replace("2026-09-10", f"2026-09-{day:02d}")
    if not failed:
        xml = xml.replace('status="FAIL"', 'status="PASS"')
    xml = xml.replace("Navegando até /login", f"Navegando até /login {marker}")
    (source / "output.xml").write_text(xml, encoding="utf-8")
    (source / "screen.png").write_bytes(image)
    return source


class TestCatalog(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.catalog = Catalog(self.root / "catalog")

    def test_imports_are_isolated_deduplicated_and_ordered_in_sqlite(self):
        older = make_results(self.root, 10, marker="older")
        newer = make_results(self.root, 12, failed=False, marker="newer")
        older_id = self.catalog.import_results(older, "alpha", "Alpha")
        newer_id = self.catalog.import_results(newer, "alpha", "Alpha")
        self.catalog.import_results(older, "beta", "Beta")
        self.catalog.import_results(newer, "alpha", "Alpha")

        metadata, history, directory = self.catalog.load("alpha")
        self.assertEqual([entry.execution_id for entry in history], [older_id, newer_id])
        self.assertEqual(metadata["current_execution_id"], newer_id)
        self.assertEqual(history[-1].failed, 0)
        self.assertTrue((directory / "results" / "output.xml").is_file())
        self.assertEqual(len(self.catalog.load("beta")[1]), 1)

    def test_history_has_no_automatic_entry_limit(self):
        for number in range(32):
            self.catalog.import_results(
                make_results(self.root, day=10, marker=str(number)), "alpha", "Alpha"
            )
        self.assertEqual(len(self.catalog.load("alpha")[1]), 32)

    def test_equal_dates_have_stable_order_across_systems(self):
        first = make_results(self.root, marker="first")
        second = make_results(self.root, marker="second")
        self.catalog.import_results(first, "alpha", "Alpha")
        self.catalog.import_results(second, "alpha", "Alpha")
        self.catalog.import_results(second, "beta", "Beta")
        self.catalog.import_results(first, "beta", "Beta")
        alpha, alpha_history, _ = self.catalog.load("alpha")
        beta, beta_history, _ = self.catalog.load("beta")
        self.assertEqual(
            [entry.execution_id for entry in alpha_history],
            [entry.execution_id for entry in beta_history],
        )
        self.assertEqual(alpha["current_execution_id"], beta["current_execution_id"])

    def test_remove_execution_keeps_other_system_and_rejects_unknown_ids(self):
        alpha_id = self.catalog.import_results(make_results(self.root), "alpha", "Alpha")
        beta_id = self.catalog.import_results(make_results(self.root, marker="beta"), "beta", "Beta")
        self.catalog.remove("alpha", alpha_id)
        self.assertEqual(self.catalog.load("alpha")[1], [])
        self.assertEqual(len(self.catalog.load("beta")[1]), 1)
        with self.assertRaises(ValueError):
            self.catalog.remove("beta", "unknown")
        with self.assertRaises(ValueError):
            self.catalog.remove("../escape", beta_id)

    def test_invalid_xml_does_not_add_an_execution(self):
        source = make_results(self.root)
        (source / "output.xml").write_text("invalid XML", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.catalog.import_results(source, "alpha", "Alpha")
        self.assertEqual(self.catalog.systems(), [])

    def test_render_catalog_reads_sqlite_without_changing_it(self):
        self.catalog.import_results(make_results(self.root), "alpha", "Alpha")
        before = self.catalog.store.history("alpha")
        report = self.root / "report.html"
        failed = render_catalog(self.catalog.database, report, "Reports")
        self.assertTrue(failed)
        self.assertTrue(report.is_file())
        self.assertEqual(self.catalog.store.history("alpha"), before)
        self.assertIn('id="systemSelect"', report.read_text(encoding="utf-8"))

    def test_render_empty_sqlite_catalog(self):
        report = self.root / "empty.html"
        failed = render_catalog(self.catalog.database, report, "Reports")
        self.assertFalse(failed)
        self.assertTrue(report.is_file())


if __name__ == "__main__":
    unittest.main()

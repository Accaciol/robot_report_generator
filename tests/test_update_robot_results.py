import tempfile
import unittest
from pathlib import Path

from scripts.update_robot_results import replace_results


class TestUpdateRobotResults(unittest.TestCase):
    def test_replacement_removes_stale_evidence_and_preserves_new_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, target = root / "source", root / "current"
            (source / "screenshots").mkdir(parents=True)
            (source / "output.xml").write_text("<robot/>")
            (source / "screenshots" / "new.png").write_bytes(b"image")
            (source / "log.html").write_text("unused")
            target.mkdir()
            (target / "old.png").write_bytes(b"old")
            replace_results(source, target)
            self.assertFalse((target / "old.png").exists())
            self.assertFalse((target / "log.html").exists())
            self.assertEqual((target / "screenshots" / "new.png").read_bytes(), b"image")
            self.assertTrue((source / "log.html").exists())
            self.assertTrue((target / "output.xml").is_file())

    def test_missing_output_preserves_previous_results(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "current"
            target.mkdir()
            (target / "output.xml").write_text("previous")
            with self.assertRaises(ValueError):
                replace_results(root / "missing", target)
            self.assertEqual((target / "output.xml").read_text(), "previous")

    def test_overlapping_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            (source / "output.xml").write_text("<robot/>")
            with self.assertRaises(ValueError):
                replace_results(source, source / "current")
            with self.assertRaises(ValueError):
                replace_results(source, source)

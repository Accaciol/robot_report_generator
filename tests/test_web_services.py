import tempfile
import unittest
from pathlib import Path

from core.web_services import list_folders, validate_run_request


class TestWebServices(unittest.TestCase):
    def test_run_request_deduplicates_paths_and_keeps_system_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            results = root / "results"
            results.mkdir()
            (results / "output.xml").write_text("<robot />", encoding="utf-8")
            destination = root / "reports"
            destination.mkdir()
            history = root / "history.json"
            sources, actual_destination, actual_history = validate_run_request({
                "folders": [
                    {"path": str(results), "system_id": "portal", "name": "Portal"},
                    {"path": str(results), "system_id": "portal", "name": "Portal"},
                ],
                "destination": str(destination),
                "history": str(history),
            })

            self.assertEqual(len(sources), 1)
            self.assertEqual(sources[0]["system_id"], "portal")
            self.assertEqual(sources[0]["name"], "Portal")
            self.assertEqual(actual_destination, destination)
            self.assertEqual(actual_history, history)

    def test_list_folders_reports_output_xml_and_sorted_children(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "zeta").mkdir()
            (root / "Alpha").mkdir()
            (root / "output.xml").touch()

            result = list_folders(root)

            self.assertTrue(result["has_output"])
            self.assertEqual([folder["name"] for folder in result["folders"]], ["Alpha", "zeta"])


if __name__ == "__main__":
    unittest.main()

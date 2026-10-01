import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from core.history_manager import HistoryManager
from models import ExecutionStats, SuiteResult, TestResult, Status


class TestHistoryManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.history_file = Path(self.temp_dir.name) / "history.json"
        self.manager = HistoryManager(str(self.history_file), max_entries=5)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_load_non_existent(self):
        entries = self.manager.load()
        self.assertEqual(entries, [])

    def test_load_corrupted_json(self):
        self.history_file.write_text("invalid json content { [", encoding="utf-8")
        entries = self.manager.load()
        self.assertEqual(entries, [])

    def test_append_and_rotation(self):
        stats = ExecutionStats(total=10, passed=8, failed=2, skipped=0, elapsed_s=15.5)
        suites = [
            SuiteResult(
                name="Suite 1",
                tests=[
                    TestResult(name="Test A", status=Status.PASS, elapsed_s=5.0),
                    TestResult(name="Test B", status=Status.FAIL, elapsed_s=10.5),
                ]
            )
        ]

        # Append 7 entries when max_entries is 5
        for i in range(7):
            history = self.manager.append(stats, suites=suites, execution_start="2026-09-10 10:00:00",
                                          execution_id=f"run-{i}")
            self.assertLessEqual(len(history), 5)

        self.assertEqual(len(history), 5)
        # Check that history file was persisted and is valid JSON
        data = json.loads(self.history_file.read_text(encoding="utf-8"))
        self.assertEqual(len(data), 5)
        self.assertEqual(data[-1]["passed"], 8)
        self.assertEqual(data[-1]["failed"], 2)

    def test_reused_output_is_not_added_twice(self):
        stats = ExecutionStats(total=1, passed=1)
        suites = [SuiteResult(name="Suite", tests=[TestResult(name="Teste", status=Status.PASS)])]
        first = self.manager.append(stats, suites, "2026-09-10 10:00:00", "xml-a")
        repeated = self.manager.append(stats, suites, "2026-09-10 10:00:00", "xml-a")
        self.assertEqual(len(repeated), 1)
        self.assertEqual(repeated[0].version, first[0].version)
        self.assertEqual(len(json.loads(self.history_file.read_text(encoding="utf-8"))), 1)
        changed_xml = self.manager.append(stats, suites, "2026-09-10 10:00:00", "xml-b")
        self.assertEqual(len(changed_xml), 2)

    def test_legacy_duplicates_are_collapsed_and_reused_output_is_identified(self):
        stats = ExecutionStats(total=1, passed=1)
        suites = [SuiteResult(name="Suite", tests=[TestResult(name="Teste", status=Status.PASS)])]
        first = self.manager.append(stats, suites, "2026-09-10 10:00:00")
        raw = json.loads(self.history_file.read_text(encoding="utf-8"))
        duplicate = dict(raw[0], version="2026-09-10 #2")
        self.history_file.write_text(json.dumps([raw[0], duplicate]), encoding="utf-8")
        self.assertEqual(len(self.manager.load()), 1)
        history = self.manager.append(stats, suites, "2026-09-10 10:00:00", "xml-a")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].version, first[0].version)
        self.assertEqual(history[0].execution_id, "xml-a")
        self.assertEqual(len(json.loads(self.history_file.read_text(encoding="utf-8"))), 1)

    def test_remove_uses_visible_index_after_legacy_deduplication(self):
        stats = ExecutionStats(total=1, passed=1)
        self.manager.append(stats, execution_start="2026-09-10 10:00:00")
        second = self.manager.append(stats, execution_start="2026-09-11 10:00:00")
        raw = json.loads(self.history_file.read_text(encoding="utf-8"))
        raw.insert(1, dict(raw[0], version="2026-09-10 #2"))
        self.history_file.write_text(json.dumps(raw), encoding="utf-8")
        self.assertEqual(len(self.manager.load()), 2)
        self.manager.remove(1, second[-1].timestamp, second[-1].version)
        remaining = json.loads(self.history_file.read_text(encoding="utf-8"))
        self.assertEqual(remaining, [raw[0]])

    def test_timestamp_handling(self):
        now = datetime(2026, 9, 11, 14, 30, 0)
        ts_dt = HistoryManager._timestamp(now)
        self.assertEqual(ts_dt, "2026-09-11T14:30:00")

        ts_str = HistoryManager._timestamp("20260911 14:30:00")
        self.assertEqual(ts_str, "2026-09-11T14:30:00")

        ts_iso = HistoryManager._timestamp("2026-09-11T14:30:00")
        self.assertEqual(ts_iso, "2026-09-11T14:30:00")

    def test_detect_flaky_tests(self):
        from models import HistoryEntry
        history = [
            HistoryEntry(timestamp="2026-09-10T10:00:00", total=2, passed=2, failed=0, skipped=0, elapsed_s=10, pass_rate=100, tests=[
                {"stable_id": "Suite::T1", "test_name": "T1", "suite_name": "Suite", "status": "PASS"},
                {"stable_id": "Suite::T2", "test_name": "T2", "suite_name": "Suite", "status": "PASS"},
            ]),
            HistoryEntry(timestamp="2026-09-10T11:00:00", total=2, passed=1, failed=1, skipped=0, elapsed_s=10, pass_rate=50, tests=[
                {"stable_id": "Suite::T1", "test_name": "T1", "suite_name": "Suite", "status": "FAIL"},
                {"stable_id": "Suite::T2", "test_name": "T2", "suite_name": "Suite", "status": "PASS"},
            ]),
            HistoryEntry(timestamp="2026-09-10T12:00:00", total=2, passed=2, failed=0, skipped=0, elapsed_s=10, pass_rate=100, tests=[
                {"stable_id": "Suite::T1", "test_name": "T1", "suite_name": "Suite", "status": "PASS"},
                {"stable_id": "Suite::T2", "test_name": "T2", "suite_name": "Suite", "status": "PASS"},
            ]),
        ]

        flaky = HistoryManager.detect_flaky_tests(history)
        self.assertEqual(len(flaky), 1)
        self.assertEqual(flaky[0]["test_name"], "T1")
        self.assertEqual(flaky[0]["flips"], 2)

    def test_compute_delta_stats(self):
        from models import HistoryEntry
        history = [
            HistoryEntry(timestamp="2026-09-10T10:00:00", version="v1", total=2, passed=1, failed=1, skipped=0, elapsed_s=10.0, pass_rate=50.0),
            HistoryEntry(timestamp="2026-09-10T11:00:00", version="v2", total=2, passed=2, failed=0, skipped=0, elapsed_s=8.0, pass_rate=100.0),
        ]
        curr_stats = ExecutionStats(total=2, passed=2, failed=0, skipped=0, elapsed_s=8.0)
        delta = HistoryManager.compute_delta_stats(curr_stats, history)
        self.assertTrue(delta.get("has_delta"))
        self.assertEqual(delta.get("pass_rate_delta"), 50.0)
        self.assertEqual(delta.get("failed_delta"), -1)


if __name__ == "__main__":
    unittest.main()

import unittest
from datetime import datetime

from core.history_manager import HistoryManager
from models import ExecutionStats, HistoryEntry


class TestHistoryManager(unittest.TestCase):
    def test_timestamp_handling(self):
        now = datetime(2026, 9, 11, 14, 30, 0)
        self.assertEqual(HistoryManager._timestamp(now), "2026-09-11T14:30:00")
        self.assertEqual(
            HistoryManager._timestamp("20260911 14:30:00"), "2026-09-11T14:30:00"
        )
        self.assertEqual(
            HistoryManager._timestamp("2026-09-11T14:30:00"), "2026-09-11T14:30:00"
        )

    def test_detect_flaky_tests(self):
        history = [
            HistoryEntry(
                timestamp="2026-09-10T10:00:00", total=2, passed=2,
                failed=0, skipped=0, elapsed_s=10, pass_rate=100,
                tests=[
                    {"stable_id": "Suite::T1", "test_name": "T1", "suite_name": "Suite", "status": "PASS"},
                    {"stable_id": "Suite::T2", "test_name": "T2", "suite_name": "Suite", "status": "PASS"},
                ],
            ),
            HistoryEntry(
                timestamp="2026-09-10T11:00:00", total=2, passed=1,
                failed=1, skipped=0, elapsed_s=10, pass_rate=50,
                tests=[
                    {"stable_id": "Suite::T1", "test_name": "T1", "suite_name": "Suite", "status": "FAIL"},
                    {"stable_id": "Suite::T2", "test_name": "T2", "suite_name": "Suite", "status": "PASS"},
                ],
            ),
            HistoryEntry(
                timestamp="2026-09-10T12:00:00", total=2, passed=2,
                failed=0, skipped=0, elapsed_s=10, pass_rate=100,
                tests=[
                    {"stable_id": "Suite::T1", "test_name": "T1", "suite_name": "Suite", "status": "PASS"},
                    {"stable_id": "Suite::T2", "test_name": "T2", "suite_name": "Suite", "status": "PASS"},
                ],
            ),
        ]

        flaky = HistoryManager.detect_flaky_tests(history)
        self.assertEqual(len(flaky), 1)
        self.assertEqual(flaky[0]["test_name"], "T1")
        self.assertEqual(flaky[0]["flips"], 2)

    def test_compute_delta_stats(self):
        history = [
            HistoryEntry(
                timestamp="2026-09-10T10:00:00", version="v1", total=2,
                passed=1, failed=1, skipped=0, elapsed_s=10.0, pass_rate=50.0,
            ),
            HistoryEntry(
                timestamp="2026-09-10T11:00:00", version="v2", total=2,
                passed=2, failed=0, skipped=0, elapsed_s=8.0, pass_rate=100.0,
            ),
        ]
        current = ExecutionStats(total=2, passed=2, failed=0, skipped=0, elapsed_s=8.0)
        delta = HistoryManager.compute_delta_stats(current, history)
        self.assertTrue(delta.get("has_delta"))
        self.assertEqual(delta.get("pass_rate_delta"), 50.0)
        self.assertEqual(delta.get("failed_delta"), -1)


if __name__ == "__main__":
    unittest.main()

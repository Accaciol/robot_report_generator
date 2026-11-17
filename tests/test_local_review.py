import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from complemento.local_review import Review, validate_destination


def matrix():
    return {'report_id': 'a' * 64, 'candidates': [
        {'candidate_id': str(i), 'status': 'FAIL', 'test_name': f'Test {i}',
         'message': '<script>bad()</script>', 'artifact_ids': []}
        for i in range(2)], 'artifacts': []}


class LocalReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'state.json'
        self.review = Review(matrix(), self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_destination_rejects_credentials_and_wrong_host(self):
        for url in ('http://dev.azure.com/o/p/_boards',
                    'https://dev.azure.com.evil.test/o/p/_boards',
                    'https://user:pass@dev.azure.com/o/p/_boards',
                    'https://dev.azure.com/o/p/_workitems'):
            with self.assertRaises(ValueError):
                validate_destination({'board_url': url})
        config = validate_destination({'board_url': 'https://dev.azure.com/org/Project/_boards/board/t/Team/Stories',
                                       'initial_state': 'New', 'desired_column': 'Triage'})
        self.assertEqual(config['project'], 'Project')
        self.assertNotEqual(config['initial_state'], config['desired_column'])

    def prepare(self):
        self.review.prepare({'board_url': 'https://dev.azure.com/org/Project/_boards'})

    def test_one_form_and_confirmed_decision_only(self):
        self.prepare()
        candidate, attempt = self.review.open_next()
        with self.assertRaises(ValueError):
            self.review.open_next()
        with self.assertRaises(ValueError):
            self.review.decide(candidate['candidate_id'], 'wrong', 'saved', 'title', 'body')
        self.review.decide(candidate['candidate_id'], attempt, 'saved', 'title', 'body')
        with self.assertRaises(ValueError):
            self.review.decide(candidate['candidate_id'], attempt, 'saved', 'title', 'body')
        next_candidate, _ = self.review.open_next()
        self.assertNotEqual(candidate['candidate_id'], next_candidate['candidate_id'])
        self.assertEqual(self.review.snapshot()['results'][0]['simulation_id'], 'SIM-0001')
        self.assertIsNone(self.review.snapshot()['results'][0]['work_item_id'])

    def test_restart_pauses_and_invalidates_old_attempt(self):
        self.prepare()
        candidate, attempt = self.review.open_next()
        recovered = Review(matrix(), self.path)
        self.assertEqual(recovered.snapshot()['status'], 'paused')
        with self.assertRaises(ValueError):
            recovered.decide(candidate['candidate_id'], attempt, 'saved', 'title', 'body')
        self.assertEqual(recovered.open_next()[0], candidate)

    def test_discard_completion_and_empty_report(self):
        self.prepare()
        for _ in range(2):
            candidate, attempt = self.review.open_next()
            self.review.decide(candidate['candidate_id'], attempt, 'discarded', '', '')
        self.assertEqual(self.review.snapshot()['status'], 'completed')
        with self.assertRaises(ValueError):
            self.review.open_next()
        empty = matrix()
        empty['candidates'] = []
        review = Review(empty, Path(self.tmp.name) / 'empty.json')
        review.prepare({'board_url': 'https://dev.azure.com/o/p/_boards'})
        self.assertEqual(review.snapshot()['status'], 'completed')

    def test_state_is_bound_to_report_and_corruption_is_not_reset(self):
        self.prepare()
        other = matrix()
        other['report_id'] = 'b' * 64
        with self.assertRaises(ValueError):
            Review(other, self.path)
        self.path.write_text('bad json')
        with self.assertRaises(ValueError):
            Review(matrix(), self.path)

    def test_failed_persistence_does_not_advance_the_queue(self):
        self.prepare()
        candidate, attempt = self.review.open_next()
        before = self.review.snapshot()
        with patch.object(Path, 'replace', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                self.review.decide(candidate['candidate_id'], attempt, 'saved', 'title', 'body')
        self.assertEqual(self.review.snapshot(), before)


if __name__ == '__main__':
    unittest.main()

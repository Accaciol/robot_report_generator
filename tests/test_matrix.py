import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from models import Artifact, ExecutionStats, KeywordResult, ReportData, Status, SuiteResult, TestResult
from complemento.matrix import build_matrix, inject_controls, validate_artifact_paths


class MatrixTests(unittest.TestCase):
    def test_only_failures_with_distinct_occurrences_and_nested_evidence(self):
        artifact = Artifact('image', 'proof.png', 'data:image/png;base64,aGVsbG8=')
        failed = TestResult('Repeated', Status.FAIL, suite_name='Suite', message='problem',
                            keywords=[KeywordResult('outer', Status.FAIL, children=[
                                KeywordResult('inner', Status.FAIL, artifacts=[artifact])])])
        data = ReportData(ExecutionStats(), [SuiteResult('Suite', tests=[failed, failed,
                          TestResult('ok', Status.PASS), TestResult('skip', Status.SKIP)])], [], 'today')
        matrix = build_matrix(data, 'a' * 64)
        self.assertEqual(len(matrix['candidates']), 2)
        self.assertNotEqual(matrix['candidates'][0]['candidate_id'], matrix['candidates'][1]['candidate_id'])
        self.assertEqual(len(matrix['artifacts']), 1)
        self.assertEqual(matrix['candidates'][0]['artifact_ids'], [matrix['artifacts'][0]['artifact_id']])

    def test_json_cannot_end_script_or_render_failure_as_markup(self):
        data = ReportData(ExecutionStats(), [SuiteResult('S', tests=[
            TestResult('</script><img onerror=alert(1)>', Status.FAIL)])], [], 'today')
        html = inject_controls('<html><body><main></main></body></html>', build_matrix(data, 'a' * 64))
        self.assertNotIn('</script><img', html)
        self.assertIn('ruzy-matrix', html)

    def test_evidence_cannot_read_files_outside_results_directory(self):
        artifact = Artifact('image', '../../private-file.png')
        suites = [SuiteResult('S', tests=[TestResult('T', Status.FAIL,
                    keywords=[KeywordResult('K', Status.FAIL, artifacts=[artifact])])])]
        with self.assertRaisesRegex(ValueError, 'fora da pasta'):
            validate_artifact_paths(suites, ROOT / 'demo' / 'results')


if __name__ == '__main__':
    unittest.main()

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from complemento.local_review import Review
from complemento.local_service import create_app
from tests.test_local_review import matrix

ORIGIN = 'http://127.0.0.1:8877'


class LocalServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.review = Review(matrix(), Path(self.tmp.name) / 'state.json')
        self.opened = []
        self.app = create_app(self.review, '<html><main>Robot</main></html>',
                              lambda: self.opened.append(True))
        self.app.config.update(LOCAL_ORIGIN=ORIGIN, TESTING=True)
        self.client = self.app.test_client()
        self.headers = {'X-Ruzy-Token': self.app.config['SESSION_TOKEN'], 'Origin': ORIGIN}
        self.client.post('/api/session', base_url=ORIGIN, headers=self.headers)

    def post(self, route, data=None, headers=None):
        return self.client.post(route, base_url=ORIGIN, headers=headers or self.headers, json=data or {})

    def test_protects_api_and_report_without_cors(self):
        self.assertEqual(self.client.get('/api/state', base_url=ORIGIN).status_code, 403)
        self.assertEqual(self.client.get('/api/state', base_url='http://evil.test',
                                         headers=self.headers).status_code, 403)
        self.assertEqual(self.post('/api/prepare', headers={**self.headers, 'Origin': 'null'}).status_code, 403)
        self.assertNotIn('Access-Control-Allow-Origin', self.client.get('/', base_url=ORIGIN).headers)
        self.assertEqual(self.app.test_client().get('/report', base_url=ORIGIN).status_code, 403)
        report = self.client.get('/report', base_url=ORIGIN)
        self.assertEqual(report.status_code, 200)
        self.assertIn('sandbox', report.headers['Content-Security-Policy'])
        self.assertNotIn('allow-same-origin', report.headers['Content-Security-Policy'])

    def test_sequential_decisions_and_export_escaping(self):
        self.assertEqual(self.post('/api/prepare', {'board_url': 'https://dev.azure.com/o/p/_boards'}).status_code, 200)
        self.assertEqual(self.post('/api/start').status_code, 200)
        self.assertEqual(len(self.opened), 1)
        candidate, attempt = self.review.open_next()
        payload = {'candidate_id': candidate['candidate_id'], 'attempt': attempt, 'status': 'saved',
                   'title': '<script>bad()</script>', 'description': 'Reviewed'}
        response = self.post('/decision', payload, {'Origin': ORIGIN})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.opened), 2)
        self.assertEqual(self.post('/decision', payload, {'Origin': ORIGIN}).status_code, 400)
        exported = self.client.get('/api/export/html', base_url=ORIGIN, headers=self.headers)
        self.assertIn('&lt;script&gt;bad()', exported.text)
        self.assertNotIn('<script>bad()', exported.text)
        self.assertNotIn(attempt, exported.text)
        self.assertIn('SIM-0001', exported.text)

    def test_rejects_invalid_json_and_oversize_data(self):
        response = self.client.post('/api/prepare', base_url=ORIGIN, headers=self.headers, json=[])
        self.assertEqual(response.status_code, 400)
        response = self.post('/api/prepare', {'board_url': 'x' * (70 * 1024)})
        self.assertEqual(response.status_code, 413)

    def test_persistence_error_has_no_advance_or_stack_trace(self):
        with patch.object(Path, 'replace', side_effect=OSError('private path')):
            response = self.post('/api/prepare', {'board_url': 'https://dev.azure.com/o/p/_boards'})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private path', response.text)
        self.assertEqual(self.review.snapshot()['status'], 'idle')


if __name__ == '__main__':
    unittest.main()

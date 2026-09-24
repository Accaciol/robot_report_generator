import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from core.web_app import create_app

ROOT = Path(__file__).resolve().parent.parent
ORIGIN = 'http://127.0.0.1:5000'


class TestWebApp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.app = create_app()
        self.app.testing = True
        self.client = self.app.test_client()
        self.jobs = self.app.extensions['jobs']
        self.headers = {'X-Session-Token': self.app.config['SESSION_TOKEN'], 'Origin': ORIGIN}

    def tearDown(self):
        self.jobs.close()
        self.tmp.cleanup()

    def get(self, path, **kwargs):
        return self.client.get(path, base_url=ORIGIN, headers=self.headers, **kwargs)

    def post(self, path, data=None):
        return self.client.post(path, base_url=ORIGIN, headers=self.headers, json=data or {})

    def folder(self, name, valid=True):
        path = self.base / name
        path.mkdir(parents=True)
        if valid:
            shutil.copyfile(ROOT / 'example/output.xml', path / 'output.xml')
        else:
            (path / 'output.xml').write_text('not xml')
        return path

    def start(self, folders):
        return self.post('/api/runs', {'folders': list(map(str, folders)), 'destination': str(self.base),
                                       'history': str(self.base / 'history.json')})

    def wait(self):
        self.jobs.worker.join(timeout=15)
        self.assertFalse(self.jobs.worker.is_alive())
        return self.jobs.snapshot()

    def test_session_and_local_assets(self):
        self.assertEqual(self.get('/').status_code, 200)
        for resource in ('/static/app.js', '/static/app.css'):
            response = self.get(resource)
            self.assertEqual(response.status_code, 200)
            response.close()
        response = self.post('/api/session')
        self.assertEqual(response.status_code, 200)
        self.assertIn('HttpOnly', response.headers['Set-Cookie'])
        self.assertIn('SameSite=Strict', response.headers['Set-Cookie'])
        self.assertNotIn(self.app.config['SESSION_TOKEN'], self.get('/').text)

    def test_protection(self):
        self.assertEqual(self.client.get('/api/folders', base_url=ORIGIN).status_code, 403)
        self.assertEqual(self.client.get('/api/state', base_url='http://evil.test', headers=self.headers).status_code, 403)
        self.assertEqual(self.client.post('/api/shutdown', base_url=ORIGIN,
                         headers={**self.headers, 'Origin':'http://evil.test'}, json={}).status_code, 403)
        self.assertEqual(self.client.post('/api/shutdown', base_url=ORIGIN,
                         headers={'X-Session-Token':self.app.config['SESSION_TOKEN']}, json={}).status_code, 403)
        self.assertEqual(self.client.get('/api/state', base_url=ORIGIN,
                         headers={**self.headers, 'Sec-Fetch-Site':'cross-site'}).status_code, 403)
        self.assertEqual(self.get('/reports/unknown').status_code, 403)

    def test_folder_navigation_and_validation(self):
        folder = self.folder('ação com espaços')
        response = self.get('/api/folders', query_string={'path':str(folder)})
        self.assertTrue(response.json['has_output'])
        self.assertEqual(response.json['parent'], str(self.base))
        self.assertEqual(self.get('/api/folders', query_string={'path':str(self.base / 'absent')}).status_code, 400)
        self.assertEqual(self.start([self.base]).status_code, 400)
        self.assertEqual(self.post('/api/runs', {'folders':[]}).status_code, 400)
        self.assertEqual(self.client.post('/api/runs', base_url=ORIGIN, headers=self.headers, json=[]).status_code, 400)

    def test_destination_without_permission(self):
        folder = self.folder('results')
        with patch('core.web_app.tempfile.TemporaryFile', side_effect=PermissionError('Sem permissão')):
            response = self.start([folder])
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.jobs.active)

    def test_batch_failure_same_names_and_reports(self):
        first = self.folder('ação/results')
        malformed = self.folder('broken', valid=False)
        last = self.folder('outro/results')
        self.assertEqual(self.start([first, malformed, last]).status_code, 202)
        state = self.wait()
        self.assertEqual([i['status'] for i in state['items']], ['completed','failed','completed'])
        self.assertNotEqual(state['items'][0]['report'], state['items'][2]['report'])
        self.assertEqual(len(json.loads((self.base / 'history.json').read_text())), 2)
        self.post('/api/session')
        ident = state['items'][0]['id']
        response = self.get('/reports/' + ident)
        self.assertEqual(response.status_code, 200)
        self.assertIn('sandbox', response.headers['Content-Security-Policy'])
        response.close()
        response = self.get('/reports/' + ident + '?download=1')
        self.assertIn('attachment', response.headers['Content-Disposition'])
        response.close()
        self.assertEqual(self.get('/reports/unknown').status_code, 404)
        self.assertEqual(self.get('/reports/' + state['items'][1]['id']).status_code, 404)

    def test_remove_one_history_version(self):
        history = self.base / 'history.json'
        entries = [dict(timestamp=f'2026-09-24T10:0{i}:00', version=f'v{i}', total=i + 1,
                        passed=i + 1, failed=0, skipped=0, elapsed_s=1, pass_rate=100,
                        tests=[]) for i in range(3)]
        history.write_text(json.dumps(entries), encoding='utf-8')
        response = self.get('/api/history', query_string={'path': str(history)})
        self.assertEqual([entry['version'] for entry in response.json['entries']], ['v0', 'v1', 'v2'])
        selected = response.json['entries'][1]
        payload = {'path': str(history), **{key: selected[key] for key in ('index', 'timestamp', 'version')}}
        self.assertEqual(self.post('/api/history/remove', payload).status_code, 200)
        self.assertEqual(json.loads(history.read_text(encoding='utf-8')), [entries[0], entries[2]])
        self.assertEqual(self.post('/api/history/remove', payload).status_code, 400)
        self.assertEqual(json.loads(history.read_text(encoding='utf-8')), [entries[0], entries[2]])

    def test_pdf_download_uses_original_execution_snapshot(self):
        folder = self.folder('results')
        self.assertEqual(self.start([folder]).status_code, 202)
        item = self.wait()['items'][0]
        self.assertEqual(item['status'], 'completed')
        pdf_path = Path(item['report']).with_suffix('.pdf')
        self.assertFalse(pdf_path.exists())
        self.assertEqual(self.post('/api/reports/unknown/pdf').status_code, 404)
        self.assertEqual(self.client.post('/api/reports/' + item['id'] + '/pdf',
                                          base_url=ORIGIN, headers={'Origin': ORIGIN}).status_code, 403)
        (folder / 'output.xml').write_text('changed', encoding='utf-8')
        response = self.post('/api/reports/' + item['id'] + '/pdf')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/pdf')
        self.assertIn('attachment', response.headers['Content-Disposition'])
        self.assertTrue(response.data.startswith(b'%PDF-'))
        self.assertEqual(pdf_path.read_bytes(), response.data)
        response.close()
        if shutil.which('pdftotext'):
            pdf_text = subprocess.run(['pdftotext', str(pdf_path), '-'], capture_output=True,
                                      text=True, check=True).stdout
            self.assertIn('Login com credenciais inválidas', pdf_text)
        pdf_path.write_bytes(b'old layout')
        again = self.post('/api/reports/' + item['id'] + '/pdf')
        self.assertEqual(again.status_code, 200)
        again.close()
        self.assertTrue(pdf_path.read_bytes().startswith(b'%PDF-'))

    def test_pdf_failure_keeps_html_available(self):
        self.assertEqual(self.start([self.folder('results')]).status_code, 202)
        item = self.wait()['items'][0]
        with patch('core.web_app.render_pdf', side_effect=OSError('disco cheio')):
            response = self.post('/api/reports/' + item['id'] + '/pdf')
        self.assertEqual(response.status_code, 500)
        self.assertIn('disco cheio', response.json['error'])
        self.assertTrue(Path(item['report']).is_file())
        self.assertFalse(Path(item['report']).with_suffix('.pdf').exists())

    def test_history_remove_rejects_active_job_and_invalid_selection(self):
        history = self.base / 'history.json'
        entry = dict(timestamp='2026-09-24T10:00:00', version='v1', total=1,
                     passed=1, failed=0, skipped=0, elapsed_s=1, pass_rate=100)
        history.write_text(json.dumps([entry]), encoding='utf-8')
        payload = {'path': str(history), 'index': 0, 'timestamp': entry['timestamp'], 'version': 'v1'}
        with self.jobs.lock:
            self.jobs.active = True
            self.assertEqual(self.post('/api/history/remove', payload).status_code, 409)
            self.jobs.active = False
        for invalid in ({**payload, 'index': True}, {**payload, 'version': 'changed'}):
            self.assertEqual(self.post('/api/history/remove', invalid).status_code, 400)
        self.assertEqual(json.loads(history.read_text(encoding='utf-8')), [entry])
        history.write_text('{broken', encoding='utf-8')
        self.assertEqual(self.post('/api/history/remove', payload).status_code, 400)
        self.assertEqual(history.read_text(encoding='utf-8'), '{broken')

    def test_cancel_waits_and_can_start_again(self):
        folder = self.folder('results')
        real_popen = subprocess.Popen
        spawned = threading.Event()
        def slow_process(*args, **kwargs):
            process = real_popen([sys.executable, '-u', '-c', 'import time; print("ready"); time.sleep(30)'],
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            spawned.set()
            return process
        with patch('core.web_jobs.subprocess.Popen', side_effect=slow_process):
            response = self.start([folder, self.folder('pending')])
            run_id = response.json['run_id']
            self.assertTrue(spawned.wait(3))
            self.assertEqual(self.start([folder]).status_code, 409)
            self.assertEqual(self.post('/api/cancel', {'run_id':'old'}).status_code, 409)
            self.assertEqual(self.post('/api/cancel', {'run_id':run_id}).status_code, 202)
            state = self.wait()
            self.assertEqual([i['status'] for i in state['items']], ['cancelled','cancelled'])
        self.assertEqual(self.start([folder]).status_code, 202)
        self.assertEqual(self.wait()['items'][0]['status'], 'completed')
        self.assertEqual(self.post('/api/cancel', {'run_id':run_id}).status_code, 409)

    def test_shutdown_stops_and_rejects_new_runs(self):
        stopped = threading.Event()
        self.app.config['STOP_SERVER'] = stopped.set
        self.assertEqual(self.post('/api/shutdown').status_code, 202)
        self.assertTrue(stopped.wait(3))
        self.assertEqual(self.start([self.folder('results')]).status_code, 409)


if __name__ == '__main__':
    unittest.main()

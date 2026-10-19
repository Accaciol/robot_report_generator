import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from core.pdf_summary import build_summary, collect_systems_data, render_custom_pdf, render_pdf
from core.sqlite_store import SQLiteStore
from models import ExecutionStats, ReportData, Status, SuiteResult, TestResult


class TestPdfSummary(unittest.TestCase):
    def report(self, count=2, failed=True):
        tests = [TestResult(name=f'Cenário {i} com descrição longa e acentuação',
                            status=Status.FAIL if failed and i == 0 else Status.PASS)
                 for i in range(count)]
        suite = SuiteResult(name='Suíte principal', suites=[SuiteResult(name='Funcionalidade ágil', tests=tests)])
        stats = ExecutionStats(total=count, passed=count - int(failed), failed=int(failed), elapsed_s=12.5)
        return ReportData(title='Resumo da execução ágil', generated_at='24/09/2026 10:30:00',
                          version='2026-09-24 #1', stats=stats, suites=[suite], history=[])

    def test_summary_keeps_suite_counts_and_failed_names(self):
        summary = build_summary(self.report())
        self.assertEqual(summary['stats']['pass_rate'], 50.0)
        self.assertEqual(summary['suites'][0]['name'], 'Suíte principal / Funcionalidade ágil')
        self.assertEqual(summary['suites'][0]['failed'], 1)
        self.assertEqual(summary['failures'][0]['test'], 'Cenário 0 com descrição longa e acentuação')
        self.assertEqual(build_summary(self.report(failed=False))['failures'], [])

    def test_pdf_handles_many_rows_long_names_and_no_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = build_summary(self.report(count=75, failed=False))
            summary['suites'] = [dict(suite, name=f'{suite["name"]} {i} ' + 'Nome extenso ' * 9)
                                 for i, suite in enumerate(summary['suites'] * 65)]
            path = Path(directory) / 'resumo.pdf'
            self.assertEqual(render_pdf(summary, path), path)
            self.assertTrue(path.read_bytes().startswith(b'%PDF-'))
            if shutil.which('pdfinfo'):
                info = subprocess.run(['pdfinfo', str(path)], capture_output=True, text=True, check=True)
                pages = next(int(line.split(':', 1)[1]) for line in info.stdout.splitlines()
                             if line.startswith('Pages:'))
                self.assertGreater(pages, 1)
            if shutil.which('pdftotext'):
                extracted = subprocess.run(['pdftotext', str(path), '-'], capture_output=True,
                                           text=True, check=True).stdout
                self.assertIn('Resumo da execução ágil', extracted)
                self.assertIn('Nenhum teste com falha', extracted)

    def test_render_custom_pdf_multi_systems_and_sections(self):
        with tempfile.TemporaryDirectory() as directory:
            sys1 = {
                "id": "sys-alpha",
                "name": "Sistema Alpha",
                "version": "1.0.0",
                "date": "2026-10-15 10:00:00",
                "stats": {"total": 10, "passed": 8, "failed": 2, "skipped": 0, "pass_rate": 80.0, "elapsed_s": 5.0},
                "suites": [{"name": "Auth", "total": 10, "passed": 8, "failed": 2, "skipped": 0}],
                "failures": [{"test": "Login Invalido", "suite": "Auth", "message": "Senha incorreta"}],
                "history": [{"timestamp": "2026-10-15 10:00:00", "version": "1.0.0", "total": 10, "passed": 8, "failed": 2, "pass_rate": 80.0, "elapsed_s": 5.0}],
                "slowest": [{"name": "Login Invalido", "suite": "Auth", "elapsed_s": 3.0}],
            }
            sys2 = {
                "id": "sys-beta",
                "name": "Sistema Beta",
                "version": "2.1.0",
                "date": "2026-10-15 11:00:00",
                "stats": {"total": 20, "passed": 20, "failed": 0, "skipped": 0, "pass_rate": 100.0, "elapsed_s": 15.0},
                "suites": [{"name": "Checkout", "total": 20, "passed": 20, "failed": 0, "skipped": 0}],
                "failures": [],
                "history": [],
                "slowest": [],
            }
            pdf_path = Path(directory) / "multi_relatorio.pdf"
            result = render_custom_pdf([sys1, sys2], pdf_path, title="Relatório Geral QA", sections=["executive", "suites", "failures"])
            self.assertEqual(result, pdf_path)
            self.assertTrue(pdf_path.read_bytes().startswith(b"%PDF-"))

            if shutil.which("pdftotext"):
                text = subprocess.run(["pdftotext", str(pdf_path), "-"], capture_output=True, text=True, check=True).stdout
                self.assertIn("Relatório Geral QA", text)
                self.assertIn("Sistema Alpha", text)
                self.assertIn("Sistema Beta", text)
                self.assertIn("Visão executiva consolidada", text)
                self.assertIn("Comparativo entre sistemas", text)

    def test_collect_systems_data_from_store(self):
        from models import HistoryEntry
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "test.sqlite3"
            store = SQLiteStore(db_path)
            entry = HistoryEntry(
                timestamp="2026-10-15T12:00:00",
                total=5,
                passed=5,
                failed=0,
                skipped=0,
                elapsed_s=1.2,
                pass_rate=100.0,
                version="1.0.0",
                system_version="1.0.0",
                tests=[{"test_name": "T1", "suite_name": "S1", "status": "PASS", "elapsed_s": 1.2}],
            )
            store.import_history_entries("pagamentos", "Pagamentos", [entry])
            data = collect_systems_data(store, ["pagamentos"])
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["id"], "pagamentos")
            self.assertEqual(data[0]["name"], "Pagamentos")
            self.assertEqual(data[0]["stats"]["total"], 5)
            self.assertEqual(data[0]["stats"]["passed"], 5)

    def test_public_api_custom_pdf_endpoint(self):
        from core.web_app import create_app
        from models import HistoryEntry
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "test.sqlite3"
            store = SQLiteStore(db_path)
            entry = HistoryEntry(
                timestamp="2026-10-15T12:00:00",
                total=10,
                passed=9,
                failed=1,
                skipped=0,
                elapsed_s=3.5,
                pass_rate=90.0,
                version="1.0.0",
                system_version="1.0.0",
                tests=[{"test_name": "T1", "suite_name": "S1", "status": "FAIL", "elapsed_s": 1.2}],
            )
            store.import_history_entries("checkout", "Checkout", [entry])
            app = create_app({"DATABASE": str(db_path)})
            client = app.test_client()

            # Test GET
            res_get = client.get("/public/api/pdf?systems=checkout&sections=executive,failures&title=Teste+PDF")
            self.assertEqual(res_get.status_code, 200)
            self.assertEqual(res_get.mimetype, "application/pdf")
            self.assertTrue(res_get.data.startswith(b"%PDF-"))
            res_get.close()

            # Test POST
            res_post = client.post("/public/api/pdf", json={
                "systems": ["checkout"],
                "sections": ["executive", "suites"],
                "title": "Relatório Customizado",
            })
            self.assertEqual(res_post.status_code, 200)
            self.assertEqual(res_post.mimetype, "application/pdf")
            self.assertTrue(res_post.data.startswith(b"%PDF-"))
            res_post.close()



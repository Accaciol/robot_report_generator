import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from core.pdf_summary import build_summary, render_pdf
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

import tempfile
import unittest
from pathlib import Path

from core.report_renderer import ReportRenderer
from models import (
    Artifact,
    ExecutionStats,
    HistoryEntry,
    KeywordResult,
    ReportData,
    Status,
    SuiteResult,
    TestResult,
)


class TestReportRenderer(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)
        self.output_html = self.base_dir / "output.html"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_render_report_html(self):
        stats = ExecutionStats(total=2, passed=1, failed=1, skipped=0, elapsed_s=12.3)
        kw_pass = KeywordResult(name="Keyword Pass", status=Status.PASS, elapsed_s=1.0)
        kw_fail = KeywordResult(name="Keyword Fail", status=Status.FAIL, elapsed_s=2.0)

        test_pass = TestResult(
            name="Cenário de Sucesso",
            status=Status.PASS,
            suite_name="Feature A",
            tags=["smoke"],
            keywords=[kw_pass],
            elapsed_s=1.0,
        )
        test_fail = TestResult(
            name="Cenário com Falha",
            status=Status.FAIL,
            suite_name="Feature A",
            tags=["regression"],
            message="Erro de validação esperado",
            failed_step="Keyword Fail",
            keywords=[kw_fail],
            elapsed_s=2.0,
        )

        suite = SuiteResult(
            name="Feature A",
            tests=[test_pass, test_fail],
        )

        history = [
            HistoryEntry(
                timestamp="2026-09-10T10:00:00",
                total=2,
                passed=1,
                failed=1,
                skipped=0,
                elapsed_s=12.3,
                pass_rate=50.0,
                version="2026-09-10 #1",
            )
        ]

        report_data = ReportData(
            title="Relatório de Testes Automatizados - QA",
            stats=stats,
            suites=[suite],
            history=history,
            generated_at="11/09/2026 12:00:00",
            version="2026-09-10 #1",
        )

        renderer = ReportRenderer(base_dir=self.base_dir)
        rendered_path = renderer.render(report_data, str(self.output_html))

        self.assertTrue(rendered_path.is_file())
        content = rendered_path.read_text(encoding="utf-8")

        self.assertIn("Relatório de Testes Automatizados - QA", content)
        self.assertIn("Cenário de Sucesso", content)
        self.assertIn("Cenário com Falha", content)
        self.assertIn("Erro de validação esperado", content)
        self.assertIn("themeToggle", content)
        self.assertIn("treeSearch", content)
        self.assertIn("filter-btn", content)
        self.assertIn("copyFailureError", content)


if __name__ == "__main__":
    unittest.main()

"""Teste opt-in: ROBOT_REPORT_BROWSER_TESTS=1 python -m unittest tests.test_catalog_browser."""
import base64
import os
from pathlib import Path
import tempfile
import unittest

from core.catalog import Catalog
from core.catalog_report import render_catalog
from tests.test_catalog import make_results


@unittest.skipUnless(os.environ.get("ROBOT_REPORT_BROWSER_TESTS") == "1", "Teste de navegador opt-in")
class TestCatalogBrowser(unittest.TestCase):
    def setUp(self):
        from playwright.sync_api import sync_playwright
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.catalog = Catalog(self.root / "systems")
        image = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWQAAAABJRU5ErkJggg==")
        self.old_id = self.catalog.import_results(make_results(self.root, 10, marker="alpha-old", image=image), "alpha", "Alpha")
        self.new_id = self.catalog.import_results(make_results(self.root, 12, failed=False, marker="alpha-current", image=image), "alpha")
        self.catalog.import_results(make_results(self.root, 11, marker="beta-only", image=image), "beta", "Beta")
        empty_id = self.catalog.import_results(make_results(self.root, 13, marker="empty"), "empty", "Vazio")
        self.catalog.remove("empty", empty_id)
        self.report = self.root / "report.html"
        self.render()
        self.playwright = sync_playwright().start()
        self.addCleanup(self.playwright.stop)
        executable = os.environ.get("ROBOT_REPORT_BROWSER")
        self.browser = self.playwright.chromium.launch(headless=True, executable_path=executable)
        self.addCleanup(self.browser.close)
        self.page = self.browser.new_page(viewport={"width": 1280, "height": 900})
        self.errors = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        chart_path = os.environ.get("ROBOT_REPORT_CHART_JS")
        self.chart_enabled = bool(chart_path)
        if chart_path:
            chart = Path(chart_path).read_bytes()
            self.page.route("**/chart.umd.min.js", lambda route: route.fulfill(body=chart, content_type="application/javascript"))
        else:
            # Também valida a consulta sem internet, com gráficos indisponíveis.
            self.page.route("**/chart.umd.min.js", lambda route: route.abort())
        self.page.goto(self.report.as_uri())

    def render(self):
        render_catalog(str(self.catalog.root), str(self.report), "Relatório dos sistemas")

    def frame(self, system):
        return self.page.frame_locator(f'iframe[data-system-id="{system}"]')

    def test_selection_history_filters_evidence_and_empty_state(self):
        from playwright.sync_api import expect
        self.assertEqual(self.page.locator("#systemSelect").input_value(), "alpha")
        alpha = self.frame("alpha")
        expect(alpha.locator("#metricFailed")).to_have_text("0")
        expect(alpha.locator("#versionSelectPo option")).to_have_count(2)
        self.assertIn("alpha-current", alpha.locator("#suitesContainer").text_content())
        self.assertNotIn("beta-only", alpha.locator("#suitesContainer").text_content())
        self.assertTrue(alpha.locator("img[data-src]").first.get_attribute("data-src").startswith("data:image/png;base64,"))
        expect(alpha.locator("#flakyPanel")).to_be_visible()
        if self.chart_enabled:
            self.assertEqual(alpha.locator("body").evaluate("() => reportTrendChart.data.datasets[1].data"), [1, 0])
        alpha.locator("#versionSelectPo").select_option("0")
        expect(alpha.locator("#metricFailed")).to_have_text("1")
        alpha.locator('[data-tab="dev"]').click()
        expect(alpha.locator("#technicalVersionNotice")).to_be_visible()
        expect(alpha.locator("#suitesContainer")).to_be_hidden()
        alpha.locator('[data-tab="failures"]').click()
        expect(alpha.locator("#historicalFailures")).to_contain_text("Login com credenciais inválidas")
        alpha.locator("#versionVisibility summary").click()
        alpha.locator('input[data-version-index="0"]').uncheck()
        expect(alpha.locator("#visibleVersionCount")).to_have_text("(1/2)")
        alpha.locator('[data-tab="po"]').click()
        expect(alpha.locator("#metricFailed")).to_have_text("0")
        if self.chart_enabled:
            self.assertEqual(alpha.locator("body").evaluate("() => reportTrendChart.data.datasets[1].data"), [0])
        expect(alpha.locator("#flakyPanel")).to_be_hidden()
        self.page.locator("#systemSelect").select_option("beta")
        beta = self.frame("beta")
        expect(beta.locator("#metricFailed")).to_have_text("1")
        expect(beta.locator("#versionSelectPo option")).to_have_count(1)
        self.assertNotIn("alpha-current", beta.locator("#suitesContainer").text_content())
        beta.locator('[data-tab="versions"]').click()
        expect(beta.locator("#versionTests")).to_contain_text("Adicionado")
        self.page.locator("#systemSelect").select_option("alpha")
        expect(alpha.locator("#visibleVersionCount")).to_have_text("(1/2)")
        alpha.locator('input[data-version-index="1"]').uncheck()
        expect(alpha.locator("#noVisibleVersions")).to_be_visible()
        alpha.locator("#restoreVersions").click()
        expect(alpha.locator("#visibleVersionCount")).to_have_text("(2/2)")
        self.page.locator("#systemSelect").select_option("empty")
        expect(self.page.locator("#emptyState")).to_have_text("Nenhuma execução cadastrada para Vazio.")
        self.assertEqual(self.page.locator("iframe:visible").count(), 0)
        self.page.locator("#systemSelect").select_option("alpha")
        alpha.locator("#versionVisibility summary").click()
        screenshot = os.environ.get("ROBOT_REPORT_SCREENSHOT")
        if screenshot:
            self.page.screenshot(path=screenshot, full_page=True)
        self.assertEqual(self.errors, [])

    def test_removed_current_uses_summary_without_wrong_details(self):
        from playwright.sync_api import expect
        self.catalog.remove("alpha", self.new_id)
        self.render()
        self.page.reload()
        alpha = self.frame("alpha")
        expect(alpha.locator("#metricFailed")).to_have_text("1")
        expect(alpha.locator("#versionSelectPo option")).to_have_count(1)
        expect(alpha.locator(".version-context").first).to_contain_text("detalhes completos indisponíveis")
        alpha.locator('[data-tab="dev"]').click()
        expect(alpha.locator("#technicalVersionNotice")).to_be_visible()
        expect(alpha.locator("#suitesContainer")).to_be_hidden()
        self.assertNotIn("alpha-current", self.report.read_text())
        self.catalog.remove("alpha", self.old_id)
        self.render()
        self.page.reload()
        expect(self.page.locator("#emptyState")).to_have_text("Nenhuma execução cadastrada para Alpha.")
        self.assertEqual(self.errors, [])

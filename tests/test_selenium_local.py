"""Opt-in: navegador real, exclusivamente contra páginas sintéticas locais."""
import os
import tempfile
import threading
import unittest
from pathlib import Path

from werkzeug.serving import make_server

from complemento.local_review import Review
from complemento.local_service import create_app
from complemento.selenium_demo import DemoDriver


@unittest.skipUnless(os.environ.get('RUZY_SELENIUM_TESTS') == '1', 'Opt-in Selenium local')
class SeleniumLocalTests(unittest.TestCase):
    def test_offline_button_and_sequential_review(self):
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            panel = (Path(__file__).resolve().parents[1] / 'complemento/report_panel.html').read_text(encoding='utf-8')
            report = '<!doctype html><html><body><main><h1>Robot sintético</h1>' + panel + '</main></body></html>'
            offline = root / 'offline.html'
            offline.write_text(report, encoding='utf-8')
            matrix = {'report_id': 'a' * 64, 'artifacts': [], 'candidates': [
                {'candidate_id': str(index), 'status': 'FAIL', 'test_name': f'Test {index}',
                 'message': 'Synthetic failure', 'artifact_ids': []} for index in range(3)]}
            review = Review(matrix, root / 'state.json')
            choice = os.environ.get('RUZY_TEST_BROWSER', 'chrome')
            if choice == 'edge':
                from selenium.webdriver.edge.service import Service
                create_browser, options = webdriver.Edge, webdriver.EdgeOptions()
            else:
                from selenium.webdriver.chrome.service import Service
                create_browser, options = webdriver.Chrome, webdriver.ChromeOptions()
            options.add_argument('--headless=new')
            options.add_argument('--window-size=1280,900')
            options.add_experimental_option('prefs', {'download.default_directory': str(root)})
            browser = create_browser(options=options)
            driver_path = browser.service.path
            worker = DemoDriver(review, choice, factory=lambda: create_browser(service=Service(driver_path), options=options))
            app = create_app(review, report, worker.submit)
            server = make_server('127.0.0.1', 0, app, threaded=True)
            origin = f'http://127.0.0.1:{server.server_port}'
            app.config['LOCAL_ORIGIN'] = origin
            worker.configure(origin, app.config['SESSION_TOKEN'])
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            wait = WebDriverWait(browser, 30)
            try:
                browser.get(offline.as_uri())
                self.assertFalse(browser.find_element(By.ID, 'ruzy-prepare').is_enabled())
                self.assertNotIn('Instale', browser.find_element(By.TAG_NAME, 'body').text)
                browser.get(origin + '/#' + app.config['SESSION_TOKEN'])
                wait.until(lambda b: b.find_element(By.ID, 'report').get_attribute('src').endswith('/report'))
                browser.switch_to.frame('report')
                wait.until(lambda b: b.find_element(By.ID, 'ruzy-prepare').is_enabled())
                browser.find_element(By.ID, 'ruzy-prepare').click()
                browser.switch_to.default_content()
                wait.until(lambda b: b.find_element(By.ID, 'controls').is_displayed())
                browser.find_element(By.NAME, 'board_url').send_keys('https://dev.azure.com/o/p/_boards')
                browser.find_element(By.CSS_SELECTOR, '#configuration button').click()
                wait.until(lambda b: b.find_element(By.ID, 'start').is_displayed())
                browser.find_element(By.ID, 'start').click()
                wait.until(lambda _: review.snapshot()['status'] == 'awaiting_decision')
                self.assertEqual(worker.driver.find_element(By.ID, 'title').get_attribute('value'), 'Test 0')
                worker.driver.find_element(By.ID, 'title').clear()
                worker.driver.find_element(By.ID, 'title').send_keys('Reviewed title')
                worker.driver.find_element(By.ID, 'save').click()
                wait.until(lambda _: review.snapshot()['status'] == 'awaiting_decision' and review.snapshot()['active'] == '1')
                worker.driver.find_element(By.ID, 'discard').click()
                worker.driver.switch_to.alert.accept()
                wait.until(lambda _: review.snapshot()['status'] == 'awaiting_decision' and review.snapshot()['active'] == '2')
                worker.driver.close()
                wait.until(lambda _: review.snapshot()['status'] == 'paused')
                wait.until(lambda b: b.find_element(By.ID, 'start').is_displayed())
                browser.find_element(By.ID, 'start').click()
                wait.until(lambda _: review.snapshot()['status'] == 'awaiting_decision')
                worker.driver.find_element(By.ID, 'save').click()
                wait.until(lambda _: review.snapshot()['status'] == 'completed')
                self.assertEqual([item['status'] for item in review.snapshot()['results']], ['saved', 'discarded', 'saved'])
                self.assertEqual(review.snapshot()['results'][0]['reviewed_title'], 'Reviewed title')
                wait.until(lambda _: (root / 'ruzy-resultado-simulado.html').exists())
                evidence = Path.cwd() / 'test-results'
                evidence.mkdir(exist_ok=True)
                browser.save_screenshot(str(evidence / 'local-review-completed.png'))
                final = (root / 'ruzy-resultado-simulado.html').read_text(encoding='utf-8')
                self.assertNotIn(app.config['SESSION_TOKEN'], final)
                self.assertIn('SIM-0001', final)
                self.assertIn('Robot sintético', final)
                result = root / 'final.html'
                result.write_text(final, encoding='utf-8')
                browser.get(result.as_uri())
                self.assertFalse(browser.find_element(By.ID, 'ruzy-prepare').is_enabled())
                browser.save_screenshot(str(evidence / 'local-portable-result.png'))
            finally:
                worker.close()
                browser.quit()
                server.shutdown()
                server.server_close()

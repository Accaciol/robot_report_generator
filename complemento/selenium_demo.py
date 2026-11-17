"""WebDriver dedicado exclusivamente ao formulário local sintético."""
from __future__ import annotations

import queue
import threading

from complemento.local_review import Review


class DemoDriver:
    def __init__(self, review: Review, browser: str, factory=None):
        self.review = review
        self.browser = browser
        self.factory = factory
        self.commands = queue.Queue(maxsize=1)
        self.stopping = threading.Event()
        self.origin = self.token = ''
        self.driver = None
        self.scheduled = False
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._work, daemon=True)

    def configure(self, origin: str, token: str) -> None:
        self.origin, self.token = origin, token
        self.thread.start()

    def submit(self) -> None:
        with self.lock:
            if self.scheduled or self.review.snapshot()['status'] not in ('ready', 'paused'):
                raise ValueError('Já existe uma abertura em andamento.')
            self.scheduled = True
            self.commands.put_nowait(True)

    def _create_driver(self):
        if self.factory:
            return self.factory()
        from selenium import webdriver
        # Selenium creates its own browser profile; never attach to the user's default profile.
        if self.browser == 'edge':
            return webdriver.Edge()
        return webdriver.Chrome()

    def _open(self) -> None:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait

        candidate, _ = self.review.open_next()
        if self.driver is None:
            self.driver = self._create_driver()
            self.driver.set_page_load_timeout(20)
            self.driver.get(self.origin + '/#' + self.token)
            WebDriverWait(self.driver, 15).until(lambda browser: browser.get_cookie('ruzy_session'))
        self.driver.get(self.origin + '/form')
        title = WebDriverWait(self.driver, 10).until(lambda browser: browser.find_element(By.ID, 'title'))
        title.clear()
        title.send_keys(candidate['test_name'][:500])
        description = self.driver.find_element(By.ID, 'description')
        description.clear()
        description.send_keys(candidate.get('message', '')[:20000])
        self.review.opened()

    def _work(self) -> None:
        try:
            while not self.stopping.is_set():
                try:
                    self.commands.get(timeout=0.5)
                except queue.Empty:
                    if self.driver and self.review.snapshot()['status'] == 'awaiting_decision':
                        try:
                            if self.driver.current_url != self.origin + '/form':
                                self.review.pause()
                        except Exception:
                            self.review.pause()
                            self._quit()
                    continue
                try:
                    self._open()
                except Exception:
                    # Do not echo driver errors: they can include machine paths or session details.
                    self.review.pause()
                    self._quit()
                finally:
                    with self.lock:
                        self.scheduled = False
        finally:
            self._quit()

    def _quit(self) -> None:
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

    def close(self) -> None:
        self.stopping.set()
        if self.thread.is_alive():
            self.thread.join(timeout=5)

"""Real-browser demonstration tests; never contacts Azure or a personal profile."""
import argparse
import json
import os
import re
from pathlib import Path
import tempfile

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'test-results'


def scenario(channel: str, package: str) -> dict:
    RESULTS.mkdir(exist_ok=True)
    console_errors = []
    with tempfile.TemporaryDirectory(prefix='ruzy-browser-', dir=RESULTS) as profile, sync_playwright() as p:
        options = {'channel': channel} if channel != 'chromium' else {}
        context = p.chromium.launch_persistent_context(profile, headless=True,
            ignore_default_args=['--disable-extensions'], args=['--enable-unsafe-extension-debugging'],
            viewport={'width': 1280, 'height': 900}, accept_downloads=True, **options)
        try:
            browser_version = context.browser.version
            session = context.browser.new_browser_cdp_session()
            extension = session.send('Extensions.loadUnpacked', {'path': str(ROOT / 'extensions' / package)})
            page = context.new_page()
            context.on('page', lambda tab: tab.on('pageerror', lambda error: console_errors.append(str(error))))
            page.on('pageerror', lambda error: console_errors.append(str(error)))
            page.goto((ROOT / 'demo' / 'relatorio-demo.html').as_uri())
            expect(page.locator('#ruzy-status')).to_contain_text('Extensão conectada')
            page.locator('#ruzy-prepare').click()
            dialog = page.get_by_role('dialog')
            dialog.locator('[name=board_url]').fill('https://example.invalid/board')
            dialog.get_by_role('button', name='Confirmar e preparar').click()
            expect(dialog.locator('[role=alert]')).to_contain_text('dev.azure.com')
            dialog.locator('[name=board_url]').fill('https://dev.azure.com/equipe/Projeto%20QA/_boards/board/t/Time/Stories')
            dialog.locator('[name=desired_column]').fill('Triagem')
            dialog.locator('#ruzy-remember').check()
            dialog.get_by_role('button', name='Confirmar e preparar').click()
            expect(page.locator('#ruzy-start')).to_be_visible()
            expect(page.locator('#ruzy-progress')).to_have_attribute('value', '100')
            with context.expect_page() as opened:
                page.locator('#ruzy-start').click()
            form = opened.value
            expect(form.locator('#status')).to_contain_text('Candidato 1 de 3')
            expect(form.locator('#evidence img')).to_have_count(1)
            expect(form.locator('#destination')).to_contain_text('Projeto QA')
            form.locator('#title').fill('')
            form.locator('#save').click()
            expect(form.locator('#status')).to_contain_text('Candidato 1 de 3')
            expect(page.locator('#ruzy-results')).not_to_contain_text('SIM-0001')
            form.locator('#title').fill('Login fictício revisado pelo analista')
            form.screenshot(path=str(RESULTS / f'{package}-{channel}-form.png'), full_page=True)
            form.locator('#save').click()
            expect(form.locator('#status')).to_contain_text('Candidato 2 de 3')
            expect(page.locator('#ruzy-results')).to_contain_text('SIM-0001')
            # Terminate the background worker; a decision must reload durable state.
            targets = session.send('Target.getTargets')['targetInfos']
            for target in targets:
                if target['type'] == 'service_worker' and extension['id'] in target['url']:
                    session.send('Target.closeTarget', {'targetId': target['targetId']})
            active = [tab for tab in context.pages if tab.url.startswith('chrome-extension://' + extension['id'] + '/form.html')]
            assert len(active) == 1, 'Only one form tab may exist.'
            form.on('dialog', lambda prompt: prompt.accept())
            form.locator('#discard').click()
            expect(form.locator('#status')).to_contain_text('Candidato 3 de 3')
            form.close()
            expect(page.locator('#ruzy-status')).to_contain_text('Fila pausada')
            # A reload simulates loss of the content script's in-memory state.
            page.reload()
            expect(page.locator('#ruzy-results')).to_contain_text('SIM-0001')
            with context.expect_page() as resumed:
                page.locator('#ruzy-resume').click()
            form = resumed.value
            expect(form.locator('#status')).to_contain_text('Candidato 3 de 3')
            expect(form.locator('#evidence img')).to_have_count(1)
            form.set_viewport_size({'width': 360, 'height': 800})
            assert form.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Form overflows mobile viewport.'
            with page.expect_download() as downloaded:
                form.locator('#save').click()
            html_path = RESULTS / f'{package}-{channel}-resultado.html'
            downloaded.value.save_as(html_path)
            expect(page.locator('#ruzy-status')).to_contain_text('Revisão simulada concluída')
            with page.expect_download() as json_download:
                page.locator('#ruzy-json').click()
            json_path = RESULTS / f'{package}-{channel}-decisoes.json'
            json_download.value.save_as(json_path)
            data = json.loads(json_path.read_text(encoding='utf-8'))
            assert [r['status'] for r in data['results']] == ['saved_simulation', 'discarded', 'saved_simulation']
            assert [r['simulation_id'] for r in data['results']] == ['SIM-0001', None, 'SIM-0002']
            assert all(r['azure_id'] is None and r['azure_url'] is None for r in data['results'])
            assert data['config']['desired_column'] == 'Triagem'
            assert data['results'][0]['reviewed_title'] == 'Login fictício revisado pelo analista'
            page.locator('#ruzy-panel').screenshot(path=str(RESULTS / f'{package}-{channel}-report.png'))
            final = context.new_page()
            final.goto(html_path.as_uri())
            expect(final.locator('#ruzy-results')).to_contain_text('SIM-0002')
            expect(final.locator('#ruzy-prepare')).to_have_count(0)
            form.close()
            page.on('dialog', lambda prompt: prompt.accept())
            page.locator('#ruzy-clear').click()
            expect(page.locator('#ruzy-prepare')).to_be_enabled()
            page.locator('#ruzy-prepare').click()
            expect(page.get_by_role('dialog').locator('[name=desired_column]')).to_have_value('Triagem')
            page.get_by_role('button', name='Cancelar', exact=True).click()
            # Zero failures must finish without opening a new form.
            original = (ROOT / 'demo' / 'relatorio-demo.html').read_text(encoding='utf-8')
            found = re.search(r'(<script type="application/json" id="ruzy-matrix">)(.*?)(</script>)', original, re.S)
            empty = json.loads(found.group(2));empty['report_id'] = 'b'*64;empty['candidates'] = [];empty['artifacts'] = []
            empty_path = RESULTS / f'{package}-{channel}-empty.html'
            empty_path.write_text(original[:found.start(2)]+json.dumps(empty)+original[found.end(2):], encoding='utf-8')
            empty_page = context.new_page();empty_page.goto(empty_path.as_uri())
            expect(empty_page.locator('#ruzy-prepare')).to_be_enabled()
            count_before = len(context.pages)
            empty_page.locator('#ruzy-prepare').click()
            empty_page.get_by_role('button', name='Confirmar e preparar').click()
            expect(empty_page.locator('#ruzy-status')).to_contain_text('0 de 0')
            expect(empty_page.locator('#ruzy-start')).not_to_be_visible()
            assert len(context.pages) == count_before
            assert not console_errors, console_errors
            return {'channel':channel, 'package':package, 'version':browser_version, 'result':'passed',
                    'checks':['configuration', 'invalid_destination', 'evidence_preview', 'required_title',
                              'one_form', 'save', 'discard', 'pause_on_close', 'reload_resume',
                              'worker_restart', 'mobile_form', 'automatic_html_export', 'json_export',
                              'no_real_ids', 'portable_result', 'reviewed_title', 'clear_data', 'remember_preferences', 'zero_failures'],
                    'page_errors':console_errors}
        finally:
            context.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--channel', choices=['chrome','msedge','chromium'], default='chrome')
    parser.add_argument('--package', choices=['chrome','edge'], default='chrome')
    args = parser.parse_args()
    result = scenario(args.channel, args.package)
    (RESULTS / f'{args.package}-{args.channel}-checks.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result))

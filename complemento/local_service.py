"""Serviço local e interface confiável para a demonstração Selenium."""
from __future__ import annotations

import argparse
import hmac
import html
import json
import secrets
import webbrowser
from pathlib import Path

from flask import Flask, abort, jsonify, make_response, render_template, request
from werkzeug.serving import make_server

from complemento.generate_report import generate
from complemento.local_review import Review


def create_app(review: Review, report_html: str, open_form) -> Flask:
    app = Flask(__name__, template_folder='local_ui', static_folder='local_ui', static_url_path='/assets')
    app.config.update(LOCAL_ORIGIN='http://127.0.0.1:8877', SESSION_TOKEN=secrets.token_urlsafe(32),
                      MAX_CONTENT_LENGTH=64 * 1024)

    def valid(value):
        return isinstance(value, str) and hmac.compare_digest(value.encode(), app.config['SESSION_TOKEN'].encode())

    @app.before_request
    def protect():
        origin = app.config['LOCAL_ORIGIN']
        if (request.host_url.rstrip('/') != origin
                or request.headers.get('Origin') not in (None, origin)
                or request.headers.get('Sec-Fetch-Site') == 'cross-site'):
            abort(403)
        if request.method == 'POST' and request.headers.get('Origin') != origin:
            abort(403)
        if request.path.startswith('/api/') and not valid(request.headers.get('X-Ruzy-Token')):
            abort(403)
        if request.path in ('/report', '/form', '/decision') and not valid(request.cookies.get('ruzy_session')):
            abort(403)

    @app.after_request
    def headers(response):
        response.headers.update({'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
                                 'Referrer-Policy': 'no-referrer', 'X-Frame-Options': 'SAMEORIGIN'})
        if request.path == '/report':
            response.headers['Content-Security-Policy'] = 'sandbox allow-scripts allow-downloads'
        else:
            response.headers['Content-Security-Policy'] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
                "object-src 'none'; base-uri 'none'; frame-ancestors 'self'")
        return response

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(413)
    def error_response(error):
        return jsonify(error='Requisição local inválida ou não autorizada.'), error.code

    @app.errorhandler(OSError)
    def persistence_error(error):
        return jsonify(error='Não foi possível gravar o estado local. Confira o armazenamento antes de continuar.'), 503

    def data():
        value = request.get_json(silent=True)
        if not isinstance(value, dict):
            abort(400)
        return value

    def perform(action):
        try:
            action()
            return jsonify(review.snapshot())
        except ValueError as exc:
            return jsonify(error=str(exc)), 400

    @app.get('/')
    def index():
        return render_template('controller.html')

    @app.post('/api/session')
    def session():
        response = jsonify(ok=True)
        response.set_cookie('ruzy_session', app.config['SESSION_TOKEN'], httponly=True, samesite='Strict')
        return response

    @app.get('/api/state')
    def state():
        return jsonify(review.snapshot())

    @app.post('/api/prepare')
    def prepare():
        value = data()
        return perform(lambda: review.prepare(value))

    @app.post('/api/start')
    def start():
        def action():
            if review.snapshot()['status'] not in ('ready', 'paused'):
                raise ValueError('A fila não está pronta para iniciar ou retomar.')
            open_form()
        return perform(action)

    @app.get('/report')
    def report():
        # The untrusted generated report never receives the API token or same-origin privileges.
        script = (Path(__file__).parent / 'local_ui' / 'relay.js').read_text(encoding='utf-8')
        script = script.replace('__LOCAL_ORIGIN__', json.dumps(app.config['LOCAL_ORIGIN']))
        return report_html.replace('</body>', '<script>' + script + '</script></body>', 1)

    @app.get('/form')
    def form():
        try:
            candidate, attempt = review.form()
        except ValueError:
            abort(400)
        artifacts = []
        for artifact in review.matrix.get('artifacts', []):
            uri = artifact.get('data_uri', '')
            if (artifact['artifact_id'] in candidate.get('artifact_ids', [])
                    and isinstance(uri, str) and len(uri) <= 4 * 1024 * 1024
                    and uri.startswith(('data:image/png;base64,', 'data:image/jpeg;base64,',
                                        'data:image/webp;base64,'))):
                artifacts.append(artifact)
        return render_template('form.html', candidate=candidate, attempt=attempt, artifacts=artifacts)

    @app.post('/decision')
    def decision():
        value = data()
        def action():
            review.decide(value.get('candidate_id'), value.get('attempt'), value.get('status'),
                          value.get('title', ''), value.get('description', ''))
            if review.snapshot()['status'] == 'ready':
                try:
                    open_form()
                except ValueError:
                    # This decision is already durable. Keep the next item ready for manual resume.
                    pass
        return perform(action)

    @app.get('/api/export/<kind>')
    def export(kind):
        snapshot = review.snapshot()
        if kind == 'json':
            output = json.dumps(snapshot, ensure_ascii=False, indent=2)
            mime = 'application/json'
        elif kind == 'html':
            candidates = {item['candidate_id']: item['test_name'] for item in review.matrix['candidates']}
            rows = ''.join('<tr>' + ''.join('<td>' + html.escape(str(value or '—')) + '</td>'
                          for value in (item['reviewed_title'] or candidates[item['candidate_id']],
                                        'Salvo na simulação' if item['status'] == 'saved' else 'Descartado',
                                        item['simulation_id'], 'Não enviados ao Azure')) + '</tr>'
                           for item in snapshot['results'])
            table = ('<section id="ruzy-final-result"><h2>Resultado da revisão — SIMULAÇÃO</h2>'
                     '<p>Nenhum item real foi criado no Azure. IDs reais permanecem ausentes.</p>'
                     '<table style="width:100%;text-align:left;border-spacing:12px"><thead><tr>'
                     '<th>Teste / título</th><th>Decisão</th><th>Código simulado</th>'
                     '<th>Anexos</th></tr></thead><tbody>' + rows + '</tbody></table></section>')
            # Export the original portable report, not the service wrapper or its session.
            output = report_html.replace('</main>', table + '</main>', 1)
            mime = 'text/html'
        else:
            abort(400)
        response = make_response(output)
        response.mimetype = mime
        response.headers['Content-Disposition'] = f'attachment; filename="ruzy-resultado-simulado.{kind}"'
        return response

    return app


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--results-dir', type=Path, required=True)
    cli.add_argument('--report', type=Path, default=Path('relatorio-ruzy.html'))
    cli.add_argument('--state-dir', type=Path, default=Path('.ruzy-state'))
    cli.add_argument('--browser', choices=('edge', 'chrome'), default='edge')
    cli.add_argument('--port', type=int, default=8877)
    args = cli.parse_args()
    matrix = generate(args.results_dir.resolve(), args.report.resolve())
    review = Review(matrix, args.state_dir / (matrix['report_id'] + '.json'))
    from complemento.selenium_demo import DemoDriver
    driver = DemoDriver(review, args.browser)
    app = create_app(review, args.report.read_text(encoding='utf-8'), driver.submit)
    server = make_server('127.0.0.1', args.port, app, threaded=True)
    origin = f'http://127.0.0.1:{server.server_port}'
    app.config['LOCAL_ORIGIN'] = origin
    driver.configure(origin, app.config['SESSION_TOKEN'])
    address = origin + '/#' + app.config['SESSION_TOKEN']
    print('Ruzy local em execução. Use a janela aberta; Ctrl+C encerra. Modo: SIMULAÇÃO.')
    webbrowser.open(address)
    try:
        server.serve_forever()
    finally:
        driver.close()
        server.server_close()


if __name__ == '__main__':
    main()

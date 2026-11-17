"""Contrato de dados do relatório para a revisão local, sem reinterpretar o XML."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def validate_artifact_paths(suites: list, results_dir: Path) -> None:
    """Keep untrusted XML from embedding unrelated local files in the demo."""
    root = results_dir.resolve()

    def keywords(items: list) -> None:
        for keyword in items:
            for artifact in keyword.artifacts:
                value = artifact.original_path
                if value.startswith(('http://', 'https://', 'data:')):
                    raise ValueError('Evidência externa ou inline no XML não é aceita nesta demonstração.')
                target = (root / value).resolve()
                if not target.is_relative_to(root):
                    raise ValueError('Referência de evidência fora da pasta de resultados.')
            keywords(keyword.children)

    for suite in suites:
        for test in suite.tests:
            keywords(test.keywords)
        validate_artifact_paths(suite.suites, root)


def build_matrix(data: Any, execution_id: str) -> dict:
    artifacts: dict[str, dict] = {}
    candidates = []

    def collect_artifacts(keywords: list) -> list[str]:
        ids = []
        for keyword in keywords:
            for artifact in keyword.artifacts:
                value = artifact.embedded_data_uri or ''
                key = hashlib.sha256((artifact.kind + artifact.original_path + value).encode()).hexdigest()[:24]
                artifacts[key] = {
                    'artifact_id': key, 'name': Path(artifact.original_path).name,
                    'kind': artifact.kind, 'data_uri': value,
                    'missing': artifact.missing or not value.startswith('data:'),
                }
                ids.append(key)
            ids.extend(collect_artifacts(keyword.children))
        return list(dict.fromkeys(ids))

    def collect(suites: list, parents: tuple = ()) -> None:
        for suite in suites:
            path = (*parents, suite.name)
            for test in suite.tests:
                if not test.is_failed:
                    continue
                index = len(candidates)
                candidates.append({
                    'candidate_id': f'{execution_id}:{index}',
                    'stable_test_id': test.stable_id, 'suite_path': ' / '.join(path),
                    'test_name': test.name, 'status': 'FAIL', 'message': test.message,
                    'failed_step': test.failed_step or '', 'gherkin_steps': test.gherkin_steps,
                    'tags': test.tags, 'environment': data.environment,
                    'artifact_ids': collect_artifacts(test.keywords),
                })
            collect(suite.suites, path)

    collect(data.suites)
    return {'schema_version': 1, 'report_id': execution_id, 'execution_id': execution_id,
            'generated_at': data.generated_at, 'mode': 'simulation',
            'candidates': candidates, 'artifacts': list(artifacts.values())}


def inject_controls(html: str, matrix: dict) -> str:
    payload = json.dumps(matrix, ensure_ascii=False).replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')
    panel = Path(__file__).with_name('report_panel.html').read_text(encoding='utf-8')
    block = panel + '\n<script type="application/json" id="ruzy-matrix">' + payload + '</script>'
    if '</main>' not in html:
        raise ValueError('O relatório não contém o ponto de integração esperado.')
    return html.replace('</main>', block + '\n</main>', 1)

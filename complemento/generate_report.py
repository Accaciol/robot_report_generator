"""Gera relatório com o complemento, reutilizando parser e renderer originais."""
from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.report_renderer import ReportRenderer
from core.xml_parser import RobotOutputParser
from models import ReportData
from complemento.matrix import build_matrix, inject_controls, validate_artifact_paths


def generate(results_dir: Path, output: Path) -> dict:
    source = results_dir / 'output.xml'
    execution_id = hashlib.sha256(source.read_bytes()).hexdigest()
    parser = RobotOutputParser(str(source))
    suites, stats = parser.parse()
    validate_artifact_paths(suites, results_dir)
    data = ReportData(stats, suites, [], datetime.now().isoformat(timespec='seconds'),
                      title='Relatório de testes · demonstração Ruzy', environment=parser.environment,
                      errors=parser.errors)
    renderer = ReportRenderer(results_dir)
    # Keep the demo offline: trend charts have no history in this report.
    renderer._load_chart_js = lambda: ('inline', '')
    html = renderer.render_html(data)
    matrix = build_matrix(data, execution_id)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(inject_controls(html, matrix), encoding='utf-8')
    return matrix


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--results-dir', type=Path, required=True)
    cli.add_argument('--report', type=Path, default=ROOT / 'demo' / 'relatorio-demo.html')
    args = cli.parse_args()
    try:
        matrix = generate(args.results_dir.resolve(), args.report.resolve())
    except (OSError, ValueError) as error:
        cli.exit(1, f'Não foi possível gerar o relatório: {error}\n')
    print(f"Relatório: {args.report.resolve()} ({len(matrix['candidates'])} falhas candidatas)")

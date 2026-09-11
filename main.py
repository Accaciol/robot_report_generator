"""Ponto de entrada: gera relatorio.html a partir de output.xml.

Uso:
    python main.py --results-dir results --history history.json --report relatorio.html
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from core.history_manager import HistoryManager
from core.report_renderer import ReportRenderer
from core.xml_parser import RobotOutputParser
from models import ReportData

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("robot_report_generator")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gerador de relatório customizado para Robot Framework (BDD + BrowserLibrary)."
    )
    parser.add_argument(
        "--output-xml",
        help="Caminho para o output.xml do Robot; por padrão, procura dentro de --results-dir",
    )
    parser.add_argument(
        "--results-dir",
        help="Pasta de resultados que contém output.xml e os artefatos browser/screenshot",
    )
    parser.add_argument("--history", default="history.json", help="Caminho para o arquivo de histórico")
    parser.add_argument("--report", default="relatorio.html", help="Caminho do relatório HTML final")
    parser.add_argument(
        "--title",
        default="Relatório de Execução — Testes BDD",
        help="Título exibido no cabeçalho e na aba do relatório",
    )
    parser.add_argument(
        "--fail-on-error",
        action="store_true",
        help="Encerra com código 1 caso existam testes que falharam (ideal para CI/CD)",
    )
    parser.add_argument(
        "--no-history",
        action="store_true",
        help="Gera o relatório sem atualizar nem persistir o arquivo de histórico",
    )
    parser.add_argument(
        "--no-embed-artifacts",
        action="store_true",
        help="Não converte imagens em Base64, referenciando-as pelo caminho de arquivo",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    results_dir = Path(args.results_dir).expanduser().resolve() if args.results_dir else None
    if results_dir is not None and not results_dir.is_dir():
        logger.error("Pasta de resultados não encontrada: %s", results_dir)
        return 1

    output_xml = (
        Path(args.output_xml).expanduser().resolve()
        if args.output_xml
        else (results_dir / "output.xml" if results_dir else Path("output.xml").resolve())
    )
    if not output_xml.is_file():
        logger.error("Arquivo output.xml não encontrado: %s", output_xml)
        return 1
    artifact_dir = results_dir or output_xml.parent

    # 1. Extração (única fonte de dados: output.xml)
    xml_parser = RobotOutputParser(str(output_xml))
    try:
        suites, stats = xml_parser.parse()
    except (FileNotFoundError, ValueError) as exc:
        logger.error("Não foi possível gerar o relatório: %s", exc)
        return 1

    if xml_parser.errors:
        for err in xml_parser.errors:
            logger.warning("Aviso de parsing (não fatal): %s", err)

    # 2. Histórico (persistência local)
    history_manager = HistoryManager(args.history)
    if args.no_history:
        history = history_manager.load()
        version = "sem histórico"
    else:
        history = history_manager.append(
            stats,
            suites=suites,
            execution_start=xml_parser.execution_start,
        )
        version = history[-1].version if history else "sem versão"

    # 3. Apresentação (Jinja2 + Base64 -> HTML standalone)
    report_data = ReportData(
        title=args.title,
        stats=stats,
        suites=suites,
        history=history,
        generated_at=datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        errors=xml_parser.errors,
        version=version,
    )
    renderer = ReportRenderer(base_dir=artifact_dir, embed_artifacts=not args.no_embed_artifacts)
    out_path = renderer.render(report_data, args.report)

    logger.info(
        "Relatório gerado em: %s (Total=%d, Pass=%d, Fail=%d, Skip=%d, Taxa=%.1f%%)",
        out_path,
        stats.total,
        stats.passed,
        stats.failed,
        stats.skipped,
        stats.pass_rate,
    )
    return 1 if (args.fail_on_error and stats.failed > 0) else 0


if __name__ == "__main__":
    sys.exit(main())

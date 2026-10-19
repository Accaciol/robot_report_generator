"""Generate a standalone Robot Framework report from an output.xml file."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import logging
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from core.history_manager import HistoryManager
from core.import_service import ImportService, extract_archive
from core.pdf_summary import build_summary
from core.report_renderer import ReportRenderer
from core.sqlite_store import SQLiteStore, default_database_path
from core.xml_parser import RobotOutputParser
from models import ReportData

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("robot_report_generator")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gerador de relatório customizado para Robot Framework (BDD + BrowserLibrary)."
    )
    parser.add_argument("--database", type=Path, default=default_database_path(),
                        help="Banco SQLite de históricos e catálogo")
    parser.add_argument("--catalog-report", action="store_true",
                        help="Gera o relatório consolidado a partir do banco SQLite")
    parser.add_argument("--site-dir", help="Gera também um site estático do catálogo (requer --catalog-report)")
    parser.add_argument("--output-xml", help="Caminho explícito para output.xml")
    parser.add_argument("--results-dir", help="Pasta que contém output.xml e evidências")
    parser.add_argument("--zip", dest="input_zip", type=Path,
                        help="Arquivo ZIP com output.xml na raiz e evidências")
    parser.add_argument("--report", default="local-data/reports/relatorio.html",
                        help="Caminho do relatório HTML final")
    parser.add_argument("--summary-json", help=argparse.SUPPRESS)
    parser.add_argument("--system-id", default="robot-tests", help="Identificador do sistema no catálogo")
    parser.add_argument("--system-name", default="Robot Tests", help="Nome exibido do sistema")
    parser.add_argument("--system-version", default="não informada", help="Versão do produto testado")
    parser.add_argument("--execution-date", help="Data/hora ISO da execução; por padrão, usa o output.xml")
    parser.add_argument("--archive-zip", help=argparse.SUPPRESS)
    parser.add_argument("--title", default="Relatório de Execução — Testes BDD",
                        help="Título exibido no cabeçalho e na aba do relatório")
    parser.add_argument("--fail-on-error", action="store_true",
                        help="Encerra com código 1 se existirem testes com falha")
    parser.add_argument("--no-history", action="store_true",
                        help="Gera o relatório sem adicionar a execução ao SQLite")
    parser.add_argument("--no-report", action="store_true",
                        help="Importa a execução sem renderizar um arquivo HTML")
    parser.add_argument("--no-embed-artifacts", action="store_true",
                        help="Não converte imagens em Base64")
    parser.add_argument("--issue-url", default="",
                        help="Padrão de URL de tickets (ex.: https://jira/browse/{id})")
    parser.add_argument("--pdf", help="Gera relatório customizado em PDF no caminho especificado")
    parser.add_argument("--pdf-systems", help="Lista de IDs de sistemas separados por vírgula para o PDF")
    parser.add_argument("--pdf-sections", help="Seções a incluir no PDF separadas por vírgula (executive,distribution,suites,failures,history,slowest)")
    parser.add_argument("--pdf-title", help="Título exibido no relatório PDF")
    args = parser.parse_args()
    if args.catalog_report and (args.results_dir or args.input_zip or args.output_xml or args.archive_zip):
        parser.error("--catalog-report não aceita entradas de execução")
    if args.site_dir and not args.catalog_report:
        parser.error("--site-dir requer --catalog-report")
    if args.catalog_report and args.no_history:
        parser.error("--catalog-report não aceita --no-history")
    if args.no_report and args.no_history:
        parser.error("--no-report requer o armazenamento da execução no SQLite")
    if args.results_dir and args.input_zip:
        parser.error("Use --results-dir ou --zip, não ambos")
    if args.input_zip and args.output_xml:
        parser.error("--output-xml não pode ser combinado com --zip")
    return args


def _history_for_report(store: SQLiteStore, system_id: str) -> list:
    try:
        return store.history(system_id)
    except ValueError:
        return []


def _generate_cli_pdf(args: argparse.Namespace, store: SQLiteStore) -> int:
    from core.pdf_summary import collect_systems_data, render_custom_pdf
    pdf_path = Path(args.pdf).expanduser().resolve()
    system_ids = [s.strip() for s in args.pdf_systems.split(",") if s.strip()] if args.pdf_systems else None
    sections = [s.strip() for s in args.pdf_sections.split(",") if s.strip()] if args.pdf_sections else None
    title = args.pdf_title or args.title or "Relatório de Testes Automatizados"
    try:
        systems = collect_systems_data(store, system_ids)
        if not systems:
            logger.error("Nenhum sistema com histórico encontrado no banco para gerar o PDF.")
            return 1
        render_custom_pdf(systems, pdf_path, title=title, sections=sections)
        logger.info("Relatório PDF gerado em: %s", pdf_path)
        return 0
    except Exception as exc:
        logger.error("Erro ao gerar relatório em PDF: %s", exc)
        return 1


def _run(args: argparse.Namespace) -> int:
    database = Path(args.database).expanduser().resolve()
    store = SQLiteStore(database)

    # Prefer a fresh Robot Framework output at the conventional project root.
    default_input = Path("output.xml")
    if not default_input.is_file():
        default_input = Path("local-data/input/output.xml")
    has_input = bool(args.catalog_report or args.results_dir or args.output_xml or
                     (not args.pdf and default_input.is_file()))
    if args.pdf and not has_input:
        return _generate_cli_pdf(args, store)

    if args.catalog_report:
        from core.catalog_report import render_catalog, render_site
        try:
            failed = render_catalog(str(database), args.report, args.title, args.issue_url)
            if args.site_dir:
                failed = render_site(str(database), args.site_dir, args.title, args.issue_url) or failed
        except (OSError, ValueError, TypeError, RuntimeError) as exc:
            logger.error("Não foi possível gerar o catálogo: %s", exc)
            return 1
        logger.info("Relatório consolidado gerado em: %s", args.report)
        return 1 if args.fail_on_error and failed else 0

    results_dir = Path(args.results_dir).expanduser().resolve() if args.results_dir else None
    if results_dir is not None and not results_dir.is_dir():
        logger.error("Pasta de resultados não encontrada: %s", results_dir)
        return 1
    output_xml = (Path(args.output_xml).expanduser().resolve() if args.output_xml
                  else (results_dir / "output.xml" if results_dir else default_input.resolve()))
    if not output_xml.is_file():
        logger.error("Arquivo output.xml não encontrado: %s", output_xml)
        return 1
    artifact_dir = results_dir or output_xml.parent

    parser = RobotOutputParser(str(output_xml))
    try:
        suites, stats = parser.parse()
    except (FileNotFoundError, ValueError) as exc:
        logger.error("Não foi possível gerar o relatório: %s", exc)
        return 1
    for error in parser.errors:
        logger.warning("Aviso de parsing (não fatal): %s", error)

    digest = hashlib.sha256(output_xml.read_bytes()).hexdigest()
    history = _history_for_report(store, args.system_id)
    selected_version = "sem histórico"
    selected_history = history
    system_version = args.system_version
    execution_id = digest
    if not args.no_history:
        try:
            source = results_dir or output_xml.parent
            imported = ImportService(database).import_source(
                source, args.system_id, args.system_name, args.system_version,
                args.execution_date, archive_source=args.archive_zip,
                output_xml=output_xml if args.output_xml else None)
            execution_id = imported["execution_id"]
            history = imported["history"]
            index = next(i for i, entry in enumerate(history) if entry.execution_id == execution_id)
            selected_entry = history[index]
            selected_version = selected_entry.version
            system_version = selected_entry.system_version
            selected_history = history[:index + 1]
            if not imported["inserted"]:
                logger.info("Execução já cadastrada para o sistema %s; histórico preservado.", args.system_id)
        except (OSError, ValueError, RuntimeError) as exc:
            logger.error("Não foi possível armazenar a execução no SQLite: %s", exc)
            return 1

    if args.no_report:
        logger.info("Execução armazenada no SQLite sem gerar arquivo HTML.")
        return 1 if args.fail_on_error and stats.failed > 0 else 0

    report_data = ReportData(
        title=args.title, stats=stats, suites=suites, history=history,
        generated_at=datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        errors=parser.errors, version=selected_version, system_version=system_version,
        environment=parser.environment,
        flaky_tests=HistoryManager.detect_flaky_tests(selected_history),
        delta_stats=HistoryManager.compute_delta_stats(stats, selected_history),
        issue_url_pattern=args.issue_url,
        detailed_execution_id=execution_id if not args.no_history else None,
    )
    out_path = ReportRenderer(base_dir=artifact_dir,
                              embed_artifacts=not args.no_embed_artifacts).render(report_data, args.report)
    if args.summary_json:
        Path(args.summary_json).write_text(json.dumps(build_summary(report_data), ensure_ascii=False),
                                           encoding="utf-8")
    if args.pdf:
        _generate_cli_pdf(args, store)
    logger.info("Relatório gerado em: %s (Total=%d, Pass=%d, Fail=%d, Skip=%d, Taxa=%.1f%%)",
                out_path, stats.total, stats.passed, stats.failed, stats.skipped, stats.pass_rate)
    return 1 if args.fail_on_error and stats.failed > 0 else 0


def main() -> int:
    args = parse_args()
    if not args.input_zip:
        return _run(args)
    with tempfile.TemporaryDirectory(prefix="robot-report-cli-") as temporary:
        results_dir = Path(temporary) / "results"
        try:
            extract_archive(args.input_zip.expanduser().resolve(), results_dir)
        except (OSError, ValueError) as exc:
            logger.error("Não foi possível abrir o ZIP: %s", exc)
            return 1
        args.results_dir = str(results_dir)
        args.archive_zip = str(args.input_zip.expanduser().resolve())
        return _run(args)


if __name__ == "__main__":
    sys.exit(main())

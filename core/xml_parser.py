"""Extração de dados do output.xml do Robot Framework.

Responsabilidade única: transformar a árvore nativa do Robot
(robot.result.ExecutionResult) nas dataclasses definidas em models.py.
Nenhuma lógica de histórico ou de renderização deve entrar aqui.
"""
from __future__ import annotations

import logging
import re
from html import unescape
from pathlib import Path

from robot.api import ExecutionResult
from robot.result.visitor import ResultVisitor

from models import (
    Artifact,
    ExecutionStats,
    KeywordResult,
    Status,
    SuiteResult,
    TestResult,
)

logger = logging.getLogger(__name__)

# Prefixos usados para reconhecer passos Gherkin a partir do nome da keyword.
# Funciona tanto com robotframework-robotbdd quanto com o padrão nativo do
# Robot Framework (Given/When/Then/And/But no início do nome da keyword).
_GHERKIN_PREFIXES = ("given ", "when ", "then ", "and ", "but ")

# BrowserLibrary/SeleniumLibrary embutem evidências como HTML bruto nas
# mensagens de log (ex.: '*HTML* <img src="screenshot.png">').
_IMG_RE = re.compile(r'<img\b[^>]*?\bsrc\s*=\s*["\']([^"\']+)', re.IGNORECASE)
_VIDEO_RE = re.compile(r'<a\b[^>]*?\bhref\s*=\s*["\']([^"\']+\.(?:webm|mp4)(?:\?[^"\']*)?)', re.IGNORECASE)


def _status_from(value: str) -> Status:
    try:
        return Status(value)
    except ValueError:
        return Status.NOT_RUN


def _extract_gherkin_step(kw_name: str) -> str | None:
    lowered = kw_name.strip().lower()
    if lowered.startswith(_GHERKIN_PREFIXES):
        return kw_name.strip()
    return None


def _extract_artifacts(messages: list[str]) -> list[Artifact]:
    artifacts: list[Artifact] = []
    seen: set[tuple[str, str]] = set()
    for msg in messages:
        msg = unescape(msg)
        for m in _IMG_RE.finditer(msg):
            path = m.group(1)
            if ("image", path) not in seen:
                artifacts.append(Artifact(kind="image", original_path=path))
                seen.add(("image", path))
        for m in _VIDEO_RE.finditer(msg):
            path = m.group(1)
            if ("video", path) not in seen:
                artifacts.append(Artifact(kind="video", original_path=path))
                seen.add(("video", path))
    return artifacts


def _iter_keywords(suites: list[SuiteResult]):
    for suite in suites:
        for test in suite.tests:
            yield from _iter_keyword_nodes(test.keywords)
        yield from _iter_keywords(suite.suites)


def _iter_tests(suites: list[SuiteResult]):
    for suite in suites:
        yield from suite.tests
        yield from _iter_tests(suite.suites)


def _iter_keyword_nodes(keywords: list[KeywordResult]):
    for keyword in keywords:
        yield keyword
        yield from _iter_keyword_nodes(keyword.children)


class _CollectorVisitor(ResultVisitor):
    """Percorre a árvore de resultado do Robot e monta as dataclasses.

    Usa o padrão Visitor nativo do robot.result, o que evita reimplementar
    a navegação recursiva de suites/tests/keywords.
    """

    def __init__(self) -> None:
        self.root_suites: list[SuiteResult] = []
        self._suite_stack: list[SuiteResult] = []
        self._test_stack: list[TestResult] = []
        self._kw_stack: list[KeywordResult] = []
        self.parse_errors: list[str] = []
        self.execution_start = None

    # ---- Suites -------------------------------------------------------
    def start_suite(self, suite) -> None:  # noqa: ANN001 - tipo nativo do Robot
        if not self._suite_stack:
            self.execution_start = getattr(suite, "start_time", None) or getattr(suite, "starttime", None)
        node = SuiteResult(name=suite.name, doc=suite.doc or "", source=str(suite.source or ""))
        if self._suite_stack:
            self._suite_stack[-1].suites.append(node)
        else:
            self.root_suites.append(node)
        self._suite_stack.append(node)

    def end_suite(self, suite) -> None:  # noqa: ANN001
        self._suite_stack.pop()

    # ---- Tests ----------------------------------------------------------
    def start_test(self, test) -> None:  # noqa: ANN001
        node = TestResult(
            name=test.name,
            status=_status_from(str(getattr(test, "status", "NOT RUN"))),
            suite_name=self._suite_stack[-1].name if self._suite_stack else "",
            doc=test.doc or "",
            tags=list(test.tags),
            elapsed_s=self._safe_elapsed(test),
        )
        if not self._suite_stack:
            self.parse_errors.append(f"Teste '{test.name}' fora de qualquer suíte.")
            return
        self._suite_stack[-1].tests.append(node)
        self._test_stack.append(node)

    def end_test(self, test) -> None:  # noqa: ANN001
        if not self._test_stack:
            return
        node = self._test_stack.pop()
        node.message = getattr(test, "message", "") or ""
        node.gherkin_steps = [k.gherkin_step for k in node.keywords if k.gherkin_step]
        if node.is_failed:
            failed_kw = next(
                (k for k in node.keywords if k.status == Status.FAIL and k.gherkin_step),
                None,
            )
            if failed_kw:
                node.failed_step = failed_kw.gherkin_step
            elif node.gherkin_steps:
                node.failed_step = node.gherkin_steps[-1]
            else:
                failed_any = next((k for k in node.keywords if k.status == Status.FAIL), None)
                node.failed_step = failed_any.name if failed_any else None

    # ---- Keywords ---------------------------------------------------------
    def start_keyword(self, keyword) -> None:  # noqa: ANN001
        node = KeywordResult(
            name=getattr(keyword, "name", None) or getattr(keyword, "kwname", "") or "",
            status=_status_from(str(getattr(keyword, "status", "NOT RUN"))),
            doc=getattr(keyword, "doc", "") or "",
            args=[str(a) for a in getattr(keyword, "args", [])],
            elapsed_s=self._safe_elapsed(keyword),
        )
        node.gherkin_step = _extract_gherkin_step(node.name)
        if self._kw_stack:
            self._kw_stack[-1].children.append(node)
        elif self._test_stack:
            self._test_stack[-1].keywords.append(node)
        self._kw_stack.append(node)

    def end_keyword(self, keyword) -> None:  # noqa: ANN001
        if not self._kw_stack:
            return
        node = self._kw_stack.pop()
        node.artifacts = _extract_artifacts(node.messages)

    def visit_message(self, message) -> None:  # noqa: ANN001
        if self._kw_stack:
            try:
                message_text = getattr(message, "message", None) or getattr(message, "text", None) or ""
                if getattr(message, "html", False) and message_text:
                    message_text = unescape(message_text)
                self._kw_stack[-1].messages.append(str(message_text))
            except Exception:  # mensagem malformada não deve derrubar o parsing
                logger.debug("Mensagem de log ignorada por formato inesperado.")

    @staticmethod
    def _safe_elapsed(item) -> float:  # noqa: ANN001
        try:
            if hasattr(item, "elapsed_time") and item.elapsed_time is not None and hasattr(item.elapsed_time, "total_seconds"):
                return round(item.elapsed_time.total_seconds(), 4)
            return item.elapsedtime / 1000
        except Exception:
            return 0.0


class RobotOutputParser:
    """Fachada pública: output.xml -> (list[SuiteResult], ExecutionStats)."""

    def __init__(self, output_xml_path: str) -> None:
        self.output_xml_path = Path(output_xml_path)
        self.errors: list[str] = []
        self.execution_start = None
        self.environment: dict[str, str] = {}

    def parse(self) -> tuple[list[SuiteResult], ExecutionStats]:
        if not self.output_xml_path.exists():
            raise FileNotFoundError(f"output.xml não encontrado em: {self.output_xml_path}")

        try:
            result = ExecutionResult(str(self.output_xml_path))
        except Exception as exc:
            # Cobre XML corrompido, truncado (execução abortada) ou versão
            # de schema incompatível.
            logger.error("Falha ao carregar output.xml: %s", exc)
            raise ValueError(f"output.xml malformado ou incompatível: {exc}") from exc

        self.environment = {
            "generator": getattr(result, "generator", "") or "Robot Framework",
            "rpa": "Sim" if getattr(result, "rpa", False) else "Não",
        }

        visitor = _CollectorVisitor()
        try:
            result.visit(visitor)
        except Exception as exc:
            # Uma falha pontual (ex.: erro fatal de compilação em uma suíte)
            # não deve impedir o restante do relatório de ser gerado.
            logger.warning("Erro não fatal durante o parsing: %s", exc)
            visitor.parse_errors.append(str(exc))

        self.errors = visitor.parse_errors
        self.execution_start = (
            visitor.execution_start
            or getattr(result.suite, "start_time", None)
            or getattr(result.suite, "starttime", None)
        )

        try:
            total_stats = result.statistics.total
            stats = ExecutionStats(
                total=int(total_stats.total),
                passed=int(total_stats.passed),
                failed=int(total_stats.failed),
                skipped=int(getattr(total_stats, "skipped", 0)),
                elapsed_s=self._safe_suite_elapsed(result.suite),
                start_time=getattr(result.suite, "start_time", None) or getattr(result.suite, "starttime", None),
            )
        except Exception as exc:
            logger.warning("Não foi possível calcular estatísticas agregadas: %s", exc)
            self.errors.append(f"Estatísticas agregadas indisponíveis: {exc}")
            stats = self._stats_from_suites(visitor.root_suites)

        return visitor.root_suites, stats

    @staticmethod
    def _safe_suite_elapsed(suite) -> float:  # noqa: ANN001
        try:
            if hasattr(suite, "elapsed_time") and suite.elapsed_time is not None and hasattr(suite.elapsed_time, "total_seconds"):
                return round(suite.elapsed_time.total_seconds(), 4)
            return suite.elapsedtime / 1000
        except Exception:
            return 0.0

    @staticmethod
    def _stats_from_suites(suites: list[SuiteResult]) -> ExecutionStats:
        """Fallback: recalcula estatísticas manualmente a partir das dataclasses
        já coletadas, usado se a API de Statistics do Robot falhar."""
        all_tests = [t for s in suites for t in s.all_tests]
        return ExecutionStats(
            total=len(all_tests),
            passed=sum(1 for t in all_tests if t.status == Status.PASS),
            failed=sum(1 for t in all_tests if t.status == Status.FAIL),
            skipped=sum(1 for t in all_tests if t.status == Status.SKIP),
            elapsed_s=sum(t.elapsed_s for t in all_tests),
        )

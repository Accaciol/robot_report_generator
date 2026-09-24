"""Modelos de dados tipados para o gerador de relatórios.

Toda a informação extraída do output.xml passa por estas dataclasses antes de
chegar ao template Jinja2. Isso desacopla o parser do Robot Framework da
camada de apresentação (o template nunca acessa objetos nativos da API do
Robot diretamente).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Status(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    NOT_RUN = "NOT RUN"


@dataclass
class Artifact:
    """Evidência gerada pela BrowserLibrary (screenshot ou vídeo)."""

    kind: str  # "image" ou "video"
    original_path: str
    embedded_data_uri: str | None = None
    missing: bool = False
    artifact_id: str = ""


@dataclass
class KeywordResult:
    name: str
    status: Status
    doc: str = ""
    args: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)
    children: list["KeywordResult"] = field(default_factory=list)
    elapsed_s: float = 0.0
    gherkin_step: str | None = None  # preenchido se a keyword é um passo Given/When/Then


@dataclass
class TestResult:
    name: str
    status: Status
    suite_name: str = ""
    doc: str = ""
    tags: list[str] = field(default_factory=list)
    message: str = ""  # mensagem/stack trace de falha
    keywords: list[KeywordResult] = field(default_factory=list)
    elapsed_s: float = 0.0
    gherkin_steps: list[str] = field(default_factory=list)
    failed_step: str | None = None

    @property
    def is_failed(self) -> bool:
        return self.status == Status.FAIL

    @property
    def stable_id(self) -> str:
        return f"{self.suite_name}::{self.name}" if self.suite_name else self.name


@dataclass
class SuiteResult:
    """Representa uma suíte Robot, tipicamente uma Feature BDD."""

    name: str
    doc: str = ""
    tests: list[TestResult] = field(default_factory=list)
    suites: list["SuiteResult"] = field(default_factory=list)
    source: str = ""
    _cached_all_tests: list[TestResult] | None = field(default=None, init=False, repr=False)
    _cached_status_summary: dict[str, int] | None = field(default=None, init=False, repr=False)

    @property
    def all_tests(self) -> list[TestResult]:
        if self._cached_all_tests is None:
            tests = list(self.tests)
            for s in self.suites:
                tests.extend(s.all_tests)
            self._cached_all_tests = tests
        return self._cached_all_tests

    @property
    def status_summary(self) -> dict[str, int]:
        if self._cached_status_summary is None:
            summary = {"PASS": 0, "FAIL": 0, "SKIP": 0}
            for t in self.all_tests:
                summary[t.status.value] = summary.get(t.status.value, 0) + 1
            self._cached_status_summary = summary
        return self._cached_status_summary


@dataclass
class ExecutionStats:
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    elapsed_s: float = 0.0
    start_time: datetime | None = None

    @property
    def pass_rate(self) -> float:
        return round((self.passed / self.total) * 100, 2) if self.total else 0.0


@dataclass
class HistoryEntry:
    timestamp: str
    total: int
    passed: int
    failed: int
    skipped: int
    elapsed_s: float
    pass_rate: float
    version: str = "sem versão"
    tests: list[dict[str, object]] = field(default_factory=list)
    execution_id: str = ""


@dataclass
class ReportData:
    """Envelope final passado ao Jinja2."""

    stats: ExecutionStats
    suites: list[SuiteResult]
    history: list[HistoryEntry]
    generated_at: str
    errors: list[str] = field(default_factory=list)  # erros não fatais de parsing
    version: str = "sem versão"
    title: str = "Relatório de Execução — Testes BDD"
    environment: dict[str, str] = field(default_factory=dict)
    flaky_tests: list[dict[str, object]] = field(default_factory=list)
    issue_url_pattern: str = ""
    delta_stats: dict[str, object] = field(default_factory=dict)
    # None mantém a convenção legada: os detalhes pertencem à última execução.
    detailed_execution_id: str | None = None

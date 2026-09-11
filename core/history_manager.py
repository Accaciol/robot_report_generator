"""Persistência do histórico de execuções em history.json.

Responsabilidade única: ler, atualizar e gravar o histórico. Não conhece
nada sobre XML nem sobre o template HTML.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from models import ExecutionStats, HistoryEntry, SuiteResult

logger = logging.getLogger(__name__)


class HistoryManager:
    """Lê, atualiza e persiste a série histórica de execuções."""

    def __init__(self, history_path: str = "history.json", max_entries: int = 30) -> None:
        self.history_path = Path(history_path)
        self.max_entries = max_entries

    def load(self) -> list[HistoryEntry]:
        if not self.history_path.exists():
            return []
        try:
            raw = json.loads(self.history_path.read_text(encoding="utf-8"))
            return [HistoryEntry(**entry) for entry in raw]
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning(
                "history.json corrompido ou em formato inesperado (%s). "
                "Iniciando um novo histórico a partir desta execução.",
                exc,
            )
            return []

    def append(
        self,
        stats: ExecutionStats,
        suites: list[SuiteResult] | None = None,
        execution_start: str | None = None,
    ) -> list[HistoryEntry]:
        """Adiciona a execução atual ao histórico, persiste e retorna a série completa."""
        history = self.load()
        version = self._version_label(execution_start, history)
        tests = self._test_snapshots(suites or [])
        entry = HistoryEntry(
            timestamp=self._timestamp(execution_start),
            total=stats.total,
            passed=stats.passed,
            failed=stats.failed,
            skipped=stats.skipped,
            elapsed_s=round(stats.elapsed_s, 2),
            pass_rate=stats.pass_rate,
            version=version,
            tests=tests,
        )
        history.append(entry)
        history = history[-self.max_entries :]
        self._save(history)
        return history

    @staticmethod
    def _timestamp(value: str | datetime | None) -> str:
        if not value:
            return datetime.now().isoformat(timespec="seconds")
        if isinstance(value, datetime):
            return value.isoformat(timespec="seconds")
        value_str = str(value)
        for fmt in ("%Y%m%d %H:%M:%S.%f", "%Y%m%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(value_str, fmt).isoformat(timespec="seconds")
            except ValueError:
                continue
        return value_str

    @classmethod
    def _version_label(cls, execution_start: str | None, history: list[HistoryEntry]) -> str:
        timestamp = cls._timestamp(execution_start)
        day = timestamp[:10] if len(timestamp) >= 10 else "sem-data"
        same_day = sum(entry.version.startswith(day) for entry in history)
        return f"{day} #{same_day + 1}"

    @staticmethod
    def _test_snapshots(suites: list[SuiteResult]) -> list[dict[str, object]]:
        snapshots: list[dict[str, object]] = []

        def collect(suite: SuiteResult) -> None:
            for test in suite.tests:
                snapshots.append(
                    {
                        "stable_id": test.stable_id,
                        "suite_name": test.suite_name or suite.name,
                        "test_name": test.name,
                        "status": test.status.value,
                        "elapsed_s": round(test.elapsed_s, 2),
                        "artifacts": sum(
                            len(keyword.artifacts) for keyword in test.keywords
                        ),
                    }
                )
            for child in suite.suites:
                collect(child)

        for suite in suites:
            collect(suite)
        return snapshots

    def _save(self, history: list[HistoryEntry]) -> None:
        try:
            self.history_path.write_text(
                json.dumps([asdict(e) for e in history], indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            # Falha ao gravar histórico não deve impedir a geração do relatório atual.
            logger.error("Falha ao gravar %s: %s", self.history_path, exc)

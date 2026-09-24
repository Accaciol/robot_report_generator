"""Persistência do histórico de execuções em history.json.

Responsabilidade única: ler, atualizar e gravar o histórico. Não conhece
nada sobre XML nem sobre o template HTML.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
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

    def remove(self, index: int, timestamp: str, version: str) -> None:
        """Remove exatamente a entrada selecionada, preservando os demais dados."""
        if type(index) is not int or index < 0:
            raise ValueError("Selecione uma versão válida.")
        try:
            raw = json.loads(self.history_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("Não foi possível ler o arquivo de histórico.") from exc
        if not isinstance(raw, list) or index >= len(raw) or not isinstance(raw[index], dict):
            raise ValueError("A versão selecionada não existe no histórico.")
        if raw[index].get("timestamp") != timestamp or raw[index].get("version", "") != version:
            raise ValueError("O histórico mudou. Recarregue a lista antes de remover.")
        raw.pop(index)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.history_path.parent,
                                             prefix=f".{self.history_path.name}.", delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(raw, stream, indent=2, ensure_ascii=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.history_path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

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

    @staticmethod
    def detect_flaky_tests(history: list[HistoryEntry]) -> list[dict[str, object]]:
        """Identifica testes que alternaram entre PASS e FAIL ao longo do histórico."""
        if len(history) < 2:
            return []

        test_runs: dict[str, list[tuple[str, str, str]]] = {}
        for entry in history:
            for t in entry.tests:
                sid = str(t.get("stable_id", ""))
                st = str(t.get("status", ""))
                tname = str(t.get("test_name", sid))
                sname = str(t.get("suite_name", ""))
                if sid not in test_runs:
                    test_runs[sid] = []
                test_runs[sid].append((st, tname, sname))

        flaky = []
        for sid, runs in test_runs.items():
            if len(runs) < 2:
                continue
            flips = 0
            pass_count = 0
            fail_count = 0
            prev_status = None
            for st, _, _ in runs:
                if st == "PASS":
                    pass_count += 1
                elif st == "FAIL":
                    fail_count += 1
                if prev_status is not None and st in ("PASS", "FAIL") and prev_status in ("PASS", "FAIL") and st != prev_status:
                    flips += 1
                if st in ("PASS", "FAIL"):
                    prev_status = st

            if flips >= 1 and pass_count >= 1 and fail_count >= 1:
                total = len(runs)
                stability = round((1.0 - (flips / total)) * 100, 1)
                _, tname, sname = runs[-1]
                flaky.append({
                    "stable_id": sid,
                    "test_name": tname,
                    "suite_name": sname,
                    "flips": flips,
                    "total_runs": total,
                    "pass_count": pass_count,
                    "fail_count": fail_count,
                    "stability": max(0.0, stability),
                    "last_status": runs[-1][0],
                })

        flaky.sort(key=lambda x: (x["flips"], -float(x["stability"])), reverse=True)
        return flaky

    @staticmethod
    def compute_delta_stats(current_stats: ExecutionStats, history: list[HistoryEntry]) -> dict[str, object]:
        """Calcula a variação de métricas em relação à execução anterior."""
        if len(history) < 2:
            return {}
        prev = history[-2]
        pass_rate_delta = round(current_stats.pass_rate - prev.pass_rate, 2)
        elapsed_delta = round(current_stats.elapsed_s - prev.elapsed_s, 2)
        failed_delta = current_stats.failed - prev.failed

        return {
            "has_delta": True,
            "prev_version": prev.version,
            "pass_rate_delta": pass_rate_delta,
            "pass_rate_delta_str": f"+{pass_rate_delta}%" if pass_rate_delta > 0 else f"{pass_rate_delta}%",
            "elapsed_delta": elapsed_delta,
            "elapsed_delta_str": f"+{elapsed_delta:.1f}s" if elapsed_delta > 0 else f"{elapsed_delta:.1f}s",
            "failed_delta": failed_delta,
            "failed_delta_str": f"+{failed_delta}" if failed_delta > 0 else f"{failed_delta}",
        }

    def _save(self, history: list[HistoryEntry]) -> None:
        try:
            self.history_path.write_text(
                json.dumps([asdict(e) for e in history], indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            # Falha ao gravar histórico não deve impedir a geração do relatório atual.
            logger.error("Falha ao gravar %s: %s", self.history_path, exc)

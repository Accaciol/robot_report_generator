"""Aggregate comparable execution metrics across catalog systems."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

from models import HistoryEntry


PERIODS = {"30": 30, "90": 90, "365": 365, "all": None}
_COUNT_FIELDS = ("total", "passed", "failed", "skipped")


def _empty_metrics() -> dict[str, int]:
    """Create a fresh daily bucket; each date and system needs its own values."""
    return {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "executions": 0}


def _pass_rate(metrics: dict[str, int]) -> float:
    total = metrics["total"]
    return round(100 * metrics["passed"] / total, 1) if total else 0


def _execution_day(timestamp: str) -> date | None:
    """Parse the date portion while tolerating malformed legacy timestamps."""
    try:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).date()
    except (AttributeError, TypeError, ValueError):
        return None


def _daily_points(days: dict[str, dict[str, int]]) -> list[dict[str, Any]]:
    return [
        {"date": day, **metrics, "pass_rate": _pass_rate(metrics)}
        for day, metrics in sorted(days.items())
    ]


def overview(
    systems: Iterable[tuple[dict[str, Any], list[HistoryEntry], Any]],
    period: str = "30",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build summary metrics and daily approval trends for a selected period.

    The summary cards always use each system's latest execution. The trend only
    includes valid timestamps inside the selected period, so these two views may
    intentionally cover different date ranges.
    """
    if period not in PERIODS:
        raise ValueError("Período inválido.")

    system_entries = list(systems)
    today = (now or datetime.now(timezone.utc)).date()
    days_back = PERIODS[period]
    cutoff = today - timedelta(days=days_back - 1) if days_back else None
    applications = []
    daily: dict[str, dict[str, int]] = defaultdict(_empty_metrics)
    system_daily: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(_empty_metrics)
    )
    latest_totals = {field: 0 for field in _COUNT_FIELDS}

    for metadata, history, _ in system_entries:
        if not history:
            continue

        latest = history[-1]
        application = {
            "id": metadata["id"],
            "name": metadata["name"],
            "executions": len(history),
            "timestamp": latest.timestamp,
        }
        for field in _COUNT_FIELDS:
            application[field] = getattr(latest, field)
            latest_totals[field] += application[field]
        application["pass_rate"] = _pass_rate(application)
        applications.append(application)

        for entry in history:
            day = _execution_day(entry.timestamp)
            if day is None or (cutoff and (day < cutoff or day > today)):
                continue

            day_key = day.isoformat()
            aggregate_point = daily[day_key]
            system_point = system_daily[metadata["id"]][day_key]
            for field in _COUNT_FIELDS:
                count = getattr(entry, field)
                aggregate_point[field] += count
                system_point[field] += count
            aggregate_point["executions"] += 1
            system_point["executions"] += 1

    history_trend = []
    for metadata, _, _ in system_entries:
        points = system_daily.get(metadata["id"], {})
        if points:
            history_trend.append({
                "id": metadata["id"],
                "name": metadata["name"],
                "trend": _daily_points(points),
            })

    return {
        "period": period,
        "applications": applications,
        "latest": {**latest_totals, "pass_rate": _pass_rate(latest_totals)},
        "trend": _daily_points(daily),
        "history_trend": history_trend,
    }

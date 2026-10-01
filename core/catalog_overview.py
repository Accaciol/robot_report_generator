"""Métricas comparáveis entre sistemas do catálogo."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone


PERIODS = {"30": 30, "90": 90, "365": 365, "all": None}


def overview(systems, period: str = "30", now=None) -> dict:
    if period not in PERIODS:
        raise ValueError("Período inválido.")
    today = (now or datetime.now(timezone.utc)).date()
    cutoff = today - timedelta(days=PERIODS[period] - 1) if PERIODS[period] else None
    applications = []
    daily = defaultdict(lambda: {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "executions": 0})
    totals = {"total": 0, "passed": 0, "failed": 0, "skipped": 0}
    for metadata, history, _ in systems:
        latest = history[-1] if history else None
        item = {"id": metadata["id"], "name": metadata["name"],
                "executions": len(history), "timestamp": latest.timestamp if latest else None}
        for key in totals:
            item[key] = getattr(latest, key) if latest else 0
            totals[key] += item[key]
        item["pass_rate"] = round(100 * item["passed"] / item["total"], 1) if item["total"] else 0
        applications.append(item)
        for entry in history:
            day = datetime.fromisoformat(entry.timestamp.replace("Z", "+00:00")).date()
            if cutoff and (day < cutoff or day > today):
                continue
            point = daily[day.isoformat()]
            for key in totals:
                point[key] += getattr(entry, key)
            point["executions"] += 1
    trend = [{"date": day, **values,
              "pass_rate": round(100 * values["passed"] / values["total"], 1) if values["total"] else 0}
             for day, values in sorted(daily.items())]
    return {"period": period, "applications": applications, "latest": {
        **totals, "pass_rate": round(100 * totals["passed"] / totals["total"], 1) if totals["total"] else 0},
        "trend": trend}

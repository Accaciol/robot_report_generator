"""Generate consolidated HTML files or a static site from the SQLite catalog."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.catalog_overview import PERIODS, overview
from core.report_renderer import ReportRenderer
from core.sqlite_store import SQLiteStore


def _overview_by_period(entries: list, periods: dict[str, int | None]) -> dict[str, Any]:
    """Prepare shared metrics once for each supported reporting range."""
    return {period: overview(entries, period) for period in periods}


def render_catalog(
    database: str | Path,
    output_path: str | Path,
    title: str,
    issue_url: str = "",
) -> bool:
    """Render a single HTML catalog and return whether any system has failures."""
    catalog = SQLiteStore(database)
    entries = catalog.systems()
    systems = []
    has_failures = False

    for metadata, history, directory in entries:
        data = catalog.report_data(metadata, history, directory, title, issue_url)
        renderer = ReportRenderer(directory / "results")
        systems.append({
            "id": metadata["id"],
            "name": metadata["name"],
            "html": renderer.render_html(data) if history else None,
        })
        has_failures |= data.stats.failed > 0

    template_root = Path(__file__).resolve().parent.parent / "frontend" / "report_templates"
    renderer = ReportRenderer(template_root)
    html = renderer.env.get_template("catalog_template.html").render(
        title=title,
        systems=systems,
        site_mode=False,
        overviews=_overview_by_period(entries, PERIODS),
    )
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(html, encoding="utf-8")
    return has_failures


def render_site(
    database: str | Path,
    site_dir: str | Path,
    title: str,
    issue_url: str = "",
) -> bool:
    """Generate a static catalog suitable for local or cloud hosting."""
    catalog = SQLiteStore(database)
    entries = catalog.systems()
    destination = Path(site_dir).expanduser().resolve()
    database_path = Path(database).expanduser().resolve()

    # Avoid deleting or overwriting the live database through a site output path.
    paths_overlap = (
        destination == database_path
        or database_path in destination.parents
        or destination in database_path.parents
    )
    if paths_overlap:
        raise ValueError("A pasta do site não pode se sobrepor ao banco SQLite.")

    destination.mkdir(parents=True, exist_ok=True)
    reports_directory = destination / "systems"
    reports_directory.mkdir(exist_ok=True)
    systems = []
    has_failures = False

    for metadata, history, directory in entries:
        data = catalog.report_data(metadata, history, directory, title, issue_url)
        report_path = f"systems/{metadata['id']}.html" if history else None
        if report_path:
            content = ReportRenderer(directory / "results").render_html(data)
            (destination / report_path).write_text(content, encoding="utf-8")
        systems.append({"id": metadata["id"], "name": metadata["name"], "report": report_path})
        has_failures |= data.stats.failed > 0

    # Remove stale HTML left by systems that were deleted from the catalog.
    current_reports = {system["report"] for system in systems if system["report"]}
    for old_report in reports_directory.glob("*.html"):
        if f"systems/{old_report.name}" not in current_reports:
            old_report.unlink()

    renderer = ReportRenderer(Path(__file__).resolve().parent.parent / "frontend" / "report_templates")
    version = datetime.now(timezone.utc).isoformat()
    index_template = renderer.env.get_template("catalog_template.html")
    index_html = index_template.render(
        title=title,
        systems=systems,
        site_mode=True,
        version=version,
        overviews=_overview_by_period(entries, PERIODS),
    )
    (destination / "index.html").write_text(index_html, encoding="utf-8")
    (destination / "version.json").write_text(
        json.dumps({"version": version}, indent=2),
        encoding="utf-8",
    )
    (destination / "staticwebapp.config.json").write_text(
        json.dumps({
            "routes": [
                {"route": "/.auth/login/github", "statusCode": 404},
                {"route": "/*", "allowedRoles": ["reader"]},
            ],
            "responseOverrides": {
                "401": {"statusCode": 302, "redirect": "/.auth/login/aad"},
            },
            "globalHeaders": {
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        }, indent=2),
        encoding="utf-8",
    )
    return has_failures

"""Render consolidated HTML reports from the SQLite execution catalog."""
import json
from datetime import datetime, timezone
from pathlib import Path

from core.catalog_overview import PERIODS, overview
from core.report_renderer import ReportRenderer
from core.sqlite_store import SQLiteStore


def render_catalog(database: str | Path, output_path: str, title: str,
                   issue_url: str = "") -> bool:
    catalog = SQLiteStore(database)
    entries = catalog.systems()
    systems = []
    has_failures = False
    for metadata, history, directory in entries:
        data = catalog.report_data(metadata, history, directory, title, issue_url)
        renderer = ReportRenderer(directory / "results")
        systems.append({"id": metadata["id"], "name": metadata["name"],
                        "html": renderer.render_html(data) if history else None})
        has_failures = has_failures or data.stats.failed > 0
    renderer = ReportRenderer(Path(__file__).resolve().parent.parent / "robot-results")
    html = renderer.env.get_template("catalog_template.html").render(
        title=title, systems=systems, site_mode=False,
        overviews={period: overview(entries, period) for period in PERIODS})
    Path(output_path).write_text(html, encoding="utf-8")
    return has_failures


def render_site(database: str | Path, site_dir: str | Path, title: str,
                issue_url: str = "") -> bool:
    """Generate a static catalog for optional local deployment."""
    catalog = SQLiteStore(database)
    entries = catalog.systems()
    destination = Path(site_dir)
    database_path = Path(database).expanduser().resolve()
    resolved_destination = destination.expanduser().resolve()
    if (resolved_destination == database_path or database_path in resolved_destination.parents
            or resolved_destination in database_path.parents):
        raise ValueError("A pasta do site não pode se sobrepor ao banco SQLite.")
    destination.mkdir(parents=True, exist_ok=True)
    reports = destination / "systems"
    reports.mkdir(exist_ok=True)
    systems = []
    has_failures = False
    for metadata, history, directory in entries:
        data = catalog.report_data(metadata, history, directory, title, issue_url)
        report = f"systems/{metadata['id']}.html" if history else None
        if report:
            content = ReportRenderer(directory / "results").render_html(data)
            (destination / report).write_text(content, encoding="utf-8")
        systems.append({"id": metadata["id"], "name": metadata["name"], "report": report})
        has_failures = has_failures or data.stats.failed > 0
    current_reports = {system["report"] for system in systems if system["report"]}
    for old_report in reports.glob("*.html"):
        if f"systems/{old_report.name}" not in current_reports:
            old_report.unlink()
    renderer = ReportRenderer(Path(__file__).resolve().parent.parent / "robot-results")
    version = datetime.now(timezone.utc).isoformat()
    (destination / "index.html").write_text(renderer.env.get_template("catalog_template.html").render(
        title=title, systems=systems, site_mode=True, version=version,
        overviews={period: overview(entries, period) for period in PERIODS}), encoding="utf-8")
    (destination / "version.json").write_text(json.dumps({"version": version}), encoding="utf-8")
    (destination / "staticwebapp.config.json").write_text(json.dumps({
        "routes": [{"route": "/.auth/login/github", "statusCode": 404},
                   {"route": "/*", "allowedRoles": ["reader"]}],
        "responseOverrides": {"401": {"statusCode": 302, "redirect": "/.auth/login/aad"}},
        "globalHeaders": {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
    }, indent=2), encoding="utf-8")
    return has_failures

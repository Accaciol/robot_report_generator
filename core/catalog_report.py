"""Gera um HTML consolidado sem alterar o catálogo."""
import json
from datetime import datetime, timezone
from pathlib import Path

from core.catalog import Catalog
from core.catalog_overview import PERIODS, overview
from core.report_renderer import ReportRenderer


def render_catalog(catalog_dir: str, output_path: str, title: str,
                   issue_url: str = "") -> bool:
    catalog = Catalog(catalog_dir)
    catalog_systems = catalog.systems()
    systems = []
    has_failures = False
    for metadata, history, directory in catalog_systems:
        data = catalog.report_data(metadata, history, directory, title, issue_url)
        renderer = ReportRenderer(directory / "current")
        systems.append({"id": metadata["id"], "name": metadata["name"],
                        "html": renderer.render_html(data) if history else None})
        has_failures = has_failures or data.stats.failed > 0
    renderer = ReportRenderer(Path(catalog_dir))
    html = renderer.env.get_template("catalog_template.html").render(
        title=title, systems=systems, site_mode=False,
        overviews={period: overview(catalog_systems, period) for period in PERIODS})
    Path(output_path).write_text(html, encoding="utf-8")
    return has_failures


def render_site(catalog_dir: str, site_dir: str | Path, title: str,
                issue_url: str = "") -> bool:
    """Gera um diretório estático pronto para Azure Static Web Apps."""
    catalog = Catalog(catalog_dir)
    catalog_systems = catalog.systems()
    destination = Path(site_dir)
    catalog_root = Path(catalog_dir).expanduser().resolve()
    resolved_destination = destination.expanduser().resolve()
    if (resolved_destination == catalog_root or catalog_root in resolved_destination.parents
            or resolved_destination in catalog_root.parents):
        raise ValueError("A pasta do site não pode se sobrepor ao catálogo.")
    destination.mkdir(parents=True, exist_ok=True)
    reports = destination / "systems"
    reports.mkdir(exist_ok=True)
    systems = []
    has_failures = False
    for metadata, history, directory in catalog_systems:
        data = catalog.report_data(metadata, history, directory, title, issue_url)
        report = f"systems/{metadata['id']}.html" if history else None
        if report:
            (destination / report).write_text(ReportRenderer(directory / "current").render_html(data), encoding="utf-8")
        systems.append({"id": metadata["id"], "name": metadata["name"], "report": report})
        has_failures = has_failures or data.stats.failed > 0
    current_reports = {system["report"] for system in systems if system["report"]}
    for old_report in reports.glob("*.html"):
        if f"systems/{old_report.name}" not in current_reports:
            old_report.unlink()
    renderer = ReportRenderer(Path(catalog_dir))
    version = datetime.now(timezone.utc).isoformat()
    (destination / "index.html").write_text(renderer.env.get_template("catalog_template.html").render(
        title=title, systems=systems, site_mode=True, version=version,
        overviews={period: overview(catalog_systems, period) for period in PERIODS}), encoding="utf-8")
    (destination / "version.json").write_text(json.dumps({"version": version}), encoding="utf-8")
    (destination / "staticwebapp.config.json").write_text(json.dumps({
        "routes": [{"route": "/.auth/login/github", "statusCode": 404},
                   {"route": "/*", "allowedRoles": ["reader"]}],
        "responseOverrides": {"401": {"statusCode": 302, "redirect": "/.auth/login/aad"}},
        "globalHeaders": {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
    }, indent=2), encoding="utf-8")
    return has_failures

"""Gera um HTML consolidado sem alterar o catálogo."""
from pathlib import Path

from core.catalog import Catalog
from core.report_renderer import ReportRenderer


def render_catalog(catalog_dir: str, output_path: str, title: str,
                   issue_url: str = "") -> bool:
    catalog = Catalog(catalog_dir)
    systems = []
    has_failures = False
    for metadata, history, directory in catalog.systems():
        data = catalog.report_data(metadata, history, directory, title, issue_url)
        renderer = ReportRenderer(directory / "current")
        systems.append({"id": metadata["id"], "name": metadata["name"],
                        "html": renderer.render_html(data) if history else None})
        has_failures = has_failures or data.stats.failed > 0
    renderer = ReportRenderer(Path(catalog_dir))
    html = renderer.env.get_template("catalog_template.html").render(title=title, systems=systems)
    Path(output_path).write_text(html, encoding="utf-8")
    return has_failures

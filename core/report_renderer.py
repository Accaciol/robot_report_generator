"""Renderização do relatório HTML standalone via Jinja2.

Responsabilidade única: pegar ReportData (já pronto) e produzir um único
arquivo .html com CSS, JS e imagens embutidos em Base64. Não conhece nada
sobre como os dados foram extraídos do Robot Framework.
"""
from __future__ import annotations

import base64
import logging
import mimetypes
from dataclasses import asdict
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from models import KeywordResult, ReportData, SuiteResult

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_TEMPLATE_DIR = _PROJECT_ROOT / "templates"
# Vendorize o Chart.js aqui (baixe o build UMD minificado) para manter o
# relatório 100% offline/standalone. Caso o arquivo não exista, o relatório
# ainda é gerado, mas o gráfico de tendência fica indisponível.
_CHART_JS_VENDOR = _PROJECT_ROOT / "assets" / "chart.umd.min.js"
# Usado apenas como fallback quando o Chart.js não foi vendorizado localmente.
# Nesse modo o relatório deixa de ser 100% offline (precisa de internet no
# navegador que abrir o HTML), mas funciona sem nenhum passo manual.
_CHART_JS_CDN_URL = "https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"
_MAX_EMBEDDED_VIDEO_BYTES = 8 * 1024 * 1024


class ReportRenderer:
    """Converte ReportData em um arquivo HTML único e autocontido."""

    def __init__(
        self,
        base_dir: Path,
        template_name: str = "report_template.html",
        embed_artifacts: bool = True,
    ) -> None:
        self.base_dir = base_dir.expanduser().resolve()
        self.embed_artifacts = embed_artifacts
        self._b64_cache: dict[str, str] = {}
        self.env = Environment(
            loader=FileSystemLoader(str(_TEMPLATE_DIR)),
            autoescape=select_autoescape(["html"]),
        )
        self.template_name = template_name

    # ---- Embutir evidências em Base64 ----------------------------------
    def _embed_artifacts(self, suites: list[SuiteResult]) -> None:
        for suite in suites:
            for test in suite.tests:
                for kw in test.keywords:
                    self._embed_keyword_artifacts(kw)
            self._embed_artifacts(suite.suites)

    def _embed_keyword_artifacts(self, kw: KeywordResult) -> None:
        for artifact in kw.artifacts:
            if artifact.original_path.startswith(("http://", "https://", "data:")):
                continue
            file_path = (self.base_dir / artifact.original_path).resolve()
            if not file_path.exists():
                logger.debug("Artefato de imagem não encontrado: %s", file_path)
                artifact.missing = True
                continue

            if not self.embed_artifacts:
                artifact.embedded_data_uri = artifact.original_path
                continue

            path_key = str(file_path)
            if path_key in self._b64_cache:
                artifact.embedded_data_uri = self._b64_cache[path_key]
                continue

            try:
                if artifact.kind == "video" and file_path.stat().st_size > _MAX_EMBEDDED_VIDEO_BYTES:
                    logger.warning("Vídeo maior que 8 MB não foi embutido: %s", file_path)
                    artifact.missing = True
                    continue
                data = file_path.read_bytes()
                mime, _ = mimetypes.guess_type(str(file_path))
                mime = mime or ("video/mp4" if artifact.kind == "video" else "image/png")
                data_uri = f"data:{mime};base64,{base64.b64encode(data).decode()}"
                self._b64_cache[path_key] = data_uri
                artifact.embedded_data_uri = data_uri
            except OSError as exc:
                logger.warning("Não foi possível embutir artefato %s: %s", file_path, exc)
                artifact.missing = True
        for child in kw.children:
            self._embed_keyword_artifacts(child)

    def _load_chart_js(self) -> tuple[str, str]:
        """Retorna (modo, conteúdo).

        modo == "inline": conteúdo é o JS completo do Chart.js (vendorizado),
        embutido no <script> do relatório — 100% offline.
        modo == "cdn": conteúdo é a URL do Chart.js; o relatório carrega via
        <script src="...">, exigindo internet no navegador que abrir o HTML.
        """
        if _CHART_JS_VENDOR.exists():
            return "inline", _CHART_JS_VENDOR.read_text(encoding="utf-8")
        logger.info(
            "assets/chart.umd.min.js não encontrado — usando Chart.js via CDN (%s). "
            "Vendorize o arquivo nesse caminho se precisar de um relatório 100%% offline.",
            _CHART_JS_CDN_URL,
        )
        return "cdn", _CHART_JS_CDN_URL

    # ---- API pública --------------------------------------------------
    def render(self, data: ReportData, output_path: str) -> Path:
        self._embed_artifacts(data.suites)
        chart_js_mode, chart_js_content = self._load_chart_js()
        template = self.env.get_template(self.template_name)
        html = template.render(
            title=data.title,
            stats=data.stats,
            suites=data.suites,
            history=[asdict(h) for h in data.history],  # dataclass -> dict p/ o filtro |tojson
            version=data.version,
            generated_at=data.generated_at,
            errors=data.errors,
            environment=data.environment,
            flaky_tests=data.flaky_tests,
            delta_stats=data.delta_stats,
            issue_url_pattern=data.issue_url_pattern,
            chart_js_mode=chart_js_mode,
            chart_js_content=chart_js_content,
        )
        out_path = Path(output_path)
        out_path.write_text(html, encoding="utf-8")
        return out_path

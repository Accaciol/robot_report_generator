"""Publicação opcional do catálogo no Azure Static Web Apps."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from core.catalog_report import render_site


def publish_if_configured(catalog_dir: str | Path, title: str = "Relatório de Execução — Testes BDD") -> bool:
    """Retorna False quando não há token; erros de publicação são propagados."""
    token = os.environ.get("ROBOT_REPORT_SWA_TOKEN")
    if not token:
        return False
    executable = shutil.which("swa")
    if not executable:
        raise RuntimeError("Azure Static Web Apps CLI (swa) não encontrado.")
    with tempfile.TemporaryDirectory(prefix="robot-report-site-") as temporary:
        site = Path(temporary)
        render_site(str(catalog_dir), site, title)
        environment = {**os.environ, "SWA_CLI_DEPLOYMENT_TOKEN": token}
        environment.pop("ROBOT_REPORT_SWA_TOKEN", None)
        try:
            result = subprocess.run([executable, "deploy", str(site), "--env", "production"],
                                    env=environment, capture_output=True, text=True, timeout=180)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Publicação no Azure excedeu 180 segundos.") from exc
        if result.returncode:
            # A CLI pode incluir detalhes sensíveis; só exponha o código de saída.
            raise RuntimeError(f"Publicação no Azure falhou (código {result.returncode}).")
    return True

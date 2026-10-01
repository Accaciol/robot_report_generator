import json
from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.azure_publish import publish_if_configured
from core.catalog import Catalog
from core.catalog_overview import overview
from core.catalog_report import render_site
from tests.test_catalog import make_results


class TestMultiApp(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.catalog = Catalog(self.root / "catalog")

    def test_overview_uses_latest_per_app_and_filters_trend(self):
        self.catalog.import_results(make_results(self.root, 10, marker="alpha-old"), "alpha", "Alpha")
        self.catalog.import_results(make_results(self.root, 12, failed=False, marker="alpha-new"), "alpha")
        self.catalog.import_results(make_results(self.root, 11, marker="beta"), "beta", "Beta")
        systems = self.catalog.systems()
        data = overview(systems, "all")
        self.assertEqual(len(data["applications"]), 2)
        self.assertEqual(data["latest"]["total"], 4)
        self.assertEqual(data["latest"]["failed"], 1)
        self.assertEqual(data["latest"]["pass_rate"], 75)
        self.assertEqual(len(data["trend"]), 3)
        self.assertEqual(overview(systems, "30", now=datetime(2026, 11, 1, tzinfo=timezone.utc))["trend"], [])
        with self.assertRaises(ValueError):
            overview(systems, "invalid")

    def test_site_has_separate_reports_and_private_configuration(self):
        self.catalog.import_results(make_results(self.root, 10, marker="alpha"), "alpha", "Alpha")
        self.catalog.import_results(make_results(self.root, 11, marker="beta"), "beta", "Beta")
        site = self.root / "site"
        render_site(self.catalog.root, site, "Testes")
        index = (site / "index.html").read_text()
        self.assertIn("Visão geral", index)
        self.assertIn("systems/alpha.html", index)
        self.assertNotIn("Navegando até /login alpha", index)
        self.assertIn("Navegando até /login alpha", (site / "systems/alpha.html").read_text())
        self.assertTrue((site / "version.json").is_file())
        self.assertIn(json.loads((site / "version.json").read_text())["version"], index)
        config = json.loads((site / "staticwebapp.config.json").read_text())
        self.assertEqual(config["routes"][-1]["allowedRoles"], ["reader"])
        self.assertNotIn("authenticated", json.dumps(config))
        first = (site / "systems/beta.html").read_bytes()
        self.catalog.remove("beta", self.catalog.load("beta")[1][0].execution_id)
        render_site(self.catalog.root, site, "Testes")
        self.assertFalse((site / "systems/beta.html").exists())
        self.assertTrue(first)

    def test_publisher_uses_environment_without_token_in_command(self):
        self.catalog.import_results(make_results(self.root, 10), "alpha")
        with patch.dict(os.environ, {"ROBOT_REPORT_SWA_TOKEN": "secret-value"}), \
                patch("core.azure_publish.shutil.which", return_value="/usr/bin/swa"), \
                patch("core.azure_publish.subprocess.run") as run:
            run.return_value.returncode = 0
            self.assertTrue(publish_if_configured(self.catalog.root))
            args, kwargs = run.call_args
            self.assertNotIn("secret-value", str(args))
            self.assertEqual(kwargs["env"]["SWA_CLI_DEPLOYMENT_TOKEN"], "secret-value")
            self.assertNotIn("ROBOT_REPORT_SWA_TOKEN", kwargs["env"])
            run.return_value.returncode = 2
            with self.assertRaisesRegex(RuntimeError, "código 2"):
                publish_if_configured(self.catalog.root)

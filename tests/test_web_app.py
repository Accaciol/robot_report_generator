import tempfile
import threading
import unittest
from pathlib import Path

from core.import_service import ImportService
from core.sqlite_store import SQLiteStore
from core.web_app import create_app


ROOT = Path(__file__).resolve().parent.parent
ORIGIN = "http://127.0.0.1:5000"


class TestWebApp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.database = self.base / "history.sqlite3"
        self.app = create_app({"TESTING": True, "DATABASE": self.database})
        self.app.config["LOCAL_ORIGIN"] = ORIGIN
        self.client = self.app.test_client()
        self.jobs = self.app.extensions["jobs"]
        self.imports = self.app.extensions["imports"]
        self.headers = {
            "X-Session-Token": self.app.config["SESSION_TOKEN"],
            "Origin": ORIGIN,
        }
        self.addCleanup(self.jobs.close)
        self.addCleanup(self.imports.close)

    def get(self, path, *, headers=None, base_url=ORIGIN, **kwargs):
        return self.client.get(path, base_url=base_url, headers=headers or self.headers, **kwargs)

    def post(self, path, data=None, *, headers=None, base_url=ORIGIN, **kwargs):
        return self.client.post(
            path, base_url=base_url, headers=headers or self.headers, json=data, **kwargs
        )

    def seed(self, system_id="portal", name="Portal", marker=""):
        source = self.base / f"results-{system_id}-{marker or 'base'}"
        source.mkdir()
        xml = (ROOT / "example/output.xml").read_text(encoding="utf-8")
        if marker:
            xml = xml.replace("Robot Framework", f"Robot Framework {marker}")
        (source / "output.xml").write_text(xml, encoding="utf-8")
        return ImportService(self.database).import_source(source, system_id, name, "2.4")

    def test_home_assets_and_session_endpoint(self):
        page = self.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Robot Reports", page.text)
        self.assertNotIn(self.app.config["SESSION_TOKEN"], page.text)
        for resource in ("/static/app.js", "/static/app.css"):
            response = self.get(resource)
            self.assertEqual(response.status_code, 200)
            response.close()

        response = self.post("/api/session", {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["database"], str(self.database))

    def test_admin_endpoints_require_local_session_but_public_catalog_is_readable(self):
        self.assertEqual(
            self.client.get("/api/systems", base_url=ORIGIN).status_code, 403
        )
        wrong_origin = {**self.headers, "Origin": "http://evil.test"}
        self.assertEqual(self.get("/api/systems", headers=wrong_origin).status_code, 403)
        cross_site = {**self.headers, "Sec-Fetch-Site": "cross-site"}
        self.assertEqual(self.get("/api/state", headers=cross_site).status_code, 403)
        self.assertEqual(self.get("/public").status_code, 200)
        self.assertEqual(
            self.client.get("/public/api/systems", base_url="http://external.test").status_code,
            200,
        )

    def test_public_catalog_and_report_are_built_from_sqlite(self):
        self.seed()
        systems = self.client.get("/public/api/systems", base_url=ORIGIN)
        self.assertEqual(systems.status_code, 200)
        self.assertEqual(systems.json["systems"][0]["id"], "portal")
        overview = self.client.get(
            "/public/api/overview?period=all", base_url=ORIGIN
        )
        self.assertEqual(overview.json["latest"]["total"], 2)
        self.assertEqual(
            self.client.get("/public/api/overview?period=invalid", base_url=ORIGIN).status_code,
            400,
        )
        report = self.client.get("/public/reports/portal", base_url=ORIGIN)
        self.assertEqual(report.status_code, 200)
        self.assertIn("Login com credenciais inválidas", report.text)
        self.assertIn("no-store", report.headers["Cache-Control"])
        self.assertEqual(
            self.client.get("/public/reports/missing", base_url=ORIGIN).status_code, 404
        )

    def test_admin_history_can_remove_execution(self):
        result = self.seed()
        response = self.get("/api/history", query_string={"system_id": "portal"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["entries"][0]["execution_id"], result["execution_id"])
        removed = self.post("/api/history/remove", {
            "system_id": "portal", "execution_id": result["execution_id"]
        })
        self.assertEqual(removed.status_code, 200)
        self.assertEqual(SQLiteStore(self.database).history("portal"), [])
        invalid = self.post("/api/history/remove", {
            "system_id": "portal", "execution_id": "unknown"
        })
        self.assertEqual(invalid.status_code, 400)

    def test_artifact_orphan_scan_and_cleanup(self):
        store = SQLiteStore(self.database)
        orphan = store.artifacts_root / "unused" / "orphaned-run"
        orphan.mkdir(parents=True)
        (orphan / "evidence.png").write_bytes(b"evidence")
        scan = self.get("/api/artifacts/orphans")
        self.assertEqual(scan.status_code, 200)
        self.assertEqual(scan.json["count"], 1)
        cleanup = self.post("/api/artifacts/cleanup", {})
        self.assertEqual(cleanup.status_code, 200)
        self.assertFalse(orphan.exists())

    def test_shutdown_signals_server_and_closes_services(self):
        stopped = threading.Event()
        self.app.config["STOP_SERVER"] = stopped.set
        response = self.post("/api/shutdown", {})
        self.assertEqual(response.status_code, 202)
        self.assertTrue(stopped.wait(3))
        self.assertTrue(self.jobs.closing)


if __name__ == "__main__":
    unittest.main()

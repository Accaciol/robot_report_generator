import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from core.web_app import create_app

ROOT = Path(__file__).resolve().parent.parent
ORIGIN = "http://127.0.0.1:5000"


class TestWebImports(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.destination = self.base / "reports"
        self.destination.mkdir()
        self.app = create_app({"TESTING": True, "DATABASE": self.base / "history.sqlite3"})
        self.client = self.app.test_client()
        self.jobs = self.app.extensions["jobs"]
        self.imports = self.app.extensions["imports"]
        self.headers = {"X-Session-Token": self.app.config["SESSION_TOKEN"], "Origin": ORIGIN}
        self.app.config["INGEST_TOKEN"] = "automation-secret"

    def tearDown(self):
        self.jobs.close()
        self.imports.close()
        self.tmp.cleanup()

    def post(self, path, data=None, **kwargs):
        return self.client.post(path, base_url=ORIGIN, headers=self.headers, json=data, **kwargs)

    def test_zip_preview_and_import_use_sqlite(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as bundle:
            bundle.writestr("output.xml", (ROOT / "example/output.xml").read_bytes())
        stream.seek(0)
        response = self.client.post("/api/imports/preview", base_url=ORIGIN,
                                    headers=self.headers,
                                    data={"file": (stream, "results.zip")},
                                    content_type="multipart/form-data")
        self.assertEqual(response.status_code, 200, response.json)
        preview = response.json
        self.assertEqual(preview["total"], 2)
        started = self.post("/api/imports", {"upload_id": preview["upload_id"],
            "system_id": "portal", "system_name": "Portal", "system_version": "2.0",
            "execution_date": "2025-01-01T10:00", "destination": str(self.destination)})
        self.assertEqual(started.status_code, 202, started.json)
        self.jobs.worker.join(timeout=20)
        self.assertFalse(self.jobs.worker.is_alive())
        self.assertEqual(self.jobs.snapshot()["items"][0]["status"], "completed")
        systems = self.client.get("/api/systems", base_url=ORIGIN, headers=self.headers)
        self.assertEqual(systems.json["systems"][0]["id"], "portal")
        self.assertTrue((self.base / "history.sqlite3").is_file())

    def test_invalid_zip_is_rejected(self):
        response = self.client.post("/api/imports/preview", base_url=ORIGIN,
                                    headers=self.headers,
                                    data={"file": (io.BytesIO(b"not zip"), "broken.zip")},
                                    content_type="multipart/form-data")
        self.assertEqual(response.status_code, 400)
        self.assertIn("ZIP", response.json["error"])

    def automation_post(self, data):
        return self.client.post("/api/automation/imports", base_url="http://pipeline.example",
                                headers={"Authorization": "Bearer automation-secret"},
                                data=data, content_type="multipart/form-data")

    def test_automation_auth_validation_import_and_status(self):
        unauthenticated = self.client.post("/api/automation/imports", base_url="http://pipeline.example")
        self.assertEqual(unauthenticated.status_code, 403)
        bad = self.automation_post({"file": (io.BytesIO(b"broken"), "results.zip"),
                                    "system_id": "portal", "system_name": "Portal",
                                    "system_version": "1"})
        self.assertEqual(bad.status_code, 400)
        invalid_metadata = self.automation_post({"file": (io.BytesIO(b"zip"), "results.zip"),
                                                 "system_id": "../bad", "system_name": "Portal",
                                                 "system_version": "1"})
        self.assertEqual(invalid_metadata.status_code, 400)

        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as bundle:
            bundle.writestr("output.xml", (ROOT / "example/output.xml").read_bytes())
        stream.seek(0)
        response = self.automation_post({"file": (stream, "results.zip"), "system_id": "portal",
                                         "system_name": "Portal", "system_version": "${Build.BuildNumber}"})
        self.assertEqual(response.status_code, 202, response.json)
        run_id = response.json["import_id"]
        self.jobs.worker.join(timeout=20)
        status = self.client.get(f"/api/automation/imports/{run_id}", base_url="http://pipeline.example",
                                 headers={"Authorization": "Bearer automation-secret"})
        self.assertEqual(status.json["items"][0]["status"], "completed", status.json)
        systems = self.client.get("/public/api/systems", base_url="http://pipeline.example")
        self.assertEqual(systems.json["systems"][0]["id"], "portal")
        self.assertEqual(len(self.app.extensions["imports"].store.systems()[0][1]), 1)
        # Re-importing byte-identical XML is recorded as a successful no-op.
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as bundle:
            bundle.writestr("output.xml", (ROOT / "example/output.xml").read_bytes())
        stream.seek(0)
        response = self.automation_post({"file": (stream, "results.zip"), "system_id": "portal",
                                         "system_name": "Portal", "system_version": "2"})
        self.assertEqual(response.status_code, 202)
        self.jobs.worker.join(timeout=20)
        self.assertEqual(len(self.app.extensions["imports"].store.systems()[0][1]), 1)

    def test_automation_keeps_administrative_routes_on_session_token(self):
        response = self.client.get("/api/state", base_url="http://pipeline.example",
                                   headers={"Authorization": "Bearer automation-secret"})
        self.assertEqual(response.status_code, 403)

    def test_automation_rejects_wrong_token_and_oversized_zip(self):
        response = self.client.get("/api/automation/imports/not-real", base_url="http://pipeline.example",
                                   headers={"Authorization": "Bearer wrong-token"})
        self.assertEqual(response.status_code, 403)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as bundle:
            bundle.writestr("output.xml", (ROOT / "example/output.xml").read_bytes())
        stream.seek(0)
        with patch.dict("os.environ", {"ROBOT_REPORT_MAX_UPLOAD_BYTES": "1"}):
            response = self.automation_post({"file": (stream, "results.zip"), "system_id": "portal",
                                             "system_name": "Portal", "system_version": "1"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("limite", response.json["error"])

    def test_automation_status_propagates_processing_failure(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as bundle:
            bundle.writestr("output.xml", (ROOT / "example/output.xml").read_bytes())
        stream.seek(0)
        with patch("core.web_jobs.subprocess.Popen", side_effect=OSError("worker indisponível")):
            response = self.automation_post({"file": (stream, "results.zip"), "system_id": "portal",
                                             "system_name": "Portal", "system_version": "1"})
            self.assertEqual(response.status_code, 202)
            run_id = response.json["import_id"]
            self.jobs.worker.join(timeout=20)
        status = self.client.get(f"/api/automation/imports/{run_id}", base_url="http://pipeline.example",
                                 headers={"Authorization": "Bearer automation-secret"})
        self.assertEqual(status.json["items"][0]["status"], "failed")
        self.assertIn("worker indisponível", status.json["items"][0]["error"])

import io
import tempfile
import unittest
import zipfile
from pathlib import Path

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

"""Hosted transport retains the same API contracts and an isolated durable library."""
import base64
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from backend.server import DashboardService
from backend.web import AccessPolicy, create_app

ORIGIN = "https://vigil.example"
AUTH = "Basic " + base64.b64encode(b"researcher:test-only-password-twenty-characters").decode()
SETTINGS = {"VIGIL_PUBLIC_ORIGIN": ORIGIN, "VIGIL_AUTH_USER": "researcher",
            "VIGIL_AUTH_PASSWORD": "test-only-password-twenty-characters"}
COHORT = {"mode": "reference", "drug": "METFORMIN", "compare": "", "start": "2025-01-01",
          "end": "2025-01-31", "age": "All", "sex": "", "reporters": ""}


class HostedTransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service = DashboardService(storage_root=self.temp.name)
        self.app = create_app(SETTINGS, self.service)
        self.client = self.app.test_client()
        self.headers = {"Authorization": AUTH, "Origin": ORIGIN}

    def request(self, method, path, **kwargs):
        headers = kwargs.pop("headers", self.headers)
        return self.client.open(path, method=method, base_url=ORIGIN, headers=headers, **kwargs)

    def test_startup_requires_explicit_https_and_owner_credentials(self):
        for settings in [{"VIGIL_PUBLIC_ORIGIN": ORIGIN}, {**SETTINGS, "VIGIL_AUTH_PASSWORD": "short"},
                         {**SETTINGS, "VIGIL_PUBLIC_ORIGIN": "http://vigil.example"},
                         {**SETTINGS, "VIGIL_PUBLIC_ORIGIN": "https://vigil.example/path"}]:
            with self.subTest(settings=list(settings)):
                with self.assertRaises(ValueError):
                    create_app(settings, self.service)
        app = create_app({**SETTINGS, "VIGIL_PUBLIC_ORIGIN": "", "RENDER_EXTERNAL_URL": ORIGIN}, self.service)
        self.assertEqual(app.test_client().get("/healthz", base_url=ORIGIN).status_code, 200)

    def test_unauthenticated_requests_cannot_read_or_mutate_the_workspace(self):
        for path in ["/", "/api/investigations", "/api/health", "/api/model/train"]:
            response = self.request("POST" if path.endswith("train") else "GET", path, headers={})
            self.assertEqual(response.status_code, 401)
            self.assertIn("Basic", response.headers["WWW-Authenticate"])
        for authorization in ["Basic !!!", "Bearer token", "Basic " + base64.b64encode(b"researcher:wrong").decode()]:
            self.assertEqual(self.request("GET", "/api/investigations", headers={"Authorization": authorization}).status_code, 401)
        self.assertEqual(self.service.investigations.list(), [])

    def test_host_origin_and_forwarded_host_cannot_bypass_access_policy(self):
        for headers in [{**self.headers, "Origin": "https://attacker.example"},
                        {**self.headers, "Origin": ORIGIN + ".evil.test"},
                        {**self.headers, "Host": "attacker.example", "X-Forwarded-Host": "vigil.example"}]:
            self.assertEqual(self.request("GET", "/api/health", headers=headers).status_code, 403)
        self.assertEqual(self.request("GET", "/api/health").status_code, 200)

    def test_health_is_minimal_and_detects_unavailable_workspace(self):
        health = self.request("GET", "/healthz", headers={})
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json, {"status": "ok"})
        with closing(sqlite3.connect(self.service.investigations.path)) as conn:
            conn.execute("DROP TABLE investigations")
        self.assertEqual(self.request("GET", "/healthz", headers={}).status_code, 503)

    def test_save_reopen_update_and_history_survive_a_new_hosted_app(self):
        payload = {"name": "Hosted research", "notes": "A saved question", "cohort": COHORT,
                   "view": "signals", "reaction": "NAUSEA", "retrieved_at": ""}
        first = self.request("POST", "/api/investigations/save", json=payload)
        self.assertEqual(first.status_code, 200)
        saved = first.json
        second = create_app(SETTINGS, DashboardService(storage_root=self.temp.name)).test_client()
        restored = second.get("/api/investigations?id=" + saved["id"], base_url=ORIGIN, headers=self.headers)
        self.assertEqual(restored.json["notes"], payload["notes"])
        edit = {**payload, "id": saved["id"], "revision": 1, "notes": "Updated question"}
        self.assertEqual(self.request("POST", "/api/investigations/save", json=edit).json["revision"], 2)
        self.assertEqual(self.request("POST", "/api/investigations/save", json=edit).status_code, 409)
        history = self.request("GET", "/api/investigations/history?id=" + saved["id"])
        self.assertEqual([event["revision"] for event in history.json["events"]], [2, 1])

    def test_existing_narrative_and_static_head_contracts_are_preserved(self):
        result = self.request("POST", "/api/narratives", json={"texts": ["No stroke. Nausea improved."]})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json["total"], 1)
        head = self.request("HEAD", "/")
        self.assertEqual(head.status_code, 200)
        self.assertEqual(head.data, b"")
        self.assertGreater(int(head.headers["Content-Length"]), 0)
        self.assertEqual(head.headers["X-Frame-Options"], "DENY")
        self.assertEqual(self.request("GET", "/api/not-a-route").status_code, 404)

    def test_bad_and_oversized_json_remain_bounded(self):
        self.assertEqual(self.request("POST", "/api/narratives", data="{}", content_type="text/plain").status_code, 415)
        self.assertEqual(self.request("POST", "/api/narratives", data="[", content_type="application/json").status_code, 400)
        self.assertEqual(self.request("POST", "/api/narratives", data=json.dumps({"text": "x" * 2_000_001}), content_type="application/json").status_code, 413)


if __name__ == "__main__":
    unittest.main()

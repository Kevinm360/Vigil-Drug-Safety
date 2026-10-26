"""Public visitors retain tools without sharing an owner's investigation library."""
import tempfile
import unittest
from unittest.mock import patch

from backend.server import DashboardService
from backend.web import create_app
from tests.test_deployment import SETTINGS, ORIGIN, COHORT


DOCUMENT = {"name": "Browser research", "notes": "Private to this browser", "cohort": COHORT,
            "view": "signals", "reaction": "NAUSEA", "retrieved_at": ""}


class PublicVisitorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service = DashboardService(storage_root=self.temp.name)
        self.owner = self.service.investigations.save({**DOCUMENT, "name": "Owner research"})
        self.app = create_app({**SETTINGS, "VIGIL_PUBLIC_VISITORS": "1", "VIGIL_DATA_DIR": self.temp.name}, self.service)
        self.first, self.second = self.app.test_client(), self.app.test_client()

    def get(self, client, path):
        return client.get(path, base_url=ORIGIN)

    def post(self, client, path, data):
        return client.post(path, base_url=ORIGIN, headers={"Origin": ORIGIN}, json=data)

    def test_no_login_prompt_and_cookie_is_protected(self):
        response = self.get(self.first, "/api/workspace-mode")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"public_demo": False, "public_visitors": True})
        self.assertNotIn("WWW-Authenticate", response.headers)
        cookie = response.headers["Set-Cookie"]
        for attribute in ["__Host-vigil-visitor=", "Secure", "HttpOnly", "SameSite=Lax", "Path=/"]:
            self.assertIn(attribute, cookie)

    def test_owner_and_other_browser_cannot_be_read_updated_or_deleted(self):
        saved = self.post(self.first, "/api/investigations/save", DOCUMENT)
        self.assertEqual(saved.status_code, 200)
        identifier = saved.json["id"]
        self.assertEqual(len(self.get(self.first, "/api/investigations").json["investigations"]), 1)
        self.assertEqual(self.get(self.second, "/api/investigations").json, {"investigations": []})
        for client, other_id in [(self.second, identifier), (self.first, self.owner["id"])]:
            self.assertEqual(self.get(client, "/api/investigations?id=" + other_id).status_code, 404)
            self.assertEqual(self.get(client, "/api/investigations/history?id=" + other_id).status_code, 404)
            self.assertEqual(self.post(client, "/api/investigations/delete", {"id": other_id, "revision": 1}).status_code, 404)
            self.assertEqual(self.post(client, "/api/investigations/save", {**DOCUMENT, "id": other_id, "revision": 1}).status_code, 404)
        self.assertEqual(self.service.investigations.get(self.owner["id"])["name"], "Owner research")
        self.assertEqual(self.get(self.first, "/api/investigations?id=" + identifier).json["notes"], DOCUMENT["notes"])

    def test_analysis_routes_remain_available_and_origin_is_checked(self):
        with patch.object(self.service, "train", return_value={"status": "trained"}):
            self.assertEqual(self.post(self.first, "/api/model/train", COHORT).status_code, 200)
        response = self.first.post("/api/narratives", base_url=ORIGIN,
                                   headers={"Origin": "https://elsewhere.example"}, json={"text": "nausea"})
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("WWW-Authenticate", response.headers)

    def test_invalid_cookie_is_replaced_and_never_used_as_a_path(self):
        self.first.set_cookie("__Host-vigil-visitor", "../../owner", domain="vigil.example", secure=True)
        response = self.get(self.first, "/api/investigations")
        self.assertEqual(response.json, {"investigations": []})
        self.assertIn("Set-Cookie", response.headers)


"""Saved research survives restarts and keeps changes scoped to the chosen reaction."""
import copy
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from backend.investigations import InvestigationError, InvestigationStore
from backend.server import APIError, DashboardHandler, DashboardService, validate_params

COHORT = {"mode": "live", "drug": "METFORMIN", "compare": "IBUPROFEN", "start": "2025-01-01", "end": "2025-01-31", "age": "All", "sex": "Female", "reporters": "Physician"}
DOCUMENT = {"name": "Metformin follow-up", "notes": "Inspect the supporting records before interpreting a signal.", "cohort": COHORT, "view": "signals", "reaction": "NAUSEA", "retrieved_at": "2026-10-24T10:00:00+00:00"}


class InvestigationStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "workspace" / "investigations.sqlite3"
        self.store = InvestigationStore(self.path, validate_params)
        self.addCleanup(self.temp.cleanup)

    def test_saved_context_and_notes_survive_new_store_instance(self):
        saved = self.store.save(copy.deepcopy(DOCUMENT))
        self.assertEqual(saved["revision"], 1)
        reopened = InvestigationStore(self.path, validate_params).get(saved["id"])
        for key in DOCUMENT:
            self.assertEqual(reopened[key], DOCUMENT[key])
        self.assertEqual(reopened["created_at"], saved["created_at"])
        listing = self.store.list()
        self.assertNotIn("notes", listing[0])
        self.assertEqual(listing[0]["reaction"], "NAUSEA")

    def test_stale_updates_and_deletes_cannot_overwrite_another_window(self):
        first = self.store.save(DOCUMENT)
        second_store = InvestigationStore(self.path, validate_params)
        changed = {key: first[key] for key in DOCUMENT}
        changed.update(id=first["id"], revision=first["revision"], notes="Updated evidence")
        updated = second_store.save(changed)
        self.assertEqual(updated["revision"], 2)
        with self.assertRaises(InvestigationError) as update_error:
            self.store.save(changed)
        self.assertEqual(update_error.exception.status, 409)
        with self.assertRaises(InvestigationError) as delete_error:
            self.store.delete(first["id"], first["revision"])
        self.assertEqual(delete_error.exception.status, 409)
        self.assertEqual(self.store.get(first["id"])["notes"], "Updated evidence")
        self.store.delete(first["id"], updated["revision"])
        self.assertEqual(second_store.list(), [])

    def test_save_as_new_leaves_original_unchanged(self):
        first = self.store.save(DOCUMENT)
        second = self.store.save({**DOCUMENT, "notes": "Alternative hypothesis"})
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(len(self.store.list()), 2)
        self.assertEqual(self.store.get(first["id"])["notes"], DOCUMENT["notes"])

    def test_validation_rejects_incomplete_or_unexpected_data(self):
        variants = [{**DOCUMENT, "name": " "}, {**DOCUMENT, "notes": "x" * 10001},
                    {**DOCUMENT, "view": {}}, {**DOCUMENT, "view": "admin"},
                    {**DOCUMENT, "cohort": {"drug": "METFORMIN"}},
                    {**DOCUMENT, "api_key": "do-not-persist"}, {**DOCUMENT, "retrieved_at": "yesterday"},
                    {**DOCUMENT, "cohort": {**COHORT, "end": "2024-01-01"}}]
        for body in variants:
            with self.subTest(body=list(body)):
                with self.assertRaises((InvestigationError, APIError)):
                    self.store.save(body)
        self.assertEqual(self.store.list(), [])

    def test_plain_text_sql_characters_round_trip_without_execution(self):
        note = "<script>alert(1)</script> '; DROP TABLE investigations; --"
        saved = self.store.save({**DOCUMENT, "name": "Researcher's note", "notes": note})
        self.assertEqual(self.store.get(saved["id"])["notes"], note)
        self.assertEqual(len(self.store.list()), 1)
        with self.assertRaises(InvestigationError):
            self.store.get("../../secrets.toml")


class ReactionQueryTests(unittest.TestCase):
    def test_focus_query_preserves_cohort_and_escapes_the_complete_term(self):
        service = DashboardService()
        service.client = unittest.mock.Mock()
        service.client.count.return_value = 21
        service.fetch_report_sample = unittest.mock.Mock(return_value={"records": [{"safetyreportid": "1"}], "skipped_oversized": 1})
        result = service.reaction_reports({**COHORT, "reaction": 'Nausea " OR serious:1'})
        query = service.client.count.call_args.args[0]
        self.assertIn('medicinalproduct:"METFORMIN"', query)
        self.assertIn('patient.patientsex:2', query)
        self.assertIn('primarysource.qualification:1', query)
        self.assertIn('reactionmeddrapt.exact:"NAUSEA \\" OR SERIOUS:1"', query)
        self.assertEqual(service.fetch_report_sample.call_args.args[:3], (query, 20, "receivedate:desc"))
        self.assertEqual(result["total"], 21)
        self.assertEqual(result["skipped_oversized"], 1)

    def test_zero_and_failed_queries_do_not_fall_back_to_unfiltered_reports(self):
        service = DashboardService()
        service.client = unittest.mock.Mock()
        service.client.count.return_value = 0
        service.fetch_report_sample = unittest.mock.Mock()
        self.assertEqual(service.reaction_reports({**COHORT, "reaction": "NAUSEA"})["records"], [])
        service.fetch_report_sample.assert_not_called()
        service.client.count.side_effect = APIError("FDA unavailable", 503)
        with self.assertRaisesRegex(APIError, "FDA unavailable"):
            service.reaction_reports({**COHORT, "reaction": "NAUSEA"})

    def test_archive_filter_uses_exact_terms_not_substring_matches(self):
        service = DashboardService()
        service.dashboard = unittest.mock.Mock(return_value={"narratives": {"records": [
            {"id": 1, "reaction_terms": ["pain"]}, {"id": 2, "reaction_terms": ["chest pain"]}]}})
        result = service.reaction_reports({**COHORT, "mode": "reference", "sex": "", "reporters": "", "reaction": "PAIN"})
        self.assertEqual([row["id"] for row in result["records"]], [1])


class InvestigationHTTPTests(unittest.TestCase):
    def test_http_save_list_read_update_conflict_and_delete(self):
        with tempfile.TemporaryDirectory() as directory:
            store = InvestigationStore(Path(directory) / "investigations.sqlite3", validate_params)
            class Handler(DashboardHandler):
                service = DashboardService()
                def log_message(self, *_):
                    pass
            Handler.service.investigations = store
            http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            worker = threading.Thread(target=http.serve_forever, daemon=True)
            worker.start()
            def request(method, path, body=None, origin=None):
                conn = HTTPConnection("127.0.0.1", http.server_port)
                headers = {"Content-Type": "application/json"}
                if origin:
                    headers["Origin"] = origin
                conn.request(method, path, json.dumps(body) if body is not None else None, headers)
                response = conn.getresponse()
                status, data = response.status, json.loads(response.read())
                conn.close()
                return status, data
            try:
                status, saved = request("POST", "/api/investigations/save", DOCUMENT)
                self.assertEqual(status, 200)
                identifier = saved["id"]
                self.assertEqual(request("GET", "/api/investigations")[1]["investigations"][0]["id"], identifier)
                self.assertEqual(request("GET", "/api/investigations?id="+identifier)[1]["notes"], DOCUMENT["notes"])
                edit = {**DOCUMENT, "id": identifier, "revision": 1, "name": "Renamed investigation"}
                self.assertEqual(request("POST", "/api/investigations/save", edit)[1]["revision"], 2)
                self.assertEqual(request("POST", "/api/investigations/save", edit)[0], 409)
                self.assertEqual(request("POST", "/api/investigations/save", DOCUMENT, "https://attacker.example")[0], 403)
                self.assertEqual(request("POST", "/api/investigations/delete", {"id": identifier, "revision": 2})[0], 200)
                self.assertEqual(request("GET", "/api/investigations?id="+identifier)[0], 404)
            finally:
                http.shutdown()
                http.server_close()
                worker.join()


if __name__ == "__main__":
    unittest.main()

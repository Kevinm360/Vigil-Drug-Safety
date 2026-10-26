"""Real PostgreSQL contracts run against the isolated CI service, never personal data."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import psycopg
from backend.investigations import InvestigationError
from backend.postgres_investigations import PostgresInvestigationStore
from backend.server import DashboardService, validate_params
from backend.web import create_app
from tests.test_deployment import SETTINGS, ORIGIN, AUTH

URL = os.environ.get("VIGIL_TEST_DATABASE_URL", "")
COHORT = {"mode": "live", "drug": "METFORMIN", "compare": "", "start": "2025-01-01", "end": "2025-01-31", "age": "All", "sex": "Female", "reporters": "Physician"}
DOCUMENT = {"name": "Isolated database contract", "notes": "Before · original notes", "cohort": COHORT,
            "view": "signals", "reaction": "Nausea", "retrieved_at": "2026-10-25T10:00:00Z"}


class HostedDatabaseConfigurationTests(unittest.TestCase):
    def test_pooled_connection_applies_timeouts_after_connecting(self):
        store = PostgresInvestigationStore("postgresql://owner:private@remote-pooler.example/vigil?sslmode=require", validate_params)
        connection = MagicMock()
        with patch("backend.postgres_investigations.psycopg.connect", return_value=connection) as connect:
            self.assertIs(store.connect(), connection)
        self.assertNotIn("options", connect.call_args.kwargs)
        self.assertEqual(connect.call_args.kwargs["sslmode"], "require")
        self.assertEqual(connection.execute.call_count, 2)
        self.assertTrue(all(call.args[0].startswith("SET LOCAL ") for call in connection.execute.call_args_list))

    def test_failed_timeout_setup_closes_connection(self):
        store = PostgresInvestigationStore("postgresql://owner:private@remote.example/vigil", validate_params)
        connection = MagicMock()
        connection.execute.side_effect = psycopg.OperationalError("Connection lost")
        with patch("backend.postgres_investigations.psycopg.connect", return_value=connection):
            with self.assertRaises(psycopg.OperationalError):
                store.connect()
        connection.close.assert_called_once()

    def test_remote_database_requires_tls_and_does_not_expose_connection_errors(self):
        with self.assertRaises(ValueError):
            PostgresInvestigationStore("postgresql://owner:private@remote.example/vigil?sslmode=disable", validate_params)
        store = PostgresInvestigationStore("postgresql://owner:private@remote.example/vigil?sslmode=require", validate_params)
        with patch.object(store, "connect", side_effect=psycopg.OperationalError("Do not expose private-password")):
            with self.assertRaises(InvestigationError) as error:
                store.list()
        self.assertEqual(error.exception.status, 503)
        self.assertNotIn("private-password", str(error.exception))

    def test_free_hosting_cannot_silently_use_ephemeral_sqlite(self):
        with self.assertRaisesRegex(ValueError, "VIGIL_DATABASE_URL"):
            create_app({**SETTINGS, "VIGIL_REQUIRE_REMOTE_STORE": "1"})


@unittest.skipUnless(URL, "Set VIGIL_TEST_DATABASE_URL for the isolated PostgreSQL integration service.")
class PostgresContracts(unittest.TestCase):
    def test_public_browser_library_survives_an_app_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            settings = {**SETTINGS, "VIGIL_PUBLIC_VISITORS": "1", "VIGIL_DATABASE_URL": URL,
                        "VIGIL_REQUIRE_REMOTE_STORE": "1", "VIGIL_DATA_DIR": folder}
            app = create_app(settings, DashboardService(storage_root=folder))
            first, second = app.test_client(), app.test_client()
            saved = first.post("/api/investigations/save", base_url=ORIGIN, json=DOCUMENT)
            self.assertEqual(saved.status_code, 200)
            identifier = saved.json["id"]
            try:
                self.assertEqual(second.get("/api/investigations?id=" + identifier, base_url=ORIGIN).status_code, 404)
                reopened = create_app(settings, DashboardService(storage_root=folder)).test_client()
                reopened.set_cookie("__Host-vigil-visitor", first.get_cookie("__Host-vigil-visitor", domain="vigil.example").value,
                                    domain="vigil.example", secure=True)
                self.assertEqual(reopened.get("/api/investigations?id=" + identifier, base_url=ORIGIN).json["notes"], DOCUMENT["notes"])
            finally:
                first.post("/api/investigations/delete", base_url=ORIGIN, json={"id": identifier, "revision": 1})

    def test_legacy_owner_rows_remain_private_after_workspace_migration(self):
        saved = self.create()
        with self.store.connect() as conn:
            conn.execute("ALTER TABLE vigil_investigations DROP COLUMN workspace_id")
        self.store.initialize()
        self.assertEqual(self.store.get(saved["id"])["notes"], DOCUMENT["notes"])
        visitor = PostgresInvestigationStore(URL, validate_params, "test-visitor-migration")
        self.assertNotIn(saved["id"], [row["id"] for row in visitor.list()])

    def test_guest_namespaces_cannot_access_owner_or_other_guests(self):
        first = PostgresInvestigationStore(URL, validate_params, "test-visitor-first")
        second = PostgresInvestigationStore(URL, validate_params, "test-visitor-second")
        saved = first.save(copy.deepcopy(DOCUMENT))
        try:
            self.assertNotIn(saved["id"], [row["id"] for row in self.store.list()])
            self.assertNotIn(saved["id"], [row["id"] for row in second.list()])
            for other in [self.store, second]:
                for action in [lambda: other.get(saved["id"]), lambda: other.history(saved["id"]),
                               lambda: other.delete(saved["id"], 1),
                               lambda: other.save({**DOCUMENT, "id": saved["id"], "revision": 1})]:
                    with self.assertRaises(InvestigationError) as error:
                        action()
                    self.assertEqual(error.exception.status, 404)
            self.assertEqual(first.get(saved["id"])["notes"], DOCUMENT["notes"])
        finally:
            first.delete(saved["id"], 1)

    def setUp(self):
        self.store = PostgresInvestigationStore(URL, validate_params)
        self.store.initialize()
        self.identifiers = []

    def tearDown(self):
        for identifier in self.identifiers:
            try:
                saved = self.store.get(identifier)
                self.store.delete(identifier, saved["revision"])
            except InvestigationError as error:
                if error.status != 404:
                    raise

    def create(self):
        result = self.store.save(copy.deepcopy(DOCUMENT))
        self.identifiers.append(result["id"])
        return result

    def test_context_notes_and_revisions_survive_new_connection_and_stale_writes(self):
        first = self.create()
        edit = {**DOCUMENT, "id": first["id"], "revision": 1, "notes": "After · reviewed notes", "reaction": "RASH"}
        updated = PostgresInvestigationStore(URL, validate_params).save(edit)
        self.assertEqual(updated["revision"], 2)
        self.assertEqual(updated["cohort"], COHORT)
        self.assertEqual(self.store.get(first["id"])["notes"], edit["notes"])
        history = self.store.history(first["id"])
        self.assertEqual([event["revision"] for event in history["events"]], [2, 1])
        self.assertEqual(history["events"][1]["snapshot"]["notes"], DOCUMENT["notes"])
        self.assertNotIn("notes", next(item for item in self.store.list() if item["id"] == first["id"]))
        with self.assertRaises(InvestigationError) as error:
            self.store.save(edit)
        self.assertEqual(error.exception.status, 409)
        with self.assertRaises(InvestigationError):
            self.store.delete(first["id"], 1)
        self.assertEqual(len(self.store.history(first["id"])["events"]), 2)

    def test_history_write_failure_rolls_back_document_and_delete_cascades(self):
        first = self.create()
        record = self.store.record
        def fail(conn, document, kind):
            if document["revision"] == 2:
                conn.execute("SELECT * FROM deliberately_absent_vigil_test_table")
            return record(conn, document, kind)
        with patch.object(self.store, "record", side_effect=fail):
            with self.assertRaises(InvestigationError):
                self.store.save({**DOCUMENT, "id": first["id"], "revision": 1, "notes": "Must roll back"})
        self.assertEqual(self.store.get(first["id"])["notes"], DOCUMENT["notes"])
        self.assertEqual(len(self.store.history(first["id"])["events"]), 1)
        self.store.delete(first["id"], 1)
        with self.store.connect() as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM vigil_investigation_revisions WHERE investigation_id=%s", (first["id"],)).fetchone()[0], 0)

    def test_hosted_http_uses_remote_library_and_preserves_owner_authentication(self):
        with tempfile.TemporaryDirectory() as folder:
            service = DashboardService(storage_root=folder)
            app = create_app({**SETTINGS, "VIGIL_DATABASE_URL": URL, "VIGIL_REQUIRE_REMOTE_STORE": "1"}, service)
            client = app.test_client()
            self.assertEqual(client.get("/api/investigations", base_url=ORIGIN).status_code, 401)
            response = client.post("/api/investigations/save", json=DOCUMENT, base_url=ORIGIN, headers={"Authorization": AUTH})
            self.assertEqual(response.status_code, 200)
            self.identifiers.append(response.json["id"])
            self.assertEqual(self.store.get(response.json["id"])["notes"], DOCUMENT["notes"])
            self.assertFalse((Path(folder) / "workspace/investigations.sqlite3").exists())
            self.assertEqual(client.get("/healthz", base_url=ORIGIN).status_code, 200)

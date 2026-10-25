"""Hosted owner library for ephemeral free web instances. Local SQLite stays unchanged."""
from datetime import datetime, timezone
from functools import wraps
import json
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb
from .investigations import InvestigationError, InvestigationStore


def database_errors(method):
    @wraps(method)
    def safe(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except (psycopg.Error, OSError):
            # Driver exceptions can contain connection details. Never return them to a browser.
            raise InvestigationError("The hosted investigation database is unavailable. Your current workspace remains open; retry before leaving it.", 503) from None
    return safe


class PostgresInvestigationStore(InvestigationStore):
    def __init__(self, url, validate_cohort):
        parsed = urlsplit(url)
        if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname or not parsed.path.strip("/"):
            raise ValueError("Provide a complete hosted PostgreSQL connection URL.")
        self.url, self.validate_cohort = url, validate_cohort
        self.local = parsed.hostname in {"127.0.0.1", "localhost", "postgres"}
        if not self.local and parse_qs(parsed.query).get("sslmode", ["require"])[-1] not in {"require", "verify-ca", "verify-full"}:
            raise ValueError("Hosted database connections require TLS.")

    def connect(self):
        options = {"connect_timeout": 5, "options": "-c statement_timeout=5000 -c lock_timeout=5000"}
        if not self.local:
            options["sslmode"] = parse_qs(urlsplit(self.url).query).get("sslmode", ["require"])[-1]
        return psycopg.connect(self.url, **options)

    @database_errors
    def initialize(self):
        with self.connect() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(73465001)")
            conn.execute("CREATE TABLE IF NOT EXISTS vigil_investigations (id TEXT PRIMARY KEY, document JSONB NOT NULL)")
            conn.execute("""CREATE TABLE IF NOT EXISTS vigil_investigation_revisions (
                investigation_id TEXT NOT NULL REFERENCES vigil_investigations(id) ON DELETE CASCADE,
                revision INTEGER NOT NULL, saved_at TEXT NOT NULL, kind TEXT NOT NULL, snapshot JSONB NOT NULL,
                PRIMARY KEY (investigation_id,revision))""")

    def healthy(self):
        try:
            with self.connect() as conn:
                conn.execute("SELECT 1 FROM vigil_investigations LIMIT 1").fetchone()
            return True
        except (psycopg.Error, OSError):
            return False

    @database_errors
    def list(self):
        with self.connect() as conn:
            documents = [row[0] for row in conn.execute("SELECT document FROM vigil_investigations ORDER BY document->>'updated_at' DESC,id DESC")]
        for document in documents:
            document.pop("notes", None)
        return documents

    @database_errors
    def get(self, identifier):
        identifier = self.identifier(identifier)
        with self.connect() as conn:
            row = conn.execute("SELECT document FROM vigil_investigations WHERE id=%s", (identifier,)).fetchone()
        if row is None:
            raise InvestigationError("Investigation not found.", 404)
        return row[0]

    @staticmethod
    def record(conn, document, kind):
        conn.execute("""INSERT INTO vigil_investigation_revisions
            (investigation_id,revision,saved_at,kind,snapshot) VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT (investigation_id,revision) DO NOTHING""",
            (document["id"], document["revision"], document["updated_at"], kind, Jsonb(document)))

    @database_errors
    def history(self, identifier):
        identifier = self.identifier(identifier)
        with self.connect() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(73465002)")
            row = conn.execute("SELECT document FROM vigil_investigations WHERE id=%s", (identifier,)).fetchone()
            if row is None:
                raise InvestigationError("Investigation not found.", 404)
            document = row[0]
            self.record(conn, document, "legacy" if document["revision"] > 1 else "created")
            events = [{"revision": row[0], "saved_at": row[1], "kind": row[2], "snapshot": row[3]}
                      for row in conn.execute("""SELECT revision,saved_at,kind,snapshot FROM vigil_investigation_revisions
                          WHERE investigation_id=%s ORDER BY revision DESC""", (identifier,))]
        return {"id": identifier, "revision": document["revision"], "events": events}

    @database_errors
    def save(self, body):
        name, notes, cohort, view, reaction, retrieved, periods = self.validate(body)
        identifier = self.identifier(body["id"]) if body.get("id") else uuid4().hex
        revision = body.get("revision")
        if body.get("id") and (type(revision) is not int or revision < 1):
            raise InvestigationError("Provide the saved investigation revision.")
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(73465002)")
            previous = conn.execute("SELECT document FROM vigil_investigations WHERE id=%s", (identifier,)).fetchone()
            if body.get("id"):
                if previous is None:
                    raise InvestigationError("Investigation not found.", 404)
                if previous[0]["revision"] != revision:
                    raise InvestigationError("This investigation changed in another window. Open its latest version before updating.", 409)
                self.record(conn, previous[0], "legacy" if revision > 1 else "created")
            elif conn.execute("SELECT count(*) FROM vigil_investigations").fetchone()[0] >= 500:
                raise InvestigationError("Your library holds 500 investigations. Remove an unused investigation before saving another.", 409)
            document = {"id": identifier, "name": name, "notes": notes, "cohort": json.loads(cohort), "view": view,
                        "reaction": reaction, "retrieved_at": retrieved, "periods": json.loads(periods),
                        "created_at": previous[0]["created_at"] if previous else now,
                        "updated_at": now, "revision": revision + 1 if previous else 1}
            conn.execute("""INSERT INTO vigil_investigations (id,document) VALUES (%s,%s)
                ON CONFLICT (id) DO UPDATE SET document=EXCLUDED.document""", (identifier, Jsonb(document)))
            self.record(conn, document, "updated" if previous else "created")
        return document

    @database_errors
    def delete(self, identifier, revision):
        identifier = self.identifier(identifier)
        if type(revision) is not int or revision < 1:
            raise InvestigationError("Provide the saved investigation revision.")
        with self.connect() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(73465002)")
            row = conn.execute("SELECT document FROM vigil_investigations WHERE id=%s", (identifier,)).fetchone()
            if row is None:
                raise InvestigationError("Investigation not found.", 404)
            if row[0]["revision"] != revision:
                raise InvestigationError("This investigation changed in another window. Refresh the library before deleting.", 409)
            conn.execute("DELETE FROM vigil_investigations WHERE id=%s", (identifier,))

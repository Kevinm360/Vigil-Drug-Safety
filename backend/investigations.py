"""Durable local research workspaces. Separate from the disposable FDA cache."""
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
import threading
from uuid import uuid4
try:
    from .period_changes import validate_periods
except ImportError:
    from period_changes import validate_periods


class InvestigationError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class InvestigationStore:
    def __init__(self, path, validate_cohort):
        self.path = Path(path)
        self.validate_cohort = validate_cohort
        self.lock = threading.RLock()

    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""CREATE TABLE IF NOT EXISTS investigations (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, notes TEXT NOT NULL,
                cohort TEXT NOT NULL, view TEXT NOT NULL, reaction TEXT NOT NULL,
                retrieved_at TEXT NOT NULL, created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL, revision INTEGER NOT NULL)""")
            if "periods" not in {row[1] for row in conn.execute("PRAGMA table_info(investigations)")}:
                try:
                    conn.execute("ALTER TABLE investigations ADD COLUMN periods TEXT NOT NULL DEFAULT '{}'")
                except sqlite3.OperationalError:
                    if "periods" not in {row[1] for row in conn.execute("PRAGMA table_info(investigations)")}:
                        raise
            return conn
        except Exception:
            conn.close()
            raise

    @staticmethod
    def identifier(value):
        if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{32}", value):
            raise InvestigationError("Invalid investigation identifier.")
        return value

    @staticmethod
    def decode(row, include_notes=True):
        result = dict(row)
        result["cohort"] = json.loads(result["cohort"])
        result["periods"] = json.loads(result.get("periods", "{}"))
        if not include_notes:
            result.pop("notes")
        return result

    def list(self):
        with self.lock, closing(self.connect()) as conn:
            return [self.decode(row, False) for row in conn.execute(
                "SELECT * FROM investigations ORDER BY updated_at DESC, id DESC")]

    def get(self, identifier):
        identifier = self.identifier(identifier)
        with self.lock, closing(self.connect()) as conn:
            row = conn.execute("SELECT * FROM investigations WHERE id=?", (identifier,)).fetchone()
            if row is None:
                raise InvestigationError("Investigation not found.", 404)
            return self.decode(row)

    def validate(self, body):
        allowed = {"id", "revision", "name", "notes", "cohort", "view", "reaction", "retrieved_at", "periods"}
        if set(body) - allowed:
            raise InvestigationError("Unknown investigation fields.")
        for key, limit in [("name", 120), ("notes", 10000), ("reaction", 200), ("retrieved_at", 40)]:
            value = body.get(key, "")
            if not isinstance(value, str) or len(value) > limit or "\x00" in value:
                raise InvestigationError(f"{key.replace('_', ' ').capitalize()} must be text of at most {limit} characters.")
        name = body.get("name", "").strip()
        if not name:
            raise InvestigationError("Give this investigation a name.")
        if any(ord(character) < 32 for character in body.get("reaction", "")):
            raise InvestigationError("Choose a reaction term without control characters.")
        cohort = body.get("cohort")
        keys = {"mode", "drug", "compare", "start", "end", "age", "sex", "reporters"}
        if not isinstance(cohort, dict) or set(cohort) != keys or any(not isinstance(v, str) for v in cohort.values()):
            raise InvestigationError("Provide the complete applied cohort.")
        cohort = self.validate_cohort(cohort)
        if cohort["mode"] == "reference" and (cohort["age"] != "All" or cohort["sex"] or cohort["reporters"]):
            raise InvestigationError("The synthetic archive does not support patient or reporter filters.")
        # The API validator uses lists internally; the filter controls use CSV strings.
        cohort = {**cohort, "sex": ",".join(cohort["sex"]), "reporters": ",".join(cohort["reporters"])}
        view = body.get("view", "overview")
        if not isinstance(view, str) or view not in {"overview", "reactions", "reports", "signals", "severity", "network", "narratives", "models", "changes"}:
            raise InvestigationError("Choose a valid investigation tab.")
        periods = body.get("periods", {})
        if periods != {} or view == "changes":
            try:
                periods = validate_periods(periods, cohort)
            except ValueError as exc:
                raise InvestigationError(str(exc)) from None
        retrieved = body.get("retrieved_at", "")
        if retrieved:
            try:
                parsed = datetime.fromisoformat(retrieved.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    raise ValueError()
            except ValueError:
                raise InvestigationError("Invalid data retrieval timestamp.") from None
        return name, body.get("notes", ""), json.dumps(cohort), view, body.get("reaction", "").strip().upper(), retrieved, json.dumps(periods)

    def save(self, body):
        values = self.validate(body)
        identifier = self.identifier(body["id"]) if body.get("id") else uuid4().hex
        revision = body.get("revision")
        if body.get("id") and (type(revision) is not int or revision < 1):
            raise InvestigationError("Provide the saved investigation revision.")
        now = datetime.now(timezone.utc).isoformat()
        with self.lock, closing(self.connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            if body.get("id"):
                result = conn.execute("""UPDATE investigations SET name=?, notes=?, cohort=?, view=?, reaction=?,
                    retrieved_at=?, periods=?, updated_at=?, revision=revision+1 WHERE id=? AND revision=?""",
                    (*values, now, identifier, revision))
                if not result.rowcount:
                    exists = conn.execute("SELECT 1 FROM investigations WHERE id=?", (identifier,)).fetchone()
                    raise InvestigationError("This investigation changed in another window. Open its latest version before updating." if exists else "Investigation not found.", 409 if exists else 404)
            else:
                if conn.execute("SELECT count(*) FROM investigations").fetchone()[0] >= 500:
                    raise InvestigationError("Your library holds 500 investigations. Remove an unused investigation before saving another.", 409)
                conn.execute("INSERT INTO investigations (id,name,notes,cohort,view,reaction,retrieved_at,periods,created_at,updated_at,revision) VALUES (?,?,?,?,?,?,?,?,?,?,1)", (identifier, *values, now, now))
            row = conn.execute("SELECT * FROM investigations WHERE id=?", (identifier,)).fetchone()
            return self.decode(row)

    def delete(self, identifier, revision):
        identifier = self.identifier(identifier)
        if type(revision) is not int or revision < 1:
            raise InvestigationError("Provide the saved investigation revision.")
        with self.lock, closing(self.connect()) as conn, conn:
            if not conn.execute("DELETE FROM investigations WHERE id=? AND revision=?", (identifier, revision)).rowcount:
                exists = conn.execute("SELECT 1 FROM investigations WHERE id=?", (identifier,)).fetchone()
                raise InvestigationError("This investigation changed in another window. Refresh the library before deleting." if exists else "Investigation not found.", 409 if exists else 404)

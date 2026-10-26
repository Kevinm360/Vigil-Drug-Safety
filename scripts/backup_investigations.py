"""Consistent owner-library backup: SQLite locally, JSON export for hosted Postgres."""
import argparse
from contextlib import closing
import os
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
import sqlite3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    default = Path(os.environ["VIGIL_DATA_DIR"]) / "workspace/investigations.sqlite3" if os.environ.get("VIGIL_DATA_DIR") else Path(__file__).resolve().parents[1] / ".vigil-workspace/investigations.sqlite3"
    parser.add_argument("--source", type=Path, default=default)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    database_url = os.environ.get("VIGIL_DATABASE_URL")
    if database_url:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from backend.postgres_investigations import PostgresInvestigationStore
        from backend.server import validate_params
        store = PostgresInvestigationStore(database_url, validate_params)
        with store.connect() as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            documents = [row[0] for row in conn.execute("SELECT document FROM vigil_investigations ORDER BY id")]
            revisions = [{"id": row[0], "revision": row[1], "saved_at": row[2], "kind": row[3], "snapshot": row[4]}
                         for row in conn.execute("SELECT investigation_id,revision,saved_at,kind,snapshot FROM vigil_investigation_revisions ORDER BY investigation_id,revision")]
        payload = {"schema_version": 1, "storage_engine": "postgresql", "exported_at": datetime.now(timezone.utc).isoformat(),
                   "investigations": documents, "revisions": revisions}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False)
        print("Hosted investigation export created. Store it privately; it contains research notes and revision history.")
        return
    if not args.source.is_file():
        raise SystemExit("Investigation database not found.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation protects previous backups, including during concurrent runs.
    descriptor = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    with closing(sqlite3.connect(args.source.resolve().as_uri() + "?mode=ro", uri=True)) as source, closing(sqlite3.connect(args.output)) as destination:
        source.backup(destination)
        if destination.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise SystemExit("Backup verification failed; keep the original database.")
    print("Investigation backup created and verified. Store it privately; it contains your research notes.")


if __name__ == "__main__":
    main()

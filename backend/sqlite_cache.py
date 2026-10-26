"""Bounded local cache for public FDA aggregates; no credentials or narratives."""
from contextlib import closing
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import time

_FILE_LOCKS = {}
_FILE_LOCKS_GUARD = threading.Lock()

@dataclass(frozen=True)
class CachedResponse:
    value: dict
    expires_at: float
    created_at: float = 0


class SQLiteResponseCache:
    def __init__(self, path, *, max_bytes=32_000_000, max_entries=512,
                 max_entry_bytes=1_000_000, clock=time.time):
        self.path = Path(path)
        self.max_bytes, self.max_entries = max_bytes, max_entries
        self.max_entry_bytes = min(max_entry_bytes, max_bytes)
        self.clock = clock
        # Multiple clients in one process can reopen the same file. Serialize
        # their short transactions, including initial schema/WAL setup.
        with _FILE_LOCKS_GUARD:
            self.lock = _FILE_LOCKS.setdefault(str(self.path.resolve()).casefold(), threading.RLock())
        self.ready = False
        self.available = True
        self.hits = 0

    @staticmethod
    def key(endpoint, params, totals_only=False):
        # Never put the authentication key, request URL, or search text into keys.
        public = {k: v for k, v in params.items() if k.lower() != "api_key"}
        value = json.dumps(["fda-cache-v1", endpoint, public, totals_only], sort_keys=True)
        return hashlib.sha256(value.encode()).hexdigest()

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=1.5)
        try:
            if not self.ready:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("""CREATE TABLE IF NOT EXISTS response_cache (
                    cache_key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    byte_count INTEGER NOT NULL CHECK (byte_count >= 0)
                )""")
                connection.execute("CREATE INDEX IF NOT EXISTS response_cache_expiry ON response_cache(expires_at)")
                connection.execute("CREATE INDEX IF NOT EXISTS response_cache_age ON response_cache(created_at)")
                connection.commit()
                self.ready = True
            self.available = True
            return connection
        except BaseException:
            connection.close()
            raise

    def get(self, key):
        try:
            with self.lock, closing(self._connect()) as connection, connection:
                now = self.clock()
                row = connection.execute(
                    "SELECT payload, expires_at, created_at FROM response_cache WHERE cache_key = ?", (key,)
                ).fetchone()
                if not row:
                    return None
                if row[1] <= now or row[2] > now:
                    connection.execute("DELETE FROM response_cache WHERE cache_key = ?", (key,))
                    return None
                try:
                    value = json.loads(row[0])
                    if not isinstance(value, dict):
                        raise ValueError("Invalid cache value")
                except (ValueError, TypeError):
                    connection.execute("DELETE FROM response_cache WHERE cache_key = ?", (key,))
                    return None
                self.hits += 1
                return CachedResponse(value, row[1], row[2])
        except (sqlite3.Error, OSError):
            self.available = False
            return None

    def put(self, key, value, ttl, *, created_at=None):
        try:
            payload = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            size = len(payload.encode("utf-8"))
            if ttl <= 0 or size > self.max_entry_bytes:
                return False
            with self.lock, closing(self._connect()) as connection, connection:
                now = self.clock()
                created = now if created_at is None else created_at
                connection.execute("DELETE FROM response_cache WHERE expires_at <= ? OR created_at > ?", (now, now))
                connection.execute("""INSERT INTO response_cache VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(cache_key) DO UPDATE SET payload=excluded.payload,
                    created_at=excluded.created_at, expires_at=excluded.expires_at, byte_count=excluded.byte_count""",
                    (key, payload, created, created + ttl, size))
                count, total = connection.execute("SELECT COUNT(*), COALESCE(SUM(byte_count), 0) FROM response_cache").fetchone()
                while count > self.max_entries or total > self.max_bytes:
                    oldest = connection.execute("SELECT cache_key, byte_count FROM response_cache ORDER BY created_at, rowid LIMIT 1").fetchone()
                    connection.execute("DELETE FROM response_cache WHERE cache_key = ?", (oldest[0],))
                    count, total = count - 1, total - oldest[1]
                return True
        except (sqlite3.Error, OSError, ValueError, TypeError):
            self.available = False
            return False

    def stats(self):
        try:
            with self.lock, closing(self._connect()) as connection:
                count, size = connection.execute(
                    "SELECT COUNT(*), COALESCE(SUM(byte_count), 0) FROM response_cache WHERE expires_at > ? AND created_at <= ?",
                    (self.clock(), self.clock()),
                ).fetchone()
                return {"backend": "sqlite", "available": True, "fresh_entries": count,
                        "payload_bytes": size, "persistent_hits": self.hits}
        except (sqlite3.Error, OSError):
            self.available = False
            return {"backend": "sqlite", "available": False, "fresh_entries": 0,
                    "payload_bytes": 0, "persistent_hits": self.hits}

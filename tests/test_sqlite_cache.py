"""Persistent-cache behavior, privacy boundaries, and restart freshness."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from backend.server import APIError, OpenFDAClient
from backend.sqlite_cache import SQLiteResponseCache


class Response:
    def __init__(self, value):
        self.raw = json.dumps(value).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, limit):
        return self.raw[:limit]


class SQLiteCacheTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "cache.sqlite3"

    def test_survives_a_new_instance_and_expires_on_original_deadline(self):
        now = [1000.0]
        cache = SQLiteResponseCache(self.path, clock=lambda: now[0])
        cache.put("key", {"results": [{"count": 4}]}, 300)
        now[0] = 1299
        reopened = SQLiteResponseCache(self.path, clock=lambda: now[0])
        entry = reopened.get("key")
        self.assertEqual(entry.value["results"][0]["count"], 4)
        self.assertEqual(entry.expires_at, 1300)
        entry.value["results"][0]["count"] = 999
        self.assertEqual(reopened.get("key").value["results"][0]["count"], 4)
        now[0] = 1300
        self.assertIsNone(reopened.get("key"))
        self.assertEqual(reopened.stats()["fresh_entries"], 0)

    def test_limits_evict_oldest_payloads_and_reject_oversized_entries(self):
        now = [1000.0]
        cache = SQLiteResponseCache(self.path, max_entries=2, max_bytes=100, max_entry_bytes=60, clock=lambda: now[0])
        for name in ["old", "middle", "new"]:
            cache.put(name, {"value": name}, 300)
            now[0] += 1
        self.assertIsNone(cache.get("old"))
        self.assertIsNotNone(cache.get("new"))
        self.assertFalse(cache.put("huge", {"value": "x" * 80}, 300))
        self.assertLessEqual(cache.stats()["payload_bytes"], 100)
        self.assertLessEqual(cache.stats()["fresh_entries"], 2)

    def test_byte_budget_is_enforced_separately_from_entry_limit(self):
        cache = SQLiteResponseCache(self.path, max_bytes=60, max_entries=20)
        for i in range(4):
            cache.put(str(i), {"value": "x" * 20}, 300)
        self.assertLessEqual(cache.stats()["payload_bytes"], 60)
        self.assertEqual(cache.stats()["fresh_entries"], 1)

    def test_keys_separate_endpoint_cohort_and_payload_kind_without_credentials(self):
        key = SQLiteResponseCache.key
        params = {"search": 'receivedate:[20250101 TO 20250131] AND drug:"A"', "api_key": "secret"}
        self.assertEqual(key("events", params), key("events", {**params, "api_key": "other-secret"}))
        self.assertNotEqual(key("events", params), key("ndc", params))
        self.assertNotEqual(key("events", params), key("events", {**params, "search": "another cohort"}))
        self.assertNotEqual(key("events", params), key("events", params, True))
        self.assertNotIn("secret", key("events", params))
        self.assertNotIn("receivedate", key("events", params))

    def test_concurrent_instances_use_the_database_without_thread_affinity_errors(self):
        cache = SQLiteResponseCache(self.path)
        cache.put("seed", {"count": 1}, 300)

        def worker(i):
            local = SQLiteResponseCache(self.path)
            self.assertTrue(local.put(str(i), {"count": i}, 300))
            return local.get(str(i)).value["count"]

        with ThreadPoolExecutor(max_workers=6) as pool:
            self.assertEqual(list(pool.map(worker, range(16))), list(range(16)))

    def test_bad_database_or_payload_is_a_cache_miss(self):
        self.path.write_text("not a SQLite database")
        cache = SQLiteResponseCache(self.path)
        self.assertIsNone(cache.get("key"))
        self.assertFalse(cache.put("key", {"value": 1}, 300))
        self.assertFalse(cache.stats()["available"])
        # Test malformed cached JSON in a separate, valid database.
        valid = SQLiteResponseCache(Path(self.folder.name) / "valid.sqlite3")
        valid.put("key", {"value": 1}, 300)
        with closing(sqlite3.connect(valid.path)) as db, db:
            db.execute("UPDATE response_cache SET payload = 'broken json'")
        self.assertIsNone(valid.get("key"))

    def test_fda_aggregate_is_reused_by_a_new_client_without_network_access(self):
        cache = SQLiteResponseCache(self.path)
        calls = []

        def opener(request, timeout):
            calls.append(request.full_url)
            return Response({"results": [{"term": "NAUSEA", "count": 12}]})

        first = OpenFDAClient(opener=opener, cache_store=cache)
        with patch.dict("os.environ", {"OPENFDA_API_KEY": "fake-secret"}):
            expected = first.aggregate("cohort", "patient.reaction.reactionmeddrapt.exact")
        second_store = SQLiteResponseCache(self.path)
        second = OpenFDAClient(opener=lambda *a, **k: self.fail("Network should not be called"), cache_store=second_store)
        self.assertEqual(second.aggregate("cohort", "patient.reaction.reactionmeddrapt.exact"), expected)
        self.assertEqual(len(calls), 1)
        self.assertEqual(second_store.stats()["persistent_hits"], 1)
        with closing(sqlite3.connect(self.path)) as db, db:
            saved = str(db.execute("SELECT * FROM response_cache").fetchall())
        self.assertNotIn("fake-secret", saved)
        self.assertNotIn("api_key", saved)

    def test_rehydrating_memory_does_not_restart_an_entry_expiration_window(self):
        cache = SQLiteResponseCache(self.path)
        params = {"count": "field", "search": "cohort", "limit": 1000}
        key = cache.key("https://api.fda.gov/drug/event.json", params)
        cache.put(key, {"results": [{"count": 1}]}, 8)
        client = OpenFDAClient(cache_store=cache)
        client.request(params)
        expiry = next(iter(client.cache.values()))[0]
        self.assertLessEqual(expiry - time.monotonic(), 8)
        self.assertGreater(expiry - time.monotonic(), 0)

    def test_raw_report_text_is_never_persisted_even_when_retrieving_a_total(self):
        cache = SQLiteResponseCache(self.path)
        value = {"meta": {"results": {"total": 7}}, "results": [{"text": "RAW_CASE_TEXT"}]}
        client = OpenFDAClient(opener=lambda *a, **k: Response(value), cache_store=cache)
        self.assertEqual(client.request({"search": "cohort", "limit": 1}), value)
        self.assertEqual(cache.stats()["fresh_entries"], 0)
        self.assertEqual(client.count("cohort"), 7)
        with closing(sqlite3.connect(self.path)) as db, db:
            payload = db.execute("SELECT payload FROM response_cache").fetchone()[0]
        self.assertNotIn("RAW_CASE_TEXT", payload)
        self.assertEqual(json.loads(payload)["meta"]["results"]["total"], 7)

    def test_unavailable_sqlite_falls_back_to_the_fda_request(self):
        self.path.write_text("broken")
        client = OpenFDAClient(cache_store=SQLiteResponseCache(self.path), opener=lambda *a, **k: Response({"results": [{"count": 8}]}))
        self.assertEqual(client.aggregate("cohort", "field"), [{"count": 8}])

    def test_malformed_success_payloads_cannot_poison_totals_with_a_false_zero(self):
        cache = SQLiteResponseCache(self.path)
        for value in [{"results": []}, {"results": [], "meta": {"results": {"total": -1}}}, {"error": {"message": "not data"}}]:
            client = OpenFDAClient(cache_store=cache, opener=lambda *a, **k: Response(value))
            with self.assertRaises(APIError):
                client.count("cohort")
        self.assertEqual(cache.stats()["fresh_entries"], 0)

    def test_upstream_failure_does_not_replace_or_serve_an_expired_entry(self):
        cache = SQLiteResponseCache(self.path)
        params = {"search": "cohort", "count": "field", "limit": 1000}
        cache.put(cache.key("https://api.fda.gov/drug/event.json", params), {"results": [{"count": 99}]}, 300)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE response_cache SET expires_at = 0")

        def offline(*args, **kwargs):
            raise URLError("offline")

        with patch("backend.server.time.sleep"):
            with self.assertRaises(APIError):
                OpenFDAClient(opener=offline, cache_store=cache).aggregate("cohort", "field")
        self.assertEqual(cache.stats()["fresh_entries"], 0)


if __name__ == "__main__":
    unittest.main()

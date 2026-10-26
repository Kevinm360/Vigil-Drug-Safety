"""Request-local provenance for FDA responses, including worker threads."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
import threading

_trace = ContextVar("fda_freshness", default=None)


def timestamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="seconds")


def record(source, retrieved_at, expires_at):
    trace = _trace.get()
    if trace is not None:
        with trace["lock"]:
            trace["items"].append((source, retrieved_at, expires_at))


@contextmanager
def capture():
    trace = {"items": [], "lock": threading.Lock()}
    token = _trace.set(trace)
    try:
        yield trace
    finally:
        _trace.reset(token)


def describe(trace):
    items = trace["items"]
    if not items:
        return {"source": "unknown", "requests": 0}
    sources = {source for source, _, _ in items}
    return {"source": "network" if sources == {"network"} else "cache" if "network" not in sources else "mixed",
            "requests": len(items), "network_requests": sum(source == "network" for source, _, _ in items),
            "memory_hits": sum(source == "memory" for source, _, _ in items),
            "sqlite_hits": sum(source == "sqlite" for source, _, _ in items),
            "retrieved_at": timestamp(min(created for _, created, _ in items)),
            "expires_at": timestamp(min(expiry for _, _, expiry in items))}


def tracked(function):
    @wraps(function)
    def wrapped(self, params, *args, **kwargs):
        with capture() as trace:
            result = function(self, params, *args, **kwargs)
        meta = result.setdefault("meta", {})
        meta.setdefault("generated_at", datetime.now(timezone.utc).isoformat(timespec="seconds"))
        meta["freshness"] = ({"source": "local", "retrieved_at": meta["generated_at"], "cached": bool(meta.get("cached"))}
                             if params.get("mode", "reference") == "reference" else describe(trace))
        return result
    return wrapped

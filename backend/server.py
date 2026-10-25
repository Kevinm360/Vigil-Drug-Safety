"""Local, dependency-light API and static server for the React dashboard.

Run ``python backend/server.py`` after ``npm run build``. No uploaded pickle is
ever loaded. The bundled review archive is synthetic; live FAERS queries always
use openFDA and never silently fall back to reference data.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
from contextvars import copy_context
import csv
import datetime as dt
import io
import json
import math
import mimetypes
import os
from pathlib import Path
import re
import statistics
import sqlite3
import sys
import threading
import time
import tomllib
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen

try:
    from . import freshness
    from .sqlite_cache import SQLiteResponseCache
    from .investigations import InvestigationStore, InvestigationError
    from .period_changes import change_row, validate_periods
except ImportError:  # Direct execution: python backend/server.py
    import freshness
    from sqlite_cache import SQLiteResponseCache
    from investigations import InvestigationStore, InvestigationError
    from period_changes import change_row, validate_periods

ROOT = Path(__file__).resolve().parents[1]
OPENFDA_URL = "https://api.fda.gov/drug/event.json"
SEX_CODES = {"Male": "1", "Female": "2", "Unknown": "0"}
REPORTER_CODES = {"Physician": "1", "Pharmacist": "2", "Other HCP": "3", "Lawyer": "4", "Consumer": "5"}
AGE_BUCKETS = {"0–11": (0, 12), "12–17": (12, 18), "18–44": (18, 45), "45–64": (45, 65), "65+": (65, 151)}
REACTIONS = {
    "gastrointestinal": ["nausea", "vomiting", "diarrhea", "constipation", "stomach cramps", "bloating"],
    "neurological": ["headache", "dizzy", "insomnia", "fatigue", "brain fog", "tremor"],
    "dermatological": ["rash", "itching", "hives", "redness"],
    "cardiovascular": ["palpitations", "chest pain", "blood pressure"],
    "psychiatric": ["anxiety", "depression", "irritable", "panic"],
}
OUTCOMES = {
    "Death": "seriousnessdeath", "Life threatening": "seriousnesslifethreatening",
    "Hospitalization": "seriousnesshospitalization", "Disability": "seriousnessdisabling",
    "Congenital anomaly": "seriousnesscongenitalanomali", "Other serious": "seriousnessother",
}
FLAGS = ["anaphylaxis", "sudden collapse", "cardiac arrest", "arrhythmia", "stroke", "seizure", "convulsion",
         "respiratory failure", "apnea", "liver failure", "hepatotoxicity", "renal failure", "kidney failure",
         "gi bleed", "internal bleeding", "hemorrhage", "rhabdomyolysis", "neutropenia", "thrombocytopenia",
         "pancytopenia", "stevens-johnson", "toxic epidermal necrolysis", "anuria", "syncope", "loss of consciousness",
         "hypotension", "hypertensive crisis", "angioedema", "dystonia", "signal loss", "loss of signal",
         "loss of connection", "no signal", "sensor failure", "sensor error", "inaccurate reading", "false low",
         "erroneous result", "calibration failure", "occlusion", "lead fracture", "electrode detachment",
         "battery failure", "overheating", "burn", "migration", "breakage", "fragment", "infection", "site infection", "extravasation"]
POSITIVE = {"improved", "resolved", "better", "stable", "recovering", "asymptomatic", "tolerated", "helped"}
NEGATIVE = {"worse", "severe", "serious", "critical", "died", "fatal", "hospitalized", "admitted", "icu",
            "bleeding", "vomiting", "rash", "pain", "weakness", "dyspnea", "syncope", "shock", "failure"}
STOPWORDS = set("a an and are as at be been but by did do for from had has have i in is it its me my of on or that the their them then there they this to took was were when with would you your experienced effects side drug patient report reported helped metformin glucophage advil ibuprofen acetaminophen tylenol".split())


class APIError(Exception):
    def __init__(self, message: str, status: int = 400, code=None):
        super().__init__(message)
        self.status = status
        self.code = code


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def api_key():
    """Read only the openFDA credential, from environment or ignored local config."""
    if os.environ.get("OPENFDA_API_KEY"):
        return os.environ["OPENFDA_API_KEY"]
    path = ROOT / ".streamlit" / "secrets.toml"
    if path.is_file():
        try:
            value = tomllib.loads(path.read_text(encoding="utf-8-sig")).get("OPENFDA_API_KEY")
            return str(value) if value else None
        except (OSError, tomllib.TOMLDecodeError):
            pass
    return None


def canonical_drug(value):
    value = str(value or "").strip().upper()
    return {"ADVIL": "IBUPROFEN", "TYLENOL": "ACETAMINOPHEN", "GLUCOPHAGE": "METFORMIN"}.get(value, value)


def date_value(value, field):
    try:
        if not re.fullmatch(r"(?:\d{4}-\d{2}-\d{2}|\d{8})", str(value)):
            raise ValueError
        return dt.datetime.strptime(str(value).replace("-", ""), "%Y%m%d").date()
    except (ValueError, TypeError):
        raise APIError(f"{field} must be a valid date (YYYY-MM-DD).") from None


def integer(value, default, low, high):
    try:
        number = int(default if value in (None, "") else value)
    except (ValueError, TypeError):
        raise APIError("A numeric limit was expected.") from None
    if not low <= number <= high:
        raise APIError(f"Limit must be between {low} and {high}.")
    return number


def selected_values(value, mapping, label):
    if value in (None, "", "All"):
        return []
    values = value if isinstance(value, list) else str(value).split(",")
    if any(v not in mapping for v in values):
        raise APIError(f"Unknown {label} filter.")
    return list(dict.fromkeys(values))


def validate_params(params, defaults=None):
    defaults = defaults or {"start": "2024-01-01", "end": dt.date.today().isoformat()}
    mode = str(params.get("mode", "reference"))
    if mode not in {"reference", "live"}:
        raise APIError("mode must be reference or live.")
    drug = str(params.get("drug", "METFORMIN")).strip().upper()
    compare = str(params.get("compare", "")).strip().upper()
    for name in (drug, compare):
        if name and (len(name) > 120 or not re.fullmatch(r"[\w\s.+'(),/\-]+", name)):
            raise APIError("Use a drug name of 120 characters or fewer, without query operators.")
    if not drug:
        raise APIError("Choose a drug.")
    start = date_value(params.get("start") or defaults["start"], "start")
    end = date_value(params.get("end") or defaults["end"], "end")
    if start > end:
        raise APIError("Start date must be on or before end date.")
    if start < dt.date(1900, 1, 1) or (end - start).days > 36525:
        raise APIError("Choose a date window of 100 years or less, starting after 1900.")
    age = str(params.get("age") or "All").replace("-", "–")
    if age != "All" and age not in AGE_BUCKETS:
        raise APIError("Unknown age group.")
    sexes = selected_values(params.get("sex", params.get("sexes")), SEX_CODES, "sex")
    reporters = selected_values(params.get("reporters"), REPORTER_CODES, "reporter")
    return {"mode": mode, "drug": drug, "compare": compare, "start": start.isoformat(), "end": end.isoformat(),
            "age": age, "sex": sexes, "reporters": reporters}


def cohort_query(params):
    clauses = []
    if params["age"] != "All":
        lo, end = AGE_BUCKETS[params["age"]]
        parts = []
        for unit, factor in [("801", 1), ("802", 12), ("803", 52), ("804", 365.25), ("805", 365.25 * 24)]:
            # Lucene inclusive ranges: using the next boundary minus a tiny
            # amount covers fractional ages as well as integer coded ages.
            lower, upper = lo * factor, end * factor - 0.000001
            parts.append(f"(patient.patientonsetageunit:{unit} AND patient.patientonsetage:[{lower:g} TO {upper:g}])")
        clauses.append("(" + " OR ".join(parts) + ")")
    for field, values, mapping in [("patient.patientsex", params["sex"], SEX_CODES),
                                   ("primarysource.qualification", params["reporters"], REPORTER_CODES)]:
        if values:
            clauses.append("(" + " OR ".join(f"{field}:{mapping[v]}" for v in values) + ")")
    return " AND ".join(clauses)


def search_query(params, drug=True, flag=None):
    clauses = [f"receivedate:[{params['start'].replace('-', '')} TO {params['end'].replace('-', '')}]"]
    if drug:
        clauses.append(f'patient.drug.medicinalproduct:"{params["drug"]}"')
    cohort = cohort_query(params)
    if cohort:
        clauses.append(cohort)
    if flag:
        clauses.append(flag)
    return " AND ".join(clauses)


class OpenFDAClient:
    """Bounded, cached requests; API key remains on this local server."""
    def __init__(self, timeout=12, opener=None, base_url=OPENFDA_URL, cache_store=None, cache_ttl=300):
        self.timeout = timeout
        self.opener = opener or urlopen
        self.base_url = base_url
        self.cache = {}
        self.cache_bytes = 0
        self.lock = threading.Lock()
        self.cache_store = cache_store
        self.cache_ttl = cache_ttl

    def _remember(self, cache_key, data, size, ttl, retrieved_at=None):
        if size > 1_000_000 or ttl <= 0:
            return
        with self.lock:
            previous = self.cache.pop(cache_key, None)
            if previous:
                self.cache_bytes -= previous[2]
            while self.cache and (len(self.cache) >= 400 or self.cache_bytes + size > 8_000_000):
                removed = self.cache.pop(next(iter(self.cache)))
                self.cache_bytes -= removed[2]
            self.cache[cache_key] = (time.monotonic() + ttl, copy.deepcopy(data), size, retrieved_at if retrieved_at is not None else time.time())
            self.cache_bytes += size

    def request(self, params, *, totals_only=False):
        cache_key = urlencode(sorted(params.items())) + ("&__totals_only=1" if totals_only else "")
        with self.lock:
            cached = self.cache.get(cache_key)
            if cached and cached[0] > time.monotonic():
                freshness.record("memory", cached[3], time.time() + cached[0] - time.monotonic())
                return copy.deepcopy(cached[1])
        # Raw case reports and narrative text stay out of persistent storage.
        disk_key = self.cache_store.key(self.base_url, params, totals_only) if self.cache_store and (totals_only or "count" in params) else None
        if disk_key:
            saved = self.cache_store.get(disk_key)
            if saved is not None:
                self._remember(cache_key, saved.value, len(json.dumps(saved.value).encode()), saved.expires_at - time.time(), saved.created_at)
                freshness.record("sqlite", saved.created_at, saved.expires_at)
                return saved.value
        payload = dict(params)
        key = api_key()
        if key:
            payload["api_key"] = key
        request = Request(self.base_url + "?" + urlencode(payload), headers={"User-Agent": "SideEffectsSignalMonitor/2.0", "Accept": "application/json"})
        for attempt in range(2):
            try:
                with self.opener(request, timeout=self.timeout) as response:
                    raw = response.read(25_000_001)
                    if len(raw) > 25_000_000:
                        raise APIError("openFDA response was too large for one batch.", 502, code="response_too_large")
                    data = json.loads(raw)
                if not isinstance(data, dict) or "error" in data or not isinstance(data.get("results"), list):
                    raise APIError("openFDA returned an unexpected response.", 502)
                if totals_only:
                    total = data.get("meta", {}).get("results", {}).get("total")
                    if not isinstance(total, int) or isinstance(total, bool) or total < 0:
                        raise APIError("openFDA returned an invalid report total.", 502)
                    data = {"results": [], "meta": {"results": {"total": total}}}
                # Keep small aggregates hot, without retaining hundreds of MB
                # of raw report drug lists after a training run.
                size = len(json.dumps(data, ensure_ascii=False).encode())
                fetched_at = time.time()
                self._remember(cache_key, data, size, self.cache_ttl, fetched_at)
                freshness.record("network", fetched_at, fetched_at + self.cache_ttl)
                if disk_key:
                    self.cache_store.put(disk_key, data, self.cache_ttl, created_at=fetched_at)
                return data
            except HTTPError as exc:
                try:
                    detail = json.loads(exc.read(10000)).get("error", {})
                except (ValueError, AttributeError):
                    detail = {}
                if exc.code == 404:
                    # Only a genuine no-match response is treated as empty.
                    message = detail.get("message", "") if isinstance(detail, dict) else ""
                    if "no matches" in str(message).lower():
                        empty = {"results": [], "meta": {"results": {"total": 0}}}
                        fetched_at = time.time()
                        self._remember(cache_key, empty, 64, self.cache_ttl, fetched_at)
                        freshness.record("network", fetched_at, fetched_at + self.cache_ttl)
                        if disk_key:
                            self.cache_store.put(disk_key, empty, self.cache_ttl, created_at=fetched_at)
                        return empty
                if exc.code in {429, 500, 502, 503, 504} and not attempt:
                    time.sleep(0.6)
                    continue
                if exc.code in {401, 403}:
                    raise APIError("openFDA requires a valid API key for this query. Set OPENFDA_API_KEY in the server environment or in .streamlit/secrets.toml, then retry.", 503) from None
                error = "openFDA rate limit reached. Wait a moment or configure OPENFDA_API_KEY." if exc.code == 429 else f"openFDA request failed (HTTP {exc.code})."
                raise APIError(error, 503) from None
            except (URLError, TimeoutError, OSError, json.JSONDecodeError):
                if not attempt:
                    time.sleep(0.4)
                    continue
                raise APIError("openFDA could not be reached. Check your connection and retry; the local reference archive remains available.", 503) from None
        raise APIError("openFDA request failed.", 503)

    def count(self, query):
        result = self.request({"search": query, "limit": 1}, totals_only=True)
        return int(result.get("meta", {}).get("results", {}).get("total", 0))

    def aggregate(self, query, field, limit=1000):
        return self.request({"search": query, "count": field, "limit": limit}).get("results", [])


def week_start(value):
    date = date_value(str(value)[:10], "record date")
    return date - dt.timedelta(days=date.weekday())


def weekly_series(rows, start, end, compare=None):
    """Monday anchored buckets; None means comparator data is unavailable."""
    counts = Counter()
    other = Counter()
    for row in rows:
        counts[week_start(row["date"])] += int(row.get("count", 1))
    for row in compare or []:
        other[week_start(row["date"])] += int(row.get("count", 1))
    first, last = week_start(start), week_start(end)
    out, history = [], []
    for offset in range(0, (last - first).days + 1, 7):
        date = first + dt.timedelta(days=offset)
        count = counts[date]
        baseline = history[-8:]
        deviation = statistics.stdev(baseline) if len(baseline) >= 5 else 0
        z = (count - statistics.mean(baseline)) / deviation if deviation > 0 else 0
        out.append({"date": date.isoformat(), "count": count, "compare_count": other[date] if compare is not None else None, "z": round(z, 4)})
        history.append(count)
    return out


def association(reaction, a, drug_total, reaction_total, total):
    """2x2 reporting disproportionality, with consistent zero-cell correction."""
    if drug_total <= 0 or total <= drug_total:
        return None
    a, b, c = int(a), int(drug_total - a), int(reaction_total - a)
    d = int(total - a - b - c)
    if min(a, b, c, d) < 0:
        return None  # inconsistent aggregates cannot form a valid contingency table
    A, B, C, D = (x + 0.5 for x in (a, b, c, d)) if min(a, b, c, d) == 0 else (a, b, c, d)
    prr = (A / (A + B)) / (C / (C + D))
    ror = (A * D) / (B * C)
    se_prr = math.sqrt(1 / A - 1 / (A + B) + 1 / C - 1 / (C + D))
    se_ror = math.sqrt(1 / A + 1 / B + 1 / C + 1 / D)
    n = a + b + c + d
    denom = (a + b) * (c + d) * (a + c) * (b + d)
    chi2 = n * (a * d - b * c) ** 2 / denom if denom else 0
    return {"reaction": reaction, "a": a, "b": b, "c": c, "d": d,
            "prr": prr, "prr_low": math.exp(math.log(prr) - 1.96 * se_prr), "prr_high": math.exp(math.log(prr) + 1.96 * se_prr),
            "ror": ror, "ror_low": math.exp(math.log(ror) - 1.96 * se_ror), "ror_high": math.exp(math.log(ror) + 1.96 * se_ror),
            "chi2": chi2, "signal": a >= 3 and prr >= 2 and chi2 >= 4, "corrected": min(a, b, c, d) == 0}


def score_signals(reactions, drug_total, background, total):
    out = [association(row["reaction"], row["reports"], drug_total, background.get(row["reaction"].upper(), 0), total) for row in reactions]
    return sorted([row for row in out if row], key=lambda r: (r["signal"], r["prr"], r["a"]), reverse=True)


def reaction_mentions(text):
    return [term.upper() for terms in REACTIONS.values() for term in terms if re.search(r"\b" + re.escape(term) + r"\b", text, re.I)]


def normalize_text(value):
    return re.sub(r"\s+", " ", re.sub(r"\(b\)\(\d+\)", " ", str(value).lower())).strip()


def annotate(text):
    value = normalize_text(text)
    tokens = re.findall(r"\b[a-z][a-z'-]{2,}\b", value)
    flags = []
    negated = []
    for phrase in FLAGS:
        for match in re.finditer(r"\b" + re.escape(phrase) + r"\b", value):
            preceding = value[max(0, match.start() - 45):match.start()]
            # A small documented negation heuristic prevents obvious 'no stroke'
            # from being asserted as a positive finding.
            prefix = re.split(r"[.;,]", preceding)[-1]
            target = negated if re.search(r"\b(no|not|without|denies|denied|negative for)\b(?:\s+\w+){0,4}\s*$", prefix) else flags
            if phrase not in target:
                target.append(phrase)
    positive, negative = sum(t in POSITIVE for t in tokens), sum(t in NEGATIVE for t in tokens)
    return {"clinical_flags": flags, "negated_flags": negated, "pos_count": positive, "neg_count": negative,
            "sentiment_net": positive - negative, "sentiment": "positive" if positive > negative else "negative" if negative > positive else "neutral"}


def keyword_scores(texts, top_k=25, min_df=1, ngram_low=1, ngram_high=2, custom_stopwords=None):
    """Transparent TF-IDF unigram/bigram extraction with no external model."""
    documents = []
    for text in texts:
        stop = STOPWORDS.union(custom_stopwords or [])
        tokens = [t for t in re.findall(r"\b[a-z][a-z'-]{2,}\b", normalize_text(text)) if t not in stop]
        terms = [" ".join(tokens[index:index + size]) for size in range(ngram_low, ngram_high + 1) for index in range(len(tokens) - size + 1)]
        documents.append(terms)
    frequency = Counter(term for terms in documents for term in set(terms))
    scores = Counter()
    for terms in documents:
        if not terms:
            continue
        counts = Counter(terms)
        weights = {term: count / len(terms) * (math.log((1 + len(documents)) / (1 + frequency[term])) + 1) for term, count in counts.items() if frequency[term] >= min_df}
        norm = math.sqrt(sum(weight * weight for weight in weights.values())) or 1
        for term, weight in weights.items():
            scores[term] += weight / norm
    return [{"term": term, "score": round(score, 5), "documents": frequency[term]} for term, score in scores.most_common(top_k)]


def contrastive_terms(annotated):
    """Smoothed descriptive term contrast for phrase-flagged vs other text."""
    groups = [Counter(), Counter()]
    for row in annotated:
        tokens = [term for term in re.findall(r"\b[a-z][a-z'-]{2,}\b", normalize_text(row["text"])) if term not in STOPWORDS]
        groups[0 if row["clinical_flags"] else 1].update(tokens)
    left, right = groups
    if not left or not right:
        return []
    vocab = left.keys() | right.keys()
    prior = {term: left[term] + right[term] + 0.5 for term in vocab}
    alpha_total, n_left, n_right = sum(prior.values()), sum(left.values()), sum(right.values())
    terms = []
    for term in vocab:
        a, b = left[term] + prior[term], right[term] + prior[term]
        c, d = n_left - left[term] + alpha_total - prior[term], n_right - right[term] + alpha_total - prior[term]
        delta = math.log(a / c) - math.log(b / d)
        z = delta / math.sqrt(1 / a + 1 / b + 1 / c + 1 / d)
        terms.append({"term": term, "z": z, "log_odds": delta, "c_pos": left[term], "c_neg": right[term], "group": "flagged" if z >= 0 else "other"})
    terms.sort(key=lambda row: row["z"], reverse=True)
    return terms[:10] + terms[-10:]


def narratives_result(records, notice, config=None):
    annotated = [{**row, **annotate(row["text"])} for row in records]
    flags = Counter(flag for row in annotated for flag in row["clinical_flags"])
    sentiment = Counter(row["sentiment"] for row in annotated)
    return {"records": annotated, "total": len(annotated), "keywords": keyword_scores([row["text"] for row in records], **(config or {})),
            "flags": [{"flag": flag, "count": count} for flag, count in flags.most_common()],
            "sentiment": [{"label": label, "count": sentiment[label]} for label in ["positive", "neutral", "negative"]],
            "contrastive": contrastive_terms(annotated), "notice": notice, "method": "TF-IDF keywords, phrase matching with short-context negation, and a transparent sentiment lexicon. Contrastive terms use smoothed weighted log odds. Not a clinical assessment."}


def graph_result(drug_counts, signal_rows=None):
    nodes, links, rx_totals = [], [], Counter()
    primary_counts = next(iter(drug_counts.values()), Counter())
    signal_map = {str(row["reaction"]).upper(): row for row in signal_rows or []}
    # Keep the subject's available reactions, then fill remaining capacity from
    # comparison drugs. The frontend can choose a lower visible density.
    visible_reactions = dict.fromkeys(reaction for reaction, _ in primary_counts.most_common(80))
    for counts in drug_counts.values():
        for reaction, _ in counts.most_common(80):
            if len(visible_reactions) < 80:
                visible_reactions.setdefault(reaction, None)
    for drug, counts in drug_counts.items():
        nodes.append({"id": "drug:" + drug, "label": drug, "type": "drug", "value": sum(counts.values())})
        for reaction, count in counts.most_common(80):
            if reaction not in visible_reactions:
                continue
            rx_totals[reaction] += count
            links.append({"source": "drug:" + drug, "target": "rx:" + reaction, "value": count})
    for reaction, count in rx_totals.items():
        category = next((key for key, terms in REACTIONS.items() if reaction.lower() in terms), "reaction")
        node = {"id": "rx:" + reaction, "label": reaction, "type": "reaction", "category": category,
                "value": count, "a": primary_counts.get(reaction, 0)}
        signal = signal_map.get(reaction.upper())
        if signal and reaction in primary_counts:
            node.update({key: signal[key] for key in ["prr", "ror", "chi2", "signal", "prr_low", "prr_high", "ror_low", "ror_high"] if key in signal})
        nodes.append(node)
    return {"nodes": nodes, "links": links}


def _model_constants():
    path = ROOT / "app" / "serious_outcome.py"
    values = {}
    if path.is_file():
        for node in ast.parse(path.read_text(encoding="utf-8-sig")).body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                try:
                    values[node.targets[0].id] = ast.literal_eval(node.value)
                except (ValueError, TypeError):
                    pass
    return values


def model_overview():
    values = _model_constants()
    audit = []
    for name in values.get("NUMERIC_FEATURES", []) + values.get("CATEGORICAL_FEATURES", []):
        risk, rationale = values.get("FEATURE_PROXY_AUDIT", {}).get(name, ("Unknown", ""))
        audit.append({"predictor": name, "display_name": values.get("FEATURE_LABELS", {}).get(name, name),
                      "type": "numeric" if name in values.get("NUMERIC_FEATURES", []) else "categorical",
                      "proxy_risk": risk, "reduced_model": "Removed" if name in values.get("ADMINISTRATIVE_PROXY_FEATURES", []) else "Retained",
                      "audit_rationale": rationale})
    return {"status": "untrained", "notice": "Train on live report-level FAERS data to compare Logistic Regression and XGBoost, full vs reduced proxy features, using the same held-out split. The synthetic review archive has no seriousness labels.",
            "audit": audit, "exclusions": values.get("LEAKAGE_EXCLUSIONS", []), "evaluation": None,
            "min_records": values.get("MIN_ROWS", 200), "min_class_count": values.get("MIN_CLASS_COUNT", 20)}


class DashboardService:
    def __init__(self, root=ROOT, client=None, storage_root=None):
        self.root = Path(root)
        self.workspace_location = "local"
        runtime = Path(storage_root) / "cache" if storage_root else self.root / ".vigil-runtime"
        workspace = Path(storage_root) / "workspace" if storage_root else self.root / ".vigil-workspace"
        self.response_cache = SQLiteResponseCache(runtime / "fda-cache.sqlite3")
        self.investigations = InvestigationStore(workspace / "investigations.sqlite3", validate_params)
        self.client = client or OpenFDAClient(cache_store=self.response_cache)
        self.device_client = OpenFDAClient(base_url="https://api.fda.gov/device/event.json", cache_store=self.response_cache)
        self.drug_client = OpenFDAClient(base_url="https://api.fda.gov/drug/ndc.json", cache_store=self.response_cache, cache_ttl=86400)
        self.training_lock = threading.Lock()
        self.dashboard_cache = {}
        self.cache_lock = threading.Lock()

    def drug_names(self, params):
        """Search the FDA NDC name directory, independently of the loaded cohort."""
        query = str(params.get("q", "")).strip()
        if len(query) > 80 or not re.fullmatch(r"[\w\s.+'(),/\-]*", query):
            raise APIError("Use a drug name or prefix of 80 characters or fewer, without query operators.")
        tokens = re.findall(r"\w+", query.lower())
        search = " AND ".join(f"(brand_name:{token}* OR generic_name:{token}*)" for token in tokens)
        names, failures = {}, []
        fields = {"generic_name.exact": "Generic", "brand_name.exact": "Brand"}
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = {pool.submit(self.drug_client.request, {**({"search": search} if search else {}), "count": field, "limit": 1000}): kind for field, kind in fields.items()}
            for future in as_completed(jobs):
                kind = jobs[future]
                try:
                    rows = future.result().get("results", [])
                except APIError as exc:
                    failures.append(str(exc))
                    continue
                for row in rows:
                    name = str(row.get("term", "")).strip().upper()
                    words = re.findall(r"\w+", name.lower())
                    if not name or len(name) > 120 or not re.fullmatch(r"[\w\s.+'(),/\-]+", name):
                        continue
                    if any(not any(word.startswith(token) for word in words) for token in tokens):
                        continue
                    current = names.setdefault(name, {"name": name, "kinds": set(), "rank": 0})
                    current["kinds"].add(kind)
                    current["rank"] = max(current["rank"], int(row.get("count", 0)))
        if len(failures) == 2:
            raise APIError("FDA drug-name suggestions are unavailable. You can still enter a drug name manually.", 503)
        ordered = sorted(names.values(), key=lambda row: (not row["name"].startswith(query.upper()), -row["rank"], row["name"]))
        return {"drugs": [{"name": row["name"], "kind": " / ".join(sorted(row["kinds"]))} for row in ordered],
                "source": "FDA NDC directory", "query": query, "partial": bool(failures),
                "notice": "Search brand and generic names across the FDA NDC directory. Listings do not imply FDA approval. Browse results are bounded; type to search more specifically."}

    def review_path(self):
        paths = [self.root / "data" / "bronze" / "reviews.csv", self.root / "data" / "reviews.csv", self.root / "reviews.csv"]
        return next((path for path in paths if path.is_file()), None)

    @freshness.tracked
    def reaction_reports(self, raw_params):
        params = validate_params(raw_params, self.defaults())
        reaction = raw_params.get("reaction", "")
        if not isinstance(reaction, str) or not reaction.strip() or len(reaction) > 200 or any(ord(c) < 32 for c in reaction):
            raise APIError("Choose a reaction term of 200 characters or fewer.")
        reaction = reaction.strip().upper()
        if params["mode"] == "reference":
            records = self.dashboard(params)["narratives"]["records"]
            matched = [row for row in records if reaction in {str(term).upper() for term in row.get("reaction_terms", [])}]
            return {"records": matched, "total": len(matched), "reaction": reaction, "notice": "Synthetic archive records matching the exact extracted reaction term. These are not FAERS case reports."}
        # Quote the complete term; saved focus is text, never an FDA query fragment.
        escaped = reaction.replace('\\', '\\\\').replace('"', '\\"')
        query = search_query(params, flag=f'patient.reaction.reactionmeddrapt.exact:"{escaped}"')
        total = self.client.count(query)
        sample = self.fetch_report_sample(query, 20, "receivedate:desc", page_size=20,
            transform=lambda report: flatten_report(report, params["drug"])) if total else {"records": [], "skipped_oversized": 0}
        return {"records": sample["records"], "total": total, "reaction": reaction,
                "skipped_oversized": sample["skipped_oversized"],
                "notice": "Latest matching FDA report sample, up to 20 reports. The reaction filter applies to this sample query; cohort charts and signal denominators remain unchanged."}

    @freshness.tracked
    def period_changes(self, raw_params):
        current = validate_params(raw_params, self.defaults())
        try:
            periods = validate_periods({key: raw_params.get(key) for key in ("baseline_start", "baseline_end")}, current)
        except ValueError as exc:
            raise APIError(str(exc)) from None
        baseline = {**current, "start": periods["baseline_start"], "end": periods["baseline_end"]}
        if current["mode"] == "reference" and (current["age"] != "All" or current["sex"] or current["reporters"]):
            raise APIError("The synthetic archive has no patient or reporter filters.", 422)
        if current["mode"] == "reference" and self.review_path() is None:
            raise APIError("The synthetic archive is unavailable. Restore the review file before comparing periods.", 503)

        def collect(params):
            if params["mode"] == "reference":
                selected = [row for row in self.reviews() if params["start"] <= row["created_at"][:10] <= params["end"] and canonical_drug(row.get("drug", row.get("drug_raw"))) == canonical_drug(params["drug"])]
                counts = Counter(term.upper() for row in selected for term in reaction_mentions(row["review_text"]))
                return {"total": len(selected), "counts": counts, "complete": True}
            query = search_query(params)
            total = self.client.count(query)
            if not total:
                return {"total": 0, "counts": {}, "complete": True}
            rows = self.client.aggregate(query, "patient.reaction.reactionmeddrapt.exact", 1000)
            counts = {}
            for row in rows:
                term, count = row.get("term"), row.get("count")
                if not isinstance(term, str) or not term.strip() or type(count) is not int or not 0 <= count <= total:
                    raise APIError("FDA returned inconsistent reaction counts. Reload the comparison to try again.", 502)
                counts[term.upper()] = count
            return {"total": total, "counts": counts, "complete": len(rows) < 1000}

        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = [pool.submit(copy_context().run, collect, params) for params in (baseline, current)]
            before, after = [job.result() for job in jobs]
        candidates = sorted(set(term for group in (before, after) for term, _ in Counter(group["counts"]).most_common(50)))
        warnings = []
        missing = [(group, params, term) for group, params in ((before, baseline), (after, current)) for term in candidates if term not in group["counts"] and not group["complete"]]
        # Absence from a capped aggregate is unknown, never an assumed zero.
        def exact_count(params, term):
            escaped = term.replace('\\', '\\\\').replace('"', '\\"')
            return self.client.count(search_query(params, flag=f'patient.reaction.reactionmeddrapt.exact:"{escaped}"'))
        with ThreadPoolExecutor(max_workers=4) as pool:
            jobs = {pool.submit(copy_context().run, exact_count, params, term): (group, term) for group, params, term in missing}
            for job in as_completed(jobs):
                group, term = jobs[job]
                try:
                    count = job.result()
                    if type(count) is not int or not 0 <= count <= group["total"]:
                        raise APIError("Inconsistent FDA count.", 502)
                    group["counts"][term] = count
                except APIError:
                    group["counts"][term] = None
                    warnings.append(f"An exact period count for {term} was unavailable; its change is unknown.")
        rows = [change_row(term, before["counts"].get(term, 0), after["counts"].get(term, 0), before["total"], after["total"]) for term in candidates]
        rows.sort(key=lambda row: (row["share_delta_pp"] is None, -abs(row["share_delta_pp"] or 0), row["reaction"]))
        def describe(params, group):
            return {"start": params["start"], "end": params["end"], "days": (date_value(params["end"], "end")-date_value(params["start"], "start")).days+1, "total_reports": group["total"]}
        return {"meta": {"source": "Synthetic review archive · local" if current["mode"] == "reference" else "openFDA · FAERS live", "drug": current["drug"], "generated_at": utc_now(), "partial": bool(warnings), "warnings": warnings,
                          "coverage": "Union of the 50 most reported reactions in each period; not an exhaustive reaction list.",
                          "method": "Reporting-share difference (current minus baseline), percentage points. Unadjusted 95% Newcombe–Wilson intervals; exploratory, without correction for multiple comparisons. Reporting bias, duplicates, and dependence between reports are not captured."},
                "periods": {"baseline": describe(baseline, before), "current": describe(current, after)}, "rows": rows}

    def reviews(self):
        path = self.review_path()
        if not path:
            return []
        with path.open(encoding="utf-8-sig", newline="") as source:
            return [row for row in csv.DictReader(source) if row.get("created_at") and row.get("review_text")]

    def defaults(self):
        dates = sorted(row["created_at"][:10] for row in self.reviews())
        return {"start": dates[0], "end": dates[-1]} if dates else {"start": "2024-01-01", "end": dt.date.today().isoformat()}

    def base(self, params):
        reference = params["mode"] == "reference"
        return {
            "meta": {**params, "source": "Synthetic review archive · local" if reference else "openFDA · FAERS live",
                     "workspace_location": self.workspace_location,
                     "status": "ok", "generated_at": utc_now(), "warnings": [],
                     "comparison": {"drug": params["compare"], "status": "unavailable" if params["compare"] else "not_requested",
                                    "total_available": False, "timeseries_available": False, "reactions_available": False,
                                    "reactions_truncated": False},
                     "notice": "Supplied synthetic reviews generated by the original ingestion pipeline. Counts and associations describe this demonstration corpus; they are not FAERS reports or clinical evidence." if reference else "Spontaneous adverse-event reports describe reporting patterns, not incidence or causation. A report may mention multiple drugs and reactions.",
                     "record_label": "reviews" if reference else "reports", "partial_latest_week": dt.date.fromisoformat(params["end"]).weekday() != 6,
                     "partial_first_week": dt.date.fromisoformat(params["start"]).weekday() != 0,
                     "signal_method": "PRR ≥ 2, χ² ≥ 4, and at least 3 reports; 95% log-Wald confidence intervals. Zero cells receive a 0.5 correction.",
                     "burst_method": "Current week compared with up to 8 preceding weeks (at least 5); current week excluded from baseline."},
            "filters": {"drugs": [], "available_start": params["start"], "available_end": params["end"]},
            "summary": {"total_reports": 0, "compare_total": None, "latest_week": 0, "previous_week": 0, "weeks": 0, "signal_count": 0, "serious_reports": None},
            "timeseries": [], "reactions": [], "signals": [], "reports": [],
            "severity": {"outcomes": [], "demographics": [], "reactions": []},
            "graph": {"nodes": [], "links": []}, "narratives": narratives_result([], "No narratives loaded."), "model": model_overview(),
        }

    @staticmethod
    def finish(result):
        series = result["timeseries"]
        result["summary"].update({"latest_week": series[-1]["count"] if series else 0,
                                   "previous_week": series[-2]["count"] if len(series) > 1 else 0,
                                   "weeks": len(series), "signal_count": sum(row["signal"] for row in result["signals"])})
        if result["summary"]["total_reports"] == 0:
            result["meta"]["status"] = "empty"
        return result

    def dashboard_section(self, raw_params):
        section = raw_params.get("section", "core")
        if section not in {"core", "signals", "reports", "severity", "comparison"}:
            raise APIError("Choose a valid dashboard section.")
        params = validate_params(raw_params, self.defaults())
        with freshness.capture() as trace:
            result = self.dashboard(params) if params["mode"] == "reference" else self.live(params, section)
        meta = result["meta"]
        basis = meta.get("basis") or hashlib.sha256(json.dumps([result["summary"]["total_reports"], result["reactions"]], sort_keys=True).encode()).hexdigest()
        provenance = ({"source": "local", "retrieved_at": meta["generated_at"], "cached": bool(meta.get("cached"))}
                      if params["mode"] == "reference" else freshness.describe(trace))
        failures = meta.get("failures", {})
        if section == "core":
            patch = result
            # Counts of screening flags are unknown until the signal section loads.
            if params["mode"] == "live":
                patch["summary"]["signal_count"] = None
        elif section == "signals":
            patch = {"signals": result["signals"], "summary": {"signal_count": result["summary"]["signal_count"]}}
        elif section == "severity":
            patch = {"severity": result["severity"], "summary": {"serious_reports": result["summary"]["serious_reports"]}}
        elif section == "reports":
            patch = {"reports": result["reports"], "reports_notice": result.get("reports_notice", "")}
        else:
            patch = {"comparison_reactions": result["reactions"], "comparison_graph": result["graph"],
                     "comparison_timeseries": result["timeseries"], "summary": {"compare_total": result["summary"]["compare_total"]},
                     "comparison": meta["comparison"]}
        fatal = bool(failures) and (section in {"signals", "reports"} or
                    section == "comparison" and meta["comparison"]["status"] == "unavailable")
        return {"section": section, "cohort": params, "basis": basis, "data": patch,
                "generated_at": utc_now(), "freshness": provenance,
                "status": "error" if fatal else "partial" if failures else "ready",
                "errors": list(failures.values()), "warnings": meta["warnings"]}

    @freshness.tracked
    def dashboard(self, raw_params):
        params = validate_params(raw_params, self.defaults())
        key = json.dumps(params, sort_keys=True)
        # Live response freshness belongs to the individual FDA calls. Caching
        # the assembled dashboard again could extend an almost-expired result.
        memoize = params["mode"] == "reference"
        with self.cache_lock:
            cached = self.dashboard_cache.get(key) if memoize else None
            if cached and time.monotonic() - cached[0] < 300:
                result = copy.deepcopy(cached[1])
                result["meta"]["cached"] = True
                return result
        result = self.reference(params) if params["mode"] == "reference" else self.live(params)
        if memoize:
            with self.cache_lock:
                if len(self.dashboard_cache) >= 40:
                    self.dashboard_cache.pop(next(iter(self.dashboard_cache)))
                self.dashboard_cache[key] = (time.monotonic(), copy.deepcopy(result))
        return result

    def reference(self, params):
        result = self.base(params)
        all_rows = self.reviews()
        if not all_rows:
            raise APIError("The local review archive is missing. Restore data/bronze/reviews.csv or choose Live FAERS.", 503)
        all_dates = sorted(row["created_at"][:10] for row in all_rows)
        result["filters"] = {"drugs": sorted({canonical_drug(row.get("drug", row.get("drug_raw"))) for row in all_rows}),
                             "available_start": all_dates[0], "available_end": all_dates[-1]}
        window = [row for row in all_rows if params["start"] <= row["created_at"][:10] <= params["end"]]
        selected = [row for row in window if canonical_drug(row.get("drug", row.get("drug_raw"))) == canonical_drug(params["drug"])]
        compared = [row for row in window if params["compare"] and canonical_drug(row.get("drug", row.get("drug_raw"))) == canonical_drug(params["compare"])]
        if params["age"] != "All" or params["sex"] or params["reporters"]:
            raise APIError("The synthetic archive has no patient demographics or reporter fields. Choose Live FAERS to apply cohort filters.", 422)
        counts = Counter(rx for row in selected for rx in reaction_mentions(row["review_text"]))
        background = Counter(rx for row in window for rx in reaction_mentions(row["review_text"]))
        other_counts = Counter(rx for row in compared for rx in reaction_mentions(row["review_text"]))
        result["summary"]["total_reports"] = len(selected)
        result["summary"]["compare_total"] = len(compared) if params["compare"] else None
        if params["compare"]:
            result["meta"]["comparison"].update({"status": "complete", "total_available": True, "timeseries_available": True, "reactions_available": True})
        compare_rows = [{"date": row["created_at"][:10]} for row in compared] if params["compare"] else None
        result["timeseries"] = weekly_series([{"date": row["created_at"][:10]} for row in selected], params["start"], params["end"], compare_rows)
        reaction_order = counts.most_common(50) if selected else [(rx, 0) for rx, _ in other_counts.most_common(50)]
        result["reactions"] = [{"reaction": rx, "reports": count, "compare_reports": other_counts[rx] if params["compare"] else None} for rx, count in reaction_order]
        result["signals"] = score_signals(result["reactions"], len(selected), background, len(window))
        graph_drugs = {params["drug"]: counts}
        if params["compare"]:
            graph_drugs[params["compare"]] = other_counts
        result["graph"] = graph_result(graph_drugs, result["signals"])
        result["severity"]["notice"] = "The supplied synthetic reviews contain neither seriousness labels nor patient demographics. These charts populate from real FAERS records in Live mode."
        result["reports_notice"] = "FAERS report samples are available in Live mode. The local archive contains synthetic reviews shown in Narratives."
        records = [{"id": row.get("review_id"), "date": row["created_at"][:10], "drug": canonical_drug(row.get("drug")), "reaction_terms": sorted(reaction_mentions(row["review_text"])), "text": row["review_text"], "rating": int(row.get("rating") or 0), "source": "synthetic review"} for row in selected]
        result["narratives"] = narratives_result(records, "Synthetic review text from the supplied local archive, not FAERS case narratives.")
        return self.finish(result)

    def live(self, params, section=None):
        result = self.base(params)
        query, background_query = search_query(params), search_query(params, drug=False)
        # Core queries fail together. A network outage is never presented as a
        # successful empty result or silently switched to the synthetic archive.
        core = {"total": lambda: self.client.count(query),
                "timeseries": lambda: self.daily_counts(params),
                "reactions": lambda: self.client.aggregate(query, "patient.reaction.reactionmeddrapt.exact", 50)}
        if section and section != "core":
            core.pop("timeseries")
        core_values = self.parallel(core, result, required=True)
        result["meta"]["basis"] = hashlib.sha256(json.dumps([core_values["total"], core_values["reactions"]], sort_keys=True).encode()).hexdigest()
        result["summary"]["total_reports"] = core_values["total"]
        result["reactions"] = [{"reaction": row["term"], "reports": int(row["count"]), "compare_reports": None} for row in core_values["reactions"]]
        daily = [{"date": date_value(row["time"], "receivedate").isoformat(), "count": row["count"]} for row in core_values.get("timeseries", [])]
        facets = {} if not core_values["total"] else {
            "background_total": lambda: self.client.count(background_query),
            "background_reactions": lambda: self.client.aggregate(background_query, "patient.reaction.reactionmeddrapt.exact"),
            "serious": lambda: self.client.count(query + " AND serious:1"),
            "reports": lambda: self.fetch_report_sample(query, 20, "receivedate:desc", page_size=20,
                                                        transform=lambda report: flatten_report(report, params["drug"])),
            "sex": lambda: self.client.aggregate(query, "patient.patientsex"),
            "age": lambda: self.client.aggregate(query, "patient.patientagegroup"),
            "reporters": lambda: self.client.aggregate(query, "primarysource.qualification"),
            "serious_rx": lambda: self.client.aggregate(query + " AND serious:1", "patient.reaction.reactionmeddrapt.exact"),
            "background_serious_rx": lambda: self.client.aggregate(background_query + " AND serious:1", "patient.reaction.reactionmeddrapt.exact"),
        }
        if core_values["total"]:
            for label, field in OUTCOMES.items():
                facets["outcome:" + label] = lambda field=field: self.client.count(query + f" AND {field}:1")
        if params["compare"]:
            other_params = {**params, "drug": params["compare"]}
            other_query = search_query(other_params)
            facets["compare_series"] = lambda: self.daily_counts(other_params)
            facets["compare_rx"] = lambda: self.client.aggregate(other_query, "patient.reaction.reactionmeddrapt.exact", 1000)
            facets["compare_total"] = lambda: self.client.count(other_query)
        if section:
            groups = {"core": set(), "signals": {"background_total", "background_reactions"},
                      "reports": {"reports"}, "comparison": {"compare_series", "compare_rx", "compare_total"},
                      "severity": {"background_total", "background_reactions", "serious", "sex", "age", "reporters", "serious_rx", "background_serious_rx", *["outcome:" + label for label in OUTCOMES]}}
            facets = {key: task for key, task in facets.items() if key in groups[section]}
        values = self.parallel(facets, result)
        result["filters"]["drugs"] = sorted(set([params["drug"], params["compare"], "METFORMIN", "IBUPROFEN", "ACETAMINOPHEN", "SEMAGLUTIDE", "ATORVASTATIN"]) - {""})
        if params["compare"]:
            availability = {"total_available": "compare_total" in values, "timeseries_available": "compare_series" in values,
                            "reactions_available": "compare_rx" in values}
            available_count = sum(availability.values())
            result["meta"]["comparison"].update({**availability, "status": "complete" if available_count == 3 else "partial" if available_count else "unavailable",
                                                 "reactions_truncated": len(values.get("compare_rx", [])) >= 1000})
        compare_daily = ([{"date": date_value(row["time"], "receivedate").isoformat(), "count": row["count"]} for row in values["compare_series"]]
                         if "compare_series" in values else None)
        result["timeseries"] = weekly_series(daily, params["start"], params["end"], compare_daily)
        result["summary"]["serious_reports"] = values.get("serious")
        result["summary"]["compare_total"] = values.get("compare_total")
        other_counts = {str(row["term"]).upper(): int(row["count"]) for row in values.get("compare_rx", [])}
        if not core_values["total"]:
            # A successful zero subject count makes these subject-side zeros
            # known, even when the comparator has reports and reactions.
            result["reactions"] = [{"reaction": reaction, "reports": 0, "compare_reports": count}
                                   for reaction, count in sorted(other_counts.items(), key=lambda item: item[1], reverse=True)[:50]]
        for row in result["reactions"]:
            row["compare_reports"] = (other_counts.get(row["reaction"].upper(), None if len(other_counts) >= 1000 else 0)
                                      if "compare_rx" in values else None)
        if params["compare"] and any(row["compare_reports"] is None for row in result["reactions"]) and len(other_counts) >= 1000:
            result["meta"]["comparison"]["status"] = "partial"
            result["meta"]["warnings"].append("Some comparison reactions were absent from openFDA's top-1000 aggregate; their comparison counts are unavailable, not zero.")
        if not core_values["total"]:
            graph_drugs = {params["drug"]: Counter()}
            if "compare_rx" in values:
                graph_drugs[params["compare"]] = Counter(other_counts)
            result["graph"] = graph_result(graph_drugs)
            result["narratives"]["notice"] = "openFDA does not supply free-text FAERS narratives. Paste or upload your own authorized text to analyze it."
            return self.finish(result)
        if "background_total" in values and "background_reactions" in values:
            background_counts = {str(row["term"]).upper(): int(row["count"]) for row in values["background_reactions"]}
            # Terms absent from top-1000 background counts are unknown, not zero.
            scored = [row for row in result["reactions"] if row["reaction"].upper() in background_counts]
            result["signals"] = score_signals(scored, core_values["total"], background_counts, values["background_total"])
            if len(scored) < len(result["reactions"]):
                result["meta"]["warnings"].append("Some reactions were absent from openFDA's top-1000 background aggregates and were excluded from signal estimates.")
            if "serious_rx" in values and "background_serious_rx" in values:
                serious_counts = {str(row["term"]).upper(): int(row["count"]) for row in values["serious_rx"]}
                bg_serious_counts = {str(row["term"]).upper(): int(row["count"]) for row in values["background_serious_rx"]}
                for row in scored:
                    reaction = row["reaction"].upper()
                    if ((len(values["serious_rx"]) >= 1000 and reaction not in serious_counts) or
                            (len(values["background_serious_rx"]) >= 1000 and reaction not in bg_serious_counts)):
                        # An absent term in a truncated aggregate is unknown.
                        continue
                    # These are counts within the same reaction, not all reports.
                    comparison = association(row["reaction"], serious_counts.get(reaction, 0), row["reports"], bg_serious_counts.get(reaction, 0), background_counts[reaction])
                    if comparison:
                        result["severity"]["reactions"].append({"reaction": row["reaction"], "reports": row["reports"],
                            "serious": serious_counts.get(reaction, 0), "rate_drug": serious_counts.get(reaction, 0) / max(1, row["reports"]),
                            "rate_bg": comparison["c"] / max(1, comparison["c"] + comparison["d"]),
                            "RR": comparison["prr"], "RR_low": comparison["prr_low"], "RR_high": comparison["prr_high"]})
        report_sample = values.get("reports", {"records": [], "skipped_oversized": 0})
        result["reports"] = report_sample["records"]
        result["meta"]["skipped_oversized_reports"] = report_sample["skipped_oversized"]
        result["reports_notice"] = "Up to 20 latest matching reports. This sample is not the complete cohort. Receipt date and all cohort filters apply."
        if report_sample["skipped_oversized"]:
            note = (f"{report_sample['skipped_oversized']} matching report(s) exceeded the local per-response size limit "
                    "and were omitted from this displayed sample. Aggregate counts still include all matching reports.")
            result["reports_notice"] += " " + note
            result["meta"]["warnings"].append(note)
        result["severity"]["outcomes"] = [{"label": label, "count": values["outcome:" + label]} for label in OUTCOMES if "outcome:" + label in values]
        result["severity"]["notice"] = "Seriousness outcomes may overlap. Demographic counts omit reports where the corresponding field was not recorded."
        for name, mapping in [("sex", {v: k for k, v in SEX_CODES.items()}), ("age", {"1": "Neonate", "2": "Infant", "3": "Child", "4": "Adolescent", "5": "Adult", "6": "Elderly"}), ("reporters", {v: k for k, v in REPORTER_CODES.items()})]:
            result["severity"]["demographics"].extend({"group": name, "label": mapping.get(str(row["term"]), str(row["term"])), "count": row["count"]} for row in values.get(name, []))
        graph_drugs = {params["drug"]: Counter({row["reaction"]: row["reports"] for row in result["reactions"]})}
        if "compare_rx" in values:
            graph_drugs[params["compare"]] = Counter(other_counts)
        result["graph"] = graph_result(graph_drugs, result["signals"])
        result["narratives"]["notice"] = "openFDA does not supply free-text FAERS case narratives. Analyze your own authorized text below. Reaction terms and report summaries are not narratives."
        if result["meta"]["warnings"]:
            result["meta"]["status"] = "partial"
        return self.finish(result)

    def daily_counts(self, params):
        # Date count responses have a 1,000-bucket limit. Partitioning the date
        # window prevents a long range from silently losing less common days.
        current, end = date_value(params["start"], "start"), date_value(params["end"], "end")
        rows = []
        while current <= end:
            chunk_end = min(end, current + dt.timedelta(days=899))
            chunk_params = {**params, "start": current.isoformat(), "end": chunk_end.isoformat()}
            rows.extend(self.client.aggregate(search_query(chunk_params), "receivedate"))
            current = chunk_end + dt.timedelta(days=1)
        return rows

    def fetch_report_sample(self, query, requested, sort, page_size=25, transform=None):
        """Fetch a bounded real sample, adapting around unusually large reports.

        Offset always advances by actual records received (or one explicitly
        omitted oversized record). The cap counts scanned source positions;
        omitted records are never replaced by a made-up or synthetic record.
        Flattening each successful page avoids retaining large raw drug lists.
        """
        offset, skipped, reduced = 0, 0, False
        batch_size = page_size
        records = []
        while offset < requested:
            limit = min(batch_size, requested - offset)
            try:
                reports = self.client.request({"search": query, "limit": limit, "skip": offset, "sort": sort}).get("results", [])
            except APIError as exc:
                if exc.code != "response_too_large" and "response was too large" not in str(exc).lower():
                    raise
                reduced = True
                if limit > 5:
                    batch_size = 5
                elif limit > 1:
                    batch_size = 1
                else:
                    # Even a single response would exceed the hard memory cap.
                    # Advance exactly one source position, recording the omission.
                    skipped += 1
                    offset += 1
                    batch_size = min(5, page_size)
                continue
            for report in reports:
                if isinstance(report, dict):
                    row = transform(report) if transform else report
                    if row is not None:
                        records.append(row)
            offset += len(reports)
            if len(reports) < limit:
                break
            if batch_size == 1:
                batch_size = min(5, page_size)
        return {"records": records, "skipped_oversized": skipped, "adaptive_paging": reduced, "scanned_positions": offset}

    def fetch_device_narratives(self, body):
        params = validate_params({**body, "drug": body.get("term") or "DEVICE", "mode": "live"}, self.defaults())
        limit = integer(body.get("limit"), 100, 1, 1000)
        query = f"date_received:[{params['start'].replace('-', '')} TO {params['end'].replace('-', '')}]"
        if body.get("term"):
            query += f' AND (device.generic_name:"{params["drug"]}" OR device.brand_name:"{params["drug"]}")'
        payload = self.device_client.request({"search": query, "limit": limit, "sort": "date_received:desc"})
        records = []
        for report in payload.get("results", []):
            texts = [str(item.get("text", "")).strip() for item in report.get("mdr_text", []) if isinstance(item, dict) and item.get("text")]
            if texts:
                records.append({"id": str(report.get("mdr_report_key", "")), "date": report.get("date_received"),
                                "text": "\n\n".join(texts), "source": "FDA MAUDE device event", "event_type": report.get("event_type")})
        result = narratives_result(records, "Real FDA MAUDE medical-device event narratives via openFDA. Device reports are separate from the FAERS drug cohort.")
        result["source"] = "openFDA · MAUDE device/event"
        result["query"] = {"term": body.get("term", ""), "start": params["start"], "end": params["end"], "limit": limit}
        return result

    @staticmethod
    def parallel(functions, result, required=False):
        values = {}
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {pool.submit(copy_context().run, function): key for key, function in functions.items()}
            for future in as_completed(futures):
                key = futures[future]
                try:
                    values[key] = future.result()
                except APIError as exc:
                    if required:
                        raise
                    result["meta"].setdefault("failures", {})[key] = str(exc)
                    result["meta"]["warnings"].append(f"{key.replace('_', ' ')} unavailable: {exc}")
        return values

    def train(self, raw_params):
        params = validate_params(raw_params, self.defaults())
        if params["mode"] != "live":
            raise APIError("Seriousness training requires real FAERS records. Switch to Live mode; the synthetic review archive has no seriousness target.", 422)
        max_records = integer(raw_params.get("max_records"), 1000, 200, 5000)
        try:
            import pandas as pd
            if str(ROOT / "app") not in sys.path:
                sys.path.insert(0, str(ROOT / "app"))
            import serious_outcome
            import xgboost  # noqa: F401 -- check before expensive network work
        except ImportError:
            raise APIError("Model training dependencies are missing. Install requirements.txt (scikit-learn and XGBoost) in the Python environment running this server.", 503) from None
        if not self.training_lock.acquire(blocking=False):
            raise APIError("A model training run is already in progress. Wait for it to finish.", 409)
        try:
            start, end = date_value(params["start"], "start"), date_value(params["end"], "end")
            span = (end - start).days + 1
            buckets = min(10, span)
            rows, oversized_reports, adaptive_buckets = [], 0, 0
            def fetch_bucket(bucket):
                bucket_params = {**params, "start": (start + dt.timedelta(days=span * bucket // buckets)).isoformat(),
                                 "end": (start + dt.timedelta(days=span * (bucket + 1) // buckets - 1)).isoformat()}
                allocation = max_records // buckets + (bucket < max_records % buckets)
                return self.fetch_report_sample(search_query(bucket_params), allocation, "receivedate:asc",
                                                transform=lambda report: training_row(report, params["drug"]))
            with ThreadPoolExecutor(max_workers=3) as pool:
                for bucket_sample in pool.map(fetch_bucket, range(buckets)):
                    rows.extend(bucket_sample["records"])
                    oversized_reports += bucket_sample["skipped_oversized"]
                    adaptive_buckets += int(bucket_sample["adaptive_paging"])
            frame = pd.DataFrame(rows)
            if frame.empty:
                message = "No matching reports with a valid seriousness label were returned. Broaden the cohort."
                if oversized_reports:
                    message += f" {oversized_reports} real report(s) exceeded the per-response size limit even when fetched individually and were omitted."
                raise APIError(message, 422)
            frame["receivedate"] = pd.to_datetime(frame["receivedate"], format="%Y%m%d", errors="coerce")
            dropped_missing_dates = int(frame["receivedate"].isna().sum())
            frame = frame.dropna(subset=["receivedate"])
            # Keep the highest available version of each report before splitting,
            # so an earlier version cannot cross from train into test.
            before_deduplication = len(frame)
            frame = frame.sort_values(["_report_version", "receivedate"]).drop_duplicates("safetyreportid", keep="last")
            deduplicated_count = before_deduplication - len(frame)
            frame = frame.sort_values("receivedate").reset_index(drop=True)
            try:
                trained = serious_outcome.train_seriousness_models(frame)
            except ValueError as exc:
                message = str(exc)
                if oversized_reports:
                    message += f" {oversized_reports} oversized real report(s) were omitted from this sample after single-record retries."
                raise APIError(message, 422) from None
            evaluation = {key: value for key, value in trained.items() if key not in {"models", "feature_sets"}}
            evaluation["feature_sets"] = {name: {key: value for key, value in feature_set.items() if key != "models"} for name, feature_set in trained["feature_sets"].items()}
            notice = "Classifies the seriousness label on submitted reports, not a patient's clinical risk. Full/reduced models share the same held-out split. Sampling is capped across temporal buckets; no model pickle is loaded or saved."
            warnings = []
            if oversized_reports:
                warnings.append(f"{oversized_reports} oversized real report(s) were excluded from the training sample after single-record retries. This omission can affect the sample's representativeness.")
                notice += " " + warnings[-1]
            return json_safe({"status": "trained", "source": "openFDA report-level temporal sample", "generated_at": utc_now(),
                              "cohort": params, "sample_size": len(frame), "requested_records": max_records,
                              "deduplicated_reports": deduplicated_count, "dropped_missing_dates": dropped_missing_dates,
                              "dropped_oversized_reports": oversized_reports, "adaptive_paging_buckets": adaptive_buckets, "warnings": warnings,
                              "audit": model_overview()["audit"], "exclusions": model_overview()["exclusions"],
                              "notice": notice,
                              "evaluation": evaluation})
        finally:
            self.training_lock.release()


def age_in_years(value, unit):
    try:
        age = float(value)
    except (ValueError, TypeError):
        return None
    factor = {"800": 10, "801": 1, "802": 1 / 12, "803": 1 / 52, "804": 1 / 365.25, "805": 1 / (365.25 * 24)}.get(str(unit))
    return age * factor if age >= 0 and factor is not None else None


def subject_drug(drugs, drug_name):
    return next((row for row in drugs if drug_name.casefold() in str(row.get("medicinalproduct", "")).casefold()), next(iter(drugs), {}))


def flatten_report(report, drug_name):
    patient = report.get("patient") or {}
    drugs = [row for row in patient.get("drug", []) if isinstance(row, dict)]
    subject = subject_drug(drugs, drug_name)
    received = str(report.get("receivedate", ""))
    return {"safetyreportid": str(report.get("safetyreportid", "")),
            "receivedate": f"{received[:4]}-{received[4:6]}-{received[6:8]}" if len(received) == 8 else received,
            "drug_name": subject.get("medicinalproduct", drug_name),
            "drugs": [row.get("medicinalproduct", "") for row in drugs],
            "reactions": ", ".join(row.get("reactionmeddrapt", "") for row in patient.get("reaction", []) if isinstance(row, dict)),
            "reaction_terms": [str(row["reactionmeddrapt"]) for row in patient.get("reaction", []) if isinstance(row, dict) and row.get("reactionmeddrapt")],
            "sex": {v: k for k, v in SEX_CODES.items()}.get(str(patient.get("patientsex")), "Not recorded"),
            "age": age_in_years(patient.get("patientonsetage"), patient.get("patientonsetageunit")),
            "serious": str(report.get("serious")) == "1" if str(report.get("serious")) in {"1", "2"} else None,
            "reporteroccupation": {v: k for k, v in REPORTER_CODES.items()}.get(str((report.get("primarysource") or {}).get("qualification")), "Not recorded"),
            "country": report.get("occurcountry") or report.get("primarysourcecountry") or "Not recorded"}


def training_row(report, drug_name):
    if str(report.get("serious")) not in {"1", "2"} or not report.get("safetyreportid"):
        return None
    patient = report.get("patient") or {}
    source = report.get("primarysource") or {}
    drugs = [row for row in patient.get("drug", []) if isinstance(row, dict)]
    reactions = patient.get("reaction") or []
    subject = subject_drug(drugs, drug_name)
    roles = Counter(str(row.get("drugcharacterization")) for row in drugs)
    try:
        weight = float(patient.get("patientweight"))
    except (ValueError, TypeError):
        weight = None
    try:
        version = int(report.get("safetyreportversion", 0))
    except (ValueError, TypeError):
        version = 0
    return {"safetyreportid": report["safetyreportid"], "receivedate": report.get("receivedate"), "serious": int(str(report["serious"]) == "1"),
            "_report_version": version,
            "patient_age_years": age_in_years(patient.get("patientonsetage"), patient.get("patientonsetageunit")), "patient_weight_kg": weight,
            "patient_sex": patient.get("patientsex"), "reporter_qualification": source.get("qualification"), "reporter_country": source.get("reportercountry"),
            "primary_source_country": report.get("primarysourcecountry"), "occurrence_country": report.get("occurcountry"), "report_type": report.get("reporttype"),
            "drug_count": len(drugs), "reaction_count": len(reactions), "primary_suspect_drug_count": roles["1"], "concomitant_drug_count": roles["2"],
            "interacting_drug_count": roles["3"], "subject_drug_role": subject.get("drugcharacterization"), "subject_drug_route": subject.get("drugadministrationroute")}


def json_safe(value):
    """Encode numpy/pandas evaluation objects, excluding non-JSON estimators."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_safe(item) for item in value]
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    if hasattr(value, "to_dict"):
        try:
            return json_safe(value.to_dict(orient="records"))
        except TypeError:
            return json_safe(value.to_dict())
    if hasattr(value, "tolist"):
        return json_safe(value.tolist())
    if hasattr(value, "item"):
        return json_safe(value.item())
    raise TypeError(f"Unsupported JSON type: {type(value).__name__}")


def csv_response(rows):
    output = io.StringIO(newline="")
    if not rows:
        return "No matching records\r\n"
    fields = list(dict.fromkeys(key for row in rows for key in row))
    writer = csv.DictWriter(output, fields)
    writer.writeheader()
    for row in rows:
        safe = {}
        for key, value in row.items():
            if isinstance(value, (list, dict)):
                value = json.dumps(value, ensure_ascii=False)
            # Prevent formula evaluation if a report string is opened in Excel.
            if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
                value = "'" + value
            safe[key] = value
        writer.writerow(safe)
    return output.getvalue()


class DashboardRoutes:
    """Shared routes; local HTTP and hosted WSGI transports use the same methods."""
    server_version = "SignalMonitor/2.0"
    service = DashboardService()
    static_dir = ROOT / "dist"

    def log_message(self, fmt, *args):
        # Route only: query strings may contain the user's research cohort.
        print(f"[{utc_now()}] {self.command} {urlsplit(self.path).path}", file=sys.stderr)

    def allowed(self):
        host = self.headers.get("Host", "").split(":")[0]
        if host not in {"localhost", "127.0.0.1"}:
            raise APIError("This server accepts local requests only.", 403)
        origin = self.headers.get("Origin")
        if origin:
            parsed = urlsplit(origin)
            if parsed.hostname not in {"localhost", "127.0.0.1"} or parsed.scheme != "http":
                raise APIError("Cross-site requests are not allowed.", 403)

    def send_bytes(self, data, content_type, status=200, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cache-Control", "no-store" if content_type.startswith("application/json") else "no-cache")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def send_json(self, value, status=200):
        self.send_bytes(json.dumps(json_safe(value), ensure_ascii=False, allow_nan=False).encode("utf-8"), "application/json; charset=utf-8", status)

    def do_GET(self):
        try:
            self.allowed()
            parsed = urlsplit(self.path)
            params = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
            if parsed.path == "/api/health":
                return self.send_json({"status": "ok", "service": "Side Effects Signal Monitor", "reference_available": self.service.review_path() is not None,
                                       "api_key_configured": bool(api_key()), "generated_at": utc_now(), "cache": self.service.response_cache.stats()})
            if parsed.path == "/api/dashboard":
                return self.send_json(self.service.dashboard(params))
            if parsed.path == "/api/dashboard/section":
                return self.send_json(self.service.dashboard_section(params))
            if parsed.path == "/api/drugs":
                return self.send_json(self.service.drug_names(params))
            if parsed.path == "/api/reaction-reports":
                return self.send_json(self.service.reaction_reports(params))
            if parsed.path == "/api/changes":
                return self.send_json(self.service.period_changes(params))
            if parsed.path == "/api/investigations":
                return self.investigation_response(lambda: self.service.investigations.get(params["id"]) if params.get("id") else {"investigations": self.service.investigations.list()})
            if parsed.path == "/api/investigations/history":
                return self.investigation_response(lambda: self.service.investigations.history(params.get("id")))
            if parsed.path == "/api/export":
                kind = params.pop("kind", "reactions")
                if kind not in {"reactions", "timeseries", "signals", "reports"}:
                    raise APIError("Unknown export kind.")
                data = self.service.dashboard(params)
                # Include provenance in every exported row so files retain it.
                rows = [{"source": data["meta"]["source"], "drug": data["meta"]["drug"], **row} for row in data[kind]]
                return self.send_bytes(csv_response(rows).encode("utf-8-sig"), "text/csv; charset=utf-8", extra={"Content-Disposition": f'attachment; filename="{data["meta"]["mode"]}-{kind}.csv"'})
            if parsed.path.startswith("/api/"):
                raise APIError("API route not found.", 404)
            relative = parsed.path.lstrip("/") or "index.html"
            path = (self.static_dir / relative).resolve()
            if not path.is_relative_to(self.static_dir.resolve()):
                raise APIError("File not found.", 404)
            if not path.is_file() and "." not in Path(relative).name:
                path = self.static_dir / "index.html"
            if not path.is_file():
                if relative == "index.html":
                    return self.send_bytes(b"Build the dashboard first with npm install and npm run build, or run npm run dev.", "text/plain; charset=utf-8", 503)
                raise APIError("File not found.", 404)
            return self.send_bytes(path.read_bytes(), mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        except APIError as exc:
            self.send_json({"error": str(exc), "status": "error"}, exc.status)
        except Exception:
            import traceback
            traceback.print_exc()
            self.send_json({"error": "The local server could not complete this request. Review the server console for details.", "status": "error"}, 500)

    def investigation_response(self, action):
        try:
            return self.send_json(action())
        except InvestigationError as exc:
            raise APIError(str(exc), exc.status) from None
        except (sqlite3.Error, OSError):
            raise APIError("The local investigation library is unavailable. Your current workspace is still open; try again before leaving it.", 503) from None

    def do_POST(self):
        try:
            self.allowed()
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                raise APIError("Send application/json.", 415)
            length = integer(self.headers.get("Content-Length"), 0, 1, 2_000_000)
            try:
                body = json.loads(self.rfile.read(length))
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise APIError("Request body must be valid JSON.") from None
            if not isinstance(body, dict):
                raise APIError("Request body must be a JSON object.")
            route = urlsplit(self.path).path
            if route == "/api/investigations/save":
                return self.investigation_response(lambda: self.service.investigations.save(body))
            if route == "/api/investigations/delete":
                def remove():
                    self.service.investigations.delete(body.get("id"), body.get("revision"))
                    return {"deleted": True}
                return self.investigation_response(remove)
            if route == "/api/model/train":
                return self.send_json(self.service.train(body))
            if route == "/api/narratives/fetch":
                return self.send_json(self.service.fetch_device_narratives(body))
            if route == "/api/narratives":
                texts = body.get("texts")
                if texts is None:
                    texts = [body.get("text", "")]
                if not isinstance(texts, list) or not texts or len(texts) > 1000 or any(not isinstance(text, str) for text in texts):
                    raise APIError("Provide text, or a list of up to 1,000 text strings.")
                if any(len(text) > 100000 for text in texts) or not any(text.strip() for text in texts):
                    raise APIError("Provide non-empty narratives of up to 100,000 characters each.")
                records = [{"id": i + 1, "text": text, "source": "user-provided text"} for i, text in enumerate(texts) if text.strip()]
                config = {"top_k": integer(body.get("top_k"), 25, 5, 200), "min_df": integer(body.get("min_df"), 1, 1, 1000),
                          "ngram_low": integer(body.get("ngram_low"), 1, 1, 3), "ngram_high": integer(body.get("ngram_high"), 2, 1, 3)}
                if config["ngram_low"] > config["ngram_high"]:
                    raise APIError("Minimum n-gram length must not exceed maximum n-gram length.")
                stop = body.get("custom_stopwords", [])
                if not isinstance(stop, list) or len(stop) > 1000 or any(not isinstance(word, str) or len(word) > 100 for word in stop):
                    raise APIError("Custom stopwords must be a list of up to 1,000 short strings.")
                config["custom_stopwords"] = [word.strip().lower() for word in stop]
                return self.send_json(narratives_result(records, "User-provided text analyzed by the Vigil server. Text is not persisted or sent to a language-model service.", config))
            raise APIError("API route not found.", 404)
        except APIError as exc:
            self.send_json({"error": str(exc), "status": "error"}, exc.status)
        except Exception:
            import traceback
            traceback.print_exc()
            self.send_json({"error": "The analysis could not be completed. Review the server console for details.", "status": "error"}, 500)

    def do_HEAD(self):
        self.do_GET()


class DashboardHandler(DashboardRoutes, BaseHTTPRequestHandler):
    pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), DashboardHandler)
    server.daemon_threads = True
    print(f"Signal Monitor running at http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

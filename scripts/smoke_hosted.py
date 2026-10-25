"""Exercise an isolated localhost container, including persistence after restart.

This refuses non-loopback destinations. Authentication values come from env and
are never printed. Do not point it at your regular local investigation library.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:18766")
    parser.add_argument("--phase", choices=["create", "verify"], required=True)
    parser.add_argument("--state", default=".vigil-runtime/hosted-smoke.json")
    args = parser.parse_args()
    target = urlsplit(args.url)
    if target.scheme != "http" or target.hostname not in {"127.0.0.1", "localhost"} or target.path or target.query or target.fragment:
        raise SystemExit("Use only an isolated localhost test container.")
    origin = os.environ["VIGIL_PUBLIC_ORIGIN"]
    token = base64.b64encode((os.environ["VIGIL_AUTH_USER"] + ":" + os.environ["VIGIL_AUTH_PASSWORD"]).encode()).decode()

    def request(method, path, body=None, authenticated=True):
        headers = {"Host": urlsplit(origin).netloc, "Origin": origin}
        if authenticated:
            headers["Authorization"] = "Basic " + token
        if body is not None:
            headers["Content-Type"] = "application/json"
        query = Request(args.url + path, data=json.dumps(body).encode() if body is not None else None,
                        headers=headers, method=method)
        try:
            with urlopen(query, timeout=15) as response:
                return response.status, json.loads(response.read())
        except HTTPError as error:
            return error.code, json.loads(error.read())

    for attempt in range(40):
        try:
            if request("GET", "/healthz", authenticated=False)[0] == 200:
                break
        except (URLError, OSError):
            pass
        time.sleep(.25)
    else:
        raise SystemExit("Container did not become healthy.")
    assert request("GET", "/api/investigations", authenticated=False)[0] == 401
    state_path = Path(args.state)
    if args.phase == "create":
        cohort = {"mode": "reference", "drug": "METFORMIN", "compare": "", "start": "2025-01-01",
                  "end": "2025-01-31", "age": "All", "sex": "", "reporters": ""}
        status, result = request("GET", "/api/dashboard/section?" + urlencode({**cohort, "section": "core"}))
        assert status == 200 and result["section"] == "core"
        assert sum(row["count"] for row in result["data"]["timeseries"]) == result["data"]["summary"]["total_reports"]
        payload = {"name": "Container smoke investigation", "notes": "Initial test question", "cohort": cohort,
                   "reaction": "NAUSEA", "view": "signals", "retrieved_at": ""}
        status, saved = request("POST", "/api/investigations/save", payload)
        assert status == 200
        status, updated = request("POST", "/api/investigations/save", {**payload, "id": saved["id"], "revision": 1, "notes": "Updated test question"})
        assert status == 200 and updated["revision"] == 2
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps({"id": saved["id"]}), encoding="utf-8")
    else:
        identifier = json.loads(state_path.read_text(encoding="utf-8"))["id"]
        status, saved = request("GET", "/api/investigations?id=" + identifier)
        assert status == 200 and saved["notes"] == "Updated test question" and saved["revision"] == 2
        status, history = request("GET", "/api/investigations/history?id=" + identifier)
        assert status == 200 and [event["revision"] for event in history["events"]] == [2, 1]
    print(json.dumps({"check": "isolated-hosted-container", "phase": args.phase, "status": "passed"}))


if __name__ == "__main__":
    main()

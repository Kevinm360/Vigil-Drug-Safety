"""Opt-in real FDA smoke check, without printing credentials or case details.

    .venv/Scripts/python.exe tests/smoke_live.py
    .venv/Scripts/python.exe tests/smoke_live.py --train 300

Uses OPENFDA_API_KEY from the server environment or ignored local
.streamlit/secrets.toml. Never writes model pickle files or report samples.
"""
from pathlib import Path
import argparse
import json
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.server import APIError, DashboardService  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--drug", default="METFORMIN")
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default="2025-01-31")
    parser.add_argument("--train", type=int, nargs="?", const=300, default=0, metavar="REPORTS",
                        help="Also train all four model variants on a capped real sample (default 300).")
    parser.add_argument("--device-narratives", action="store_true", help="Also fetch five real MAUDE device narratives.")
    args = parser.parse_args()
    service = DashboardService()
    cohort = {"mode": "live", "drug": args.drug, "start": args.start, "end": args.end}
    started = time.monotonic()
    try:
        result = service.dashboard(cohort)
        total = result["summary"]["total_reports"]
        series_total = sum(row["count"] for row in result["timeseries"])
        assert series_total == total, "Weekly counts do not reconcile with the real cohort total."
        assert result["meta"]["mode"] == "live", "Live queries must never fall back to a synthetic source."
        assert not total or result["reports"], "A non-empty live cohort must return report samples."
        assert not result["meta"]["warnings"], "One or more live facets were unavailable."
        print(json.dumps({"check": "live-dashboard", "status": "passed", "source": result["meta"]["source"],
                          "cohort": cohort, "reports": total, "weekly_count_sum": series_total,
                          "report_samples": len(result["reports"]), "reaction_statistics": len(result["signals"]),
                          "severity_comparisons": len(result["severity"]["reactions"]),
                          "seconds": round(time.monotonic() - started, 2)}))
        if args.device_narratives:
            device = service.fetch_device_narratives({"start": args.start, "end": args.end, "limit": 5})
            assert device["total"] > 0, "No real MAUDE narratives returned in this period."
            print(json.dumps({"check": "device-narratives", "status": "passed", "source": device["source"], "narratives": device["total"]}))
        if args.train:
            started = time.monotonic()
            trained = service.train({**cohort, "max_records": args.train})
            evaluation = trained["evaluation"]
            full = evaluation["feature_sets"]["Full"]["evaluations"]
            reduced = evaluation["feature_sets"]["Reduced"]["evaluations"]
            assert len(evaluation["comparison"]) == 4, "Expected both algorithms on both feature sets."
            for model_name in full:
                labels = full[model_name]["held_out_labels"]
                assert labels == reduced[model_name]["held_out_labels"], "Full/reduced models must share the same held-out labels."
                assert len(labels) == evaluation["test_size"], "Held-out predictions do not match test count."
                assert len(full[model_name]["held_out_probabilities"]) == len(labels)
            print(json.dumps({"check": "live-model-training", "status": "passed", "source": trained["source"],
                              "sample_size": trained["sample_size"], "train_size": evaluation["train_size"], "test_size": evaluation["test_size"],
                              "variants": len(evaluation["comparison"]), "paired_held_out_labels": True,
                              "deduplicated_reports": trained["deduplicated_reports"],
                              "seconds": round(time.monotonic() - started, 2)}))
    except (APIError, AssertionError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

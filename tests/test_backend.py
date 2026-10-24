"""Behavioral checks for provenance, cohort correctness and analysis integrity."""
import csv
import datetime as dt
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import io
import json
import math
from pathlib import Path
import tempfile
import threading
import unittest
from collections import Counter
from unittest.mock import patch
from urllib.error import HTTPError

from backend.server import (
    APIError, DashboardHandler, DashboardService, OpenFDAClient, annotate,
    association, cohort_query, csv_response, date_value, flatten_report,
    keyword_scores, narratives_result, search_query, training_row,
    validate_params, weekly_series, graph_result,
)


class FakeClient:
    def __init__(self, failure=None):
        self.queries = []
        self.failure = failure

    def count(self, query):
        self.queries.append(query)
        if self.failure:
            raise self.failure
        if "seriousness" in query:
            return 1
        if "serious:1" in query:
            return 4
        return 10 if 'medicinalproduct:"METFORMIN"' in query else 100

    def aggregate(self, query, field, limit=1000):
        self.queries.append(query)
        if self.failure:
            raise self.failure
        if field == "receivedate":
            return [{"time": "20250106", "count": 10}]
        if field == "patient.reaction.reactionmeddrapt.exact":
            count = 4 if "serious:1" in query else 10
            if "medicinalproduct" not in query:
                count *= 2
            return [{"term": "NAUSEA", "count": count}]
        return [{"term": "1", "count": 3}]

    def request(self, params):
        self.queries.append(params["search"])
        return {"results": [{"safetyreportid": "real-id", "receivedate": "20250106", "serious": "1",
                             "patient": {"drug": [{"medicinalproduct": "OTHER"}, {"medicinalproduct": "METFORMIN", "drugcharacterization": "1"}],
                                         "reaction": [{"reactionmeddrapt": "NAUSEA"}], "patientonsetage": "24", "patientonsetageunit": "802"}}]}


class ComparisonClient(FakeClient):
    def __init__(self, primary_total=10, compare_total=7, failed=(), compare_reactions=None):
        super().__init__()
        self.primary_total, self.compare_total = primary_total, compare_total
        self.failed = set(failed)
        self.compare_reactions = compare_reactions

    def count(self, query):
        if 'medicinalproduct:"IBUPROFEN"' in query:
            self.queries.append(query)
            if "total" in self.failed:
                raise APIError("comparison count unavailable", 503)
            return self.compare_total
        if 'medicinalproduct:"METFORMIN"' in query and not self.primary_total:
            self.queries.append(query)
            return 0
        return super().count(query)

    def aggregate(self, query, field, limit=1000):
        if 'medicinalproduct:"IBUPROFEN"' in query:
            self.queries.append(query)
            facet = "timeseries" if field == "receivedate" else "reactions"
            if facet in self.failed:
                raise APIError(f"comparison {facet} unavailable", 503)
            if self.compare_total == 0:
                return []
            if field == "receivedate":
                return [{"time": "20250113", "count": self.compare_total}]
            return self.compare_reactions if self.compare_reactions is not None else [{"term": "NAUSEA", "count": self.compare_total}]
        if 'medicinalproduct:"METFORMIN"' in query and not self.primary_total:
            self.queries.append(query)
            return []
        return super().aggregate(query, field, limit)


class CohortAndStatisticsTests(unittest.TestCase):
    def test_network_keeps_available_reactions_and_subject_statistics(self):
        counts = Counter({f"REACTION {i}": 100 - i for i in range(50)})
        graph = graph_result({"METFORMIN": counts, "COMPARATOR": Counter({"REACTION 0": 200, "OTHER": 4})},
                             [{"reaction": "REACTION 0", "a": 100, "prr": 3, "ror": 4, "chi2": 12, "signal": True}])
        reactions = [node for node in graph["nodes"] if node["type"] == "reaction"]
        self.assertEqual(len(reactions), 51)
        first = next(node for node in reactions if node["label"] == "REACTION 0")
        self.assertEqual(first["a"], 100)
        self.assertEqual(first["value"], 300)
        self.assertEqual(first["prr"], 3)
        self.assertTrue(first["signal"])
        self.assertTrue(any(link["source"] == "drug:COMPARATOR" and link["target"] == first["id"] for link in graph["links"]))
        larger = graph_result({"METFORMIN": Counter({f"REACTION {i}": 100 - i for i in range(90)})})
        self.assertEqual(sum(node["type"] == "reaction" for node in larger["nodes"]), 80)

    def test_validates_dates_and_rejects_query_injection(self):
        for value in ["2025-02-30", "2025-1-01", "not a date", "202501"]:
            with self.assertRaises(APIError):
                date_value(value, "start")
        with self.assertRaises(APIError):
            validate_params({"drug": 'METFORMIN" OR serious:1'})
        with self.assertRaises(APIError):
            validate_params({"start": "2025-02-01", "end": "2025-01-01"})

    def test_all_cohort_filters_reach_queries(self):
        params = validate_params({"mode": "live", "drug": "metformin", "start": "2025-01-01", "end": "2025-01-31",
                                  "sex": "Female,Unknown", "reporters": "Consumer,Physician", "age": "18-44"})
        query = search_query(params)
        self.assertIn("receivedate:[20250101 TO 20250131]", query)
        self.assertIn('patient.drug.medicinalproduct:"METFORMIN"', query)
        self.assertIn("patient.patientsex:2", query)
        self.assertIn("patient.patientsex:0", query)
        self.assertIn("primarysource.qualification:5", query)
        self.assertIn("primarysource.qualification:1", query)
        self.assertIn("patient.patientonsetageunit:802", query)
        self.assertIn("patient.patientonsetageunit:804", query)
        background = search_query(params, drug=False)
        self.assertNotIn("medicinalproduct", background)
        self.assertIn(cohort_query(params), background)

    def test_contingency_table_and_confidence_intervals(self):
        result = association("NAUSEA", 20, 100, 40, 1000)
        self.assertEqual([result[k] for k in ["a", "b", "c", "d"]], [20, 80, 20, 880])
        self.assertAlmostEqual(result["prr"], 9)
        self.assertAlmostEqual(result["ror"], 11)
        self.assertLess(result["prr_low"], result["prr"])
        self.assertGreater(result["prr_high"], result["prr"])
        self.assertTrue(result["signal"])
        zero = association("RARE", 3, 10, 3, 100)
        self.assertTrue(zero["corrected"])
        self.assertTrue(math.isfinite(zero["ror_high"]))
        self.assertIsNone(association("BAD", 20, 10, 30, 100))
        self.assertIsNone(association("NO BACKGROUND", 3, 10, 3, 10))

    def test_weekly_buckets_fill_missing_and_exclude_current_baseline(self):
        start = dt.date(2025, 1, 6)
        rows = [{"date": (start + dt.timedelta(days=i * 7)).isoformat(), "count": i + 1} for i in range(6)]
        rows.append({"date": (start + dt.timedelta(days=42)).isoformat(), "count": 100})
        result = weekly_series(rows, "2025-01-06", "2025-02-24")
        self.assertEqual(result[-1]["count"], 0)
        self.assertGreater(result[-2]["z"], 40)
        self.assertEqual(sum(row["count"] for row in result), 121)

    def test_subject_drug_and_unit_conversion_do_not_use_first_drug(self):
        report = FakeClient().request({"search": ""})["results"][0]
        result = flatten_report(report, "METFORMIN")
        self.assertEqual(result["drug_name"], "METFORMIN")
        self.assertEqual(result["age"], 2)
        self.assertEqual(result["receivedate"], "2025-01-06")
        report.update({"seriousnessdeath": "1", "fulfillexpeditecriteria": "1"})
        report["patient"]["death"] = {"patientdeathdate": "20250106"}
        row = training_row(report, "METFORMIN")
        self.assertEqual(row["subject_drug_role"], "1")
        self.assertEqual(row["serious"], 1)
        self.assertNotIn("seriousnessdeath", row)
        self.assertNotIn("fulfillexpeditecriteria", row)
        self.assertNotIn("death", row)
        self.assertNotIn("reactions", row)


class NLPTests(unittest.TestCase):
    def test_negation_and_repeated_mentions(self):
        result = annotate("No evidence of stroke. Later, a stroke occurred with syncope. Infection was denied.")
        self.assertIn("stroke", result["clinical_flags"])
        self.assertIn("stroke", result["negated_flags"])
        self.assertIn("syncope", result["clinical_flags"])
        self.assertEqual(annotate("Patient denies seizure and no infection.")["clinical_flags"], [])
        self.assertEqual(annotate("stroked")['clinical_flags'], [])

    def test_tfidf_small_and_empty_corpora(self):
        self.assertEqual(keyword_scores(["", "the and it"]), [])
        self.assertTrue(keyword_scores(["severe nausea resolved"]))
        result = keyword_scores(["severe nausea resolved", "severe nausea improved"], min_df=2, ngram_low=2, ngram_high=3)
        self.assertTrue(any(row["term"] == "severe nausea" for row in result))
        self.assertFalse(any("resolved" in row["term"] for row in result))

    def test_annotated_records_and_contrastive_have_clear_source(self):
        result = narratives_result([{"id": 1, "text": "Stroke with weakness", "source": "user"},
                                    {"id": 2, "text": "Fatigue improved", "source": "user"}], "User text")
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["records"][0]["source"], "user")
        self.assertTrue(result["contrastive"])
        self.assertEqual(sum(row["count"] for row in result["sentiment"]), 2)

    def test_analysis_retains_every_annotated_record_for_table_and_export(self):
        records = [{"id": index, "text": f"Nausea improved in report {index}", "source": "user"} for index in range(151)]
        result = narratives_result(records, "User text")
        self.assertEqual(result["total"], 151)
        self.assertEqual(len(result["records"]), 151)
        self.assertEqual(result["records"][-1]["id"], 150)
        self.assertEqual(records[-1], {"id": 150, "text": "Nausea improved in report 150", "source": "user"})


class SeriousOutcomeIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import pandas as pd
            from app import serious_outcome
        except ImportError:
            raise unittest.SkipTest("Optional machine-learning dependencies are not installed.")
        cls.pd, cls.module = pd, serious_outcome

    def frame(self):
        pd, module = self.pd, self.module
        frame = pd.DataFrame({name: [i % 7 for i in range(400)] for name in module.NUMERIC_FEATURES})
        for name in module.CATEGORICAL_FEATURES:
            frame[name] = [str(i % 3) for i in range(400)]
        frame["receivedate"] = pd.date_range("2025-01-01", periods=400)
        frame["serious"] = [i % 2 for i in range(400)]
        return frame

    def test_chronological_split_has_disjoint_rows_and_dates(self):
        frame = self.frame()
        train, test, detail = self.module._split_indices(frame)
        self.assertFalse(set(train) & set(test))
        self.assertLess(frame.loc[train, "receivedate"].max(), frame.loc[test, "receivedate"].min())
        self.assertEqual(len(train) + len(test), len(frame))
        self.assertIn("Chronological", detail)

    def test_stratified_fallback_is_explicit_when_dates_cannot_split(self):
        frame = self.frame()
        frame["receivedate"] = self.pd.Timestamp("2025-01-01")
        train, test, detail = self.module._split_indices(frame)
        self.assertIn("Stratified", detail)
        self.assertFalse(set(train) & set(test))
        self.assertEqual(set(frame.loc[test, "serious"]), {0, 1})

    def test_outcomes_and_proxies_are_excluded_and_threshold_changes_counts(self):
        module = self.module
        self.assertNotIn("serious", module.PREDICTOR_COLUMNS)
        self.assertFalse(set(module.ADMINISTRATIVE_PROXY_FEATURES) & set(module.REDUCED_PREDICTOR_COLUMNS))
        self.assertFalse(any("seriousness" in feature or "outcome" in feature for feature in module.PREDICTOR_COLUMNS))
        metrics = module.threshold_metrics([0, 0, 1, 1], [.1, .8, .4, .9], .5)
        self.assertEqual(metrics["confusion_matrix"].tolist(), [[1, 1], [1, 1]])
        self.assertEqual(metrics["precision"], .5)
        stricter = module.threshold_metrics([0, 0, 1, 1], [.1, .8, .4, .9], .9)
        self.assertEqual(stricter["confusion_matrix"].tolist(), [[2, 0], [1, 1]])


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.root = Path(self.directory.name)
        (self.root / "data" / "bronze").mkdir(parents=True)
        with (self.root / "data" / "bronze" / "reviews.csv").open("w", newline="", encoding="utf-8") as output:
            writer = csv.DictWriter(output, ["review_id", "drug_raw", "drug", "review_text", "rating", "created_at"])
            writer.writeheader()
            writer.writerows([
                {"review_id": 1, "drug_raw": "Glucophage", "drug": "Metformin", "review_text": "nausea and headache", "rating": 3, "created_at": "2025-01-06 00:00:00"},
                {"review_id": 2, "drug_raw": "Advil", "drug": "Ibuprofen", "review_text": "nausea and rash", "rating": 2, "created_at": "2025-01-13 00:00:00"},
            ])
        self.service = DashboardService(self.root, FakeClient())

    def tearDown(self):
        self.directory.cleanup()

    def test_reference_provenance_no_invented_reports_or_outcomes(self):
        result = self.service.dashboard({"drug": "GLUCOPHAGE", "compare": "IBUPROFEN"})
        self.assertIn("Synthetic", result["meta"]["source"])
        self.assertEqual(result["meta"]["record_label"], "reviews")
        self.assertEqual(result["summary"]["total_reports"], 1)
        self.assertEqual(result["summary"]["compare_total"], 1)
        self.assertEqual(result["reports"], [])
        self.assertEqual(result["severity"]["outcomes"], [])
        self.assertIsNone(result["summary"]["serious_reports"])
        self.assertIn("synthetic", result["narratives"]["records"][0]["source"])
        self.assertEqual(sum(row["count"] for row in result["timeseries"]), 1)
        self.assertEqual(result["meta"]["comparison"]["status"], "complete")

    def test_reference_comparison_survives_empty_subject(self):
        result = self.service.dashboard({"drug": "NO SUBJECT MATCH", "compare": "IBUPROFEN"})
        self.assertEqual(result["summary"]["total_reports"], 0)
        self.assertEqual(result["summary"]["compare_total"], 1)
        self.assertEqual(result["meta"]["status"], "empty")
        self.assertEqual(result["meta"]["comparison"]["status"], "complete")
        self.assertEqual(sum(row["compare_count"] for row in result["timeseries"]), 1)
        self.assertTrue(result["reactions"])
        self.assertTrue(all(row["reports"] == 0 and row["compare_reports"] == 1 for row in result["reactions"]))

    def test_live_comparison_survives_empty_subject(self):
        self.service.client = ComparisonClient(primary_total=0)
        result = self.service.dashboard({"mode": "live", "compare": "IBUPROFEN", "start": "2025-01-01", "end": "2025-01-31", "sex": "Female"})
        self.assertEqual(result["summary"]["total_reports"], 0)
        self.assertEqual(result["summary"]["compare_total"], 7)
        self.assertEqual(result["meta"]["status"], "empty")
        self.assertEqual(result["meta"]["comparison"]["status"], "complete")
        self.assertEqual(sum(row["count"] for row in result["timeseries"]), 0)
        self.assertEqual(sum(row["compare_count"] for row in result["timeseries"]), 7)
        self.assertEqual(result["reactions"], [{"reaction": "NAUSEA", "reports": 0, "compare_reports": 7}])
        self.assertEqual(result["signals"], [])
        self.assertTrue(any(link["source"] == "drug:IBUPROFEN" and link["value"] == 7 for link in result["graph"]["links"]))
        for query in self.service.client.queries:
            self.assertIn("receivedate:[20250101 TO 20250131]", query)
            self.assertIn("patient.patientsex:2", query)

    def test_live_failed_comparison_facets_stay_unknown_independently(self):
        names = {"total": "total_available", "timeseries": "timeseries_available", "reactions": "reactions_available"}
        for failed in names:
            with self.subTest(failed=failed):
                service = DashboardService(self.root, ComparisonClient(failed={failed}))
                result = service.dashboard({"mode": "live", "compare": "IBUPROFEN", "start": "2025-01-01", "end": "2025-01-31"})
                comparison = result["meta"]["comparison"]
                self.assertEqual(comparison["status"], "partial")
                self.assertEqual(result["meta"]["status"], "partial")
                self.assertTrue(result["meta"]["warnings"])
                for facet, flag in names.items():
                    self.assertEqual(comparison[flag], facet != failed)
                if failed == "total":
                    self.assertIsNone(result["summary"]["compare_total"])
                else:
                    self.assertEqual(result["summary"]["compare_total"], 7)
                if failed == "timeseries":
                    self.assertTrue(all(row["compare_count"] is None for row in result["timeseries"]))
                else:
                    self.assertEqual(sum(row["compare_count"] for row in result["timeseries"]), 7)
                if failed == "reactions":
                    self.assertTrue(all(row["compare_reports"] is None for row in result["reactions"]))
                    self.assertFalse(any(node["id"] == "drug:IBUPROFEN" for node in result["graph"]["nodes"]))
                else:
                    self.assertEqual(result["reactions"][0]["compare_reports"], 7)

    def test_live_unavailable_comparison_is_not_a_zero_comparator(self):
        self.service.client = ComparisonClient(failed={"total", "timeseries", "reactions"})
        result = self.service.dashboard({"mode": "live", "compare": "IBUPROFEN"})
        self.assertEqual(result["meta"]["comparison"]["status"], "unavailable")
        self.assertIsNone(result["summary"]["compare_total"])
        self.assertTrue(all(row["compare_count"] is None for row in result["timeseries"]))
        self.assertTrue(all(row["compare_reports"] is None for row in result["reactions"]))
        self.assertEqual(len(result["meta"]["warnings"]), 3)

    def test_live_successful_empty_comparator_preserves_real_zeros(self):
        self.service.client = ComparisonClient(compare_total=0)
        result = self.service.dashboard({"mode": "live", "compare": "IBUPROFEN"})
        self.assertEqual(result["meta"]["comparison"]["status"], "complete")
        self.assertEqual(result["meta"]["warnings"], [])
        self.assertEqual(result["summary"]["compare_total"], 0)
        self.assertTrue(all(row["compare_count"] == 0 for row in result["timeseries"]))
        self.assertTrue(all(row["compare_reports"] == 0 for row in result["reactions"]))

    def test_truncated_comparison_reaction_aggregate_marks_missing_counts_unknown(self):
        reactions = [{"term": f"OTHER {index}", "count": 1} for index in range(1000)]
        self.service.client = ComparisonClient(compare_reactions=reactions)
        result = self.service.dashboard({"mode": "live", "compare": "IBUPROFEN"})
        self.assertTrue(result["meta"]["comparison"]["reactions_available"])
        self.assertTrue(result["meta"]["comparison"]["reactions_truncated"])
        self.assertEqual(result["meta"]["comparison"]["status"], "partial")
        self.assertIsNone(result["reactions"][0]["compare_reports"])
        self.assertTrue(any("comparison counts are unavailable, not zero" in warning for warning in result["meta"]["warnings"]))

    def test_unrequested_comparator_has_explicit_absent_metadata(self):
        for mode in ["reference", "live"]:
            with self.subTest(mode=mode):
                result = self.service.dashboard({"mode": mode})
                self.assertEqual(result["meta"]["comparison"]["status"], "not_requested")
                self.assertIsNone(result["summary"]["compare_total"])
                self.assertTrue(all(row["compare_count"] is None for row in result["timeseries"]))
                self.assertTrue(all(row["compare_reports"] is None for row in result["reactions"]))

    def test_reference_rejects_unavailable_cohort_filters(self):
        with self.assertRaisesRegex(APIError, "no patient demographics"):
            self.service.dashboard({"sex": "Female"})

    def test_reference_empty_window_is_truthful(self):
        result = self.service.dashboard({"start": "2020-01-01", "end": "2020-01-31"})
        self.assertEqual(result["meta"]["status"], "empty")
        self.assertEqual(result["signals"], [])
        self.assertEqual(result["narratives"]["records"], [])

    def test_live_reports_and_all_aggregate_queries_respect_date_and_cohort(self):
        result = self.service.dashboard({"mode": "live", "start": "2025-01-01", "end": "2025-01-31", "sex": "Female", "reporters": "Physician"})
        self.assertEqual(result["meta"]["source"], "openFDA · FAERS live")
        self.assertEqual(result["reports"][0]["safetyreportid"], "real-id")
        self.assertEqual(result["summary"]["total_reports"], 10)
        for query in self.service.client.queries:
            self.assertIn("receivedate:[20250101 TO 20250131]", query)
            self.assertIn("patient.patientsex:2", query)
            self.assertIn("primarysource.qualification:1", query)

    def test_live_failure_does_not_silently_become_reference(self):
        self.service.client = FakeClient(APIError("network unavailable", 503))
        with self.assertRaisesRegex(APIError, "network unavailable"):
            self.service.dashboard({"mode": "live"})

    def test_long_live_date_windows_are_partitioned(self):
        params = validate_params({"mode": "live", "start": "2020-01-01", "end": "2025-01-01"})
        self.service.daily_counts(params)
        self.assertEqual(len(self.service.client.queries), 3)
        self.assertIn("20200101 TO 20220618", self.service.client.queries[0])

    def test_caches_are_copied_to_prevent_ui_request_mutation(self):
        first = self.service.dashboard({})
        first["summary"]["total_reports"] = 99999
        second = self.service.dashboard({})
        self.assertEqual(second["summary"]["total_reports"], 1)
        self.assertTrue(second["meta"]["cached"])

    def test_reference_cannot_train_seriousness_model(self):
        with self.assertRaisesRegex(APIError, "no seriousness target"):
            self.service.train({"mode": "reference"})


class ClientAndExportTests(unittest.TestCase):
    def test_only_true_no_matches_is_treated_as_empty(self):
        def opener_no_matches(*args, **kwargs):
            raise HTTPError("https://api.fda.gov", 404, "Not Found", {}, io.BytesIO(b'{"error":{"message":"No matches found!"}}'))
        client = OpenFDAClient(opener=opener_no_matches)
        self.assertEqual(client.request({"search": "example"})["results"], [])

        def opener_not_found(*args, **kwargs):
            raise HTTPError("https://api.fda.gov", 404, "Not Found", {}, io.BytesIO(b'{"error":{"message":"Bad path"}}'))
        with self.assertRaises(APIError):
            OpenFDAClient(opener=opener_not_found).request({"search": "example"})

    def test_key_is_server_only_and_response_cache_does_not_leak_it(self):
        captured = []
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self, limit):
                return b'{"results":[],"meta":{"results":{"total":0}}}'
        def opener(request, timeout):
            captured.append(request.full_url)
            return Response()
        with patch.dict("os.environ", {"OPENFDA_API_KEY": "test-secret"}):
            client = OpenFDAClient(opener=opener)
            result = client.request({"search": "test"})
            client.request({"search": "test"})
        self.assertEqual(len(captured), 1)
        self.assertIn("api_key=test-secret", captured[0])
        self.assertNotIn("test-secret", json.dumps(result))
        self.assertNotIn("test-secret", str(client.cache))

    def test_csv_formula_strings_are_escaped(self):
        result = csv_response([{"reaction": "=HYPERLINK(\"bad\")", "ror": -1.2, "source": "synthetic"}])
        rows = list(csv.DictReader(io.StringIO(result)))
        self.assertTrue(rows[0]["reaction"].startswith("'="))
        self.assertEqual(rows[0]["ror"], "-1.2")
        self.assertIn("synthetic", result)


class AdaptiveReportPagingTests(unittest.TestCase):
    class SizedClient:
        def __init__(self, count=30, max_page=5, oversized=()):
            self.count, self.max_page, self.oversized = count, max_page, set(oversized)
            self.calls = []

        def request(self, params):
            self.calls.append(dict(params))
            offset, limit = params["skip"], params["limit"]
            positions = range(offset, min(offset + limit, self.count))
            if limit > self.max_page or self.oversized.intersection(positions):
                raise APIError("openFDA response was too large for one batch.", 502, code="response_too_large")
            return {"results": [{"safetyreportid": str(i), "receivedate": "20250106", "patient": {}} for i in positions]}

    def test_oversized_batch_retries_smaller_without_losing_or_repeating_records(self):
        client = self.SizedClient(count=30, max_page=5)
        service = DashboardService(client=client)
        result = service.fetch_report_sample("exact cohort", 30, "receivedate:asc")
        self.assertEqual([row["safetyreportid"] for row in result["records"]], [str(i) for i in range(30)])
        self.assertEqual([call["limit"] for call in client.calls[:2]], [25, 5])
        self.assertTrue(result["adaptive_paging"])
        self.assertEqual(result["skipped_oversized"], 0)
        self.assertEqual(result["scanned_positions"], 30)
        self.assertTrue(all(call["search"] == "exact cohort" and call["sort"] == "receivedate:asc" for call in client.calls))

    def test_single_oversized_records_are_explicitly_skipped_and_paging_continues(self):
        client = self.SizedClient(count=30, oversized={7, 18})
        result = DashboardService(client=client).fetch_report_sample("cohort", 30, "receivedate:desc", transform=lambda row: {"id": row["safetyreportid"]})
        self.assertEqual([row["id"] for row in result["records"]], [str(i) for i in range(30) if i not in {7, 18}])
        self.assertEqual(result["skipped_oversized"], 2)
        self.assertEqual(result["scanned_positions"], 30)
        self.assertTrue(any(call["limit"] == 1 and call["skip"] == 7 for call in client.calls))
        self.assertTrue(any(call["limit"] == 1 and call["skip"] == 18 for call in client.calls))

    def test_all_oversized_positions_are_bounded_and_never_replaced(self):
        client = self.SizedClient(count=4, oversized={0, 1, 2, 3})
        result = DashboardService(client=client).fetch_report_sample("cohort", 4, "receivedate:asc")
        self.assertEqual(result["records"], [])
        self.assertEqual(result["skipped_oversized"], 4)
        self.assertEqual(result["scanned_positions"], 4)
        self.assertLessEqual(len(client.calls), 12)

    def test_non_size_api_errors_still_surface(self):
        class FailedClient:
            def request(self, params):
                raise APIError("API key missing", 503)
        with self.assertRaisesRegex(APIError, "API key missing"):
            DashboardService(client=FailedClient()).fetch_report_sample("cohort", 20, "receivedate:desc")

    def test_live_dashboard_discloses_omission_without_changing_aggregate_counts(self):
        class Client(FakeClient):
            def request(self, params):
                offset, limit = params["skip"], params["limit"]
                if offset == 0:
                    raise APIError("openFDA response was too large for one batch.", 502, code="response_too_large")
                return {"results": [{"safetyreportid": "real-surviving-record", "receivedate": "20250106", "patient": {}}]}
        result = DashboardService(client=Client()).dashboard({"mode": "live", "start": "2025-01-01", "end": "2025-01-31"})
        self.assertEqual(result["summary"]["total_reports"], 10)
        self.assertEqual(result["meta"]["skipped_oversized_reports"], 1)
        self.assertEqual(result["meta"]["status"], "partial")
        self.assertEqual(result["reports"][0]["safetyreportid"], "real-surviving-record")
        self.assertIn("Aggregate counts still include", result["reports_notice"])


class DrugNameTests(unittest.TestCase):
    class Client:
        def __init__(self, failed=()):
            self.calls = []
            self.failed = failed

        def request(self, params):
            self.calls.append(params)
            field = params["count"]
            if field in self.failed:
                raise APIError("upstream unavailable", 503)
            return {"results": [
                {"term": "Metformin Hydrochloride", "count": 50},
                {"term": "METFORMIN HYDROCHLORIDE", "count": 40},
                {"term": "Metoprolol Tartrate", "count": 20},
                {"term": "UNRELATED", "count": 100},
                {"term": "bad:name", "count": 100},
            ]}

    def test_searches_both_fda_name_fields_and_deduplicates_without_cohort_restrictions(self):
        service = DashboardService()
        service.drug_client = self.Client()
        result = service.drug_names({"q": "met hy"})
        self.assertEqual(result["drugs"], [{"name": "METFORMIN HYDROCHLORIDE", "kind": "Brand / Generic"}])
        self.assertEqual(result["source"], "FDA NDC directory")
        self.assertFalse(result["partial"])
        self.assertEqual(len(service.drug_client.calls), 2)
        for call in service.drug_client.calls:
            self.assertIn("brand_name:met*", call["search"])
            self.assertIn("generic_name:hy*", call["search"])
            self.assertNotIn("receivedate", call["search"])
            self.assertNotIn("api_key", call)

    def test_browsing_and_no_matches_are_explicit(self):
        service = DashboardService()
        service.drug_client = self.Client()
        self.assertGreater(len(service.drug_names({})["drugs"]), 1)
        self.assertTrue(all("search" not in call for call in service.drug_client.calls))
        self.assertEqual(service.drug_names({"q": "nomatch"})["drugs"], [])

    def test_query_operators_and_excessive_prefixes_are_rejected(self):
        service = DashboardService()
        for query in ['met*', 'met OR brand_name:*', 'a' * 81]:
            with self.assertRaises(APIError):
                service.drug_names({"q": query})

    def test_partial_lookup_is_disclosed_and_total_failure_never_becomes_fake_suggestions(self):
        service = DashboardService()
        service.drug_client = self.Client(failed=("brand_name.exact",))
        result = service.drug_names({"q": "met"})
        self.assertTrue(result["partial"])
        self.assertTrue(result["drugs"])
        service.drug_client = self.Client(failed=("brand_name.exact", "generic_name.exact"))
        with self.assertRaisesRegex(APIError, "unavailable"):
            service.drug_names({"q": "met"})


class HTTPBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
        cls.worker = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.worker.join()

    def request(self, method, path, body=None, headers=None):
        connection = HTTPConnection("127.0.0.1", self.http.server_port)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        value = response.read()
        connection.close()
        return response.status, json.loads(value)

    def test_health_and_unknown_api(self):
        self.assertEqual(self.request("GET", "/api/health")[0], 200)
        self.assertEqual(self.request("GET", "/api/no-such-route")[0], 404)

    def test_drug_suggestions_are_available_through_the_local_api(self):
        with patch.object(DashboardHandler.service, "drug_names", return_value={"drugs": [{"name": "METFORMIN", "kind": "Generic"}]}) as lookup:
            status, result = self.request("GET", "/api/drugs?q=met")
        self.assertEqual(status, 200)
        self.assertEqual(result["drugs"][0]["name"], "METFORMIN")
        lookup.assert_called_once_with({"q": "met"})

    def test_cross_origin_and_dns_rebinding_are_rejected(self):
        self.assertEqual(self.request("GET", "/api/health", headers={"Origin": "https://attacker.example"})[0], 403)
        self.assertEqual(self.request("GET", "/api/health", headers={"Host": "attacker.example"})[0], 403)

    def test_narrative_endpoint_and_bad_body(self):
        status, value = self.request("POST", "/api/narratives", json.dumps({"texts": ["No stroke", "Nausea improved"]}), {"Content-Type": "application/json"})
        self.assertEqual(status, 200)
        self.assertEqual(value["total"], 2)
        self.assertEqual(value["records"][0]["clinical_flags"], [])
        self.assertEqual(self.request("POST", "/api/narratives", "{}", {"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.request("POST", "/api/narratives", "[]", {"Content-Type": "application/json"})[0], 400)


if __name__ == "__main__":
    unittest.main()

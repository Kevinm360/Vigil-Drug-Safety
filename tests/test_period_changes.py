from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock

from backend.period_changes import change_row, wilson, validate_periods
from backend.server import APIError, DashboardService, validate_params
from backend.investigations import InvestigationError, InvestigationStore

COHORT={"mode":"live","drug":"METFORMIN","compare":"IBUPROFEN","start":"2025-04-01","end":"2025-06-29","age":"All","sex":"Female","reporters":"Physician"}
PERIODS={"baseline_start":"2025-01-01","baseline_end":"2025-03-31"}


class ShareChangeTests(unittest.TestCase):
    def test_volume_growth_does_not_imply_share_growth(self):
        row=change_row("NAUSEA",10,20,100,200)
        self.assertEqual(row["count_delta"],10)
        self.assertEqual(row["share_delta_pp"],0)
        self.assertEqual(row["direction"],"uncertain")
        self.assertLess(row["ci_low_pp"],0)
        self.assertGreater(row["ci_high_pp"],0)

    def test_sparse_zero_and_empty_denominators_remain_distinct(self):
        current_only=change_row("NAUSEA",0,10,100,100)
        self.assertTrue(current_only["current_only"])
        self.assertTrue(current_only["sparse"])
        self.assertEqual(current_only["direction"],"higher")
        empty=change_row("NAUSEA",0,10,0,100)
        self.assertFalse(empty["current_only"])
        self.assertIsNone(empty["baseline_share"])
        self.assertIsNone(empty["share_delta_pp"])
        unknown=change_row("NAUSEA",None,10,100,100)
        self.assertIsNone(unknown["count_delta"])
        self.assertEqual(unknown["direction"],"unavailable")

    def test_interval_reverses_when_periods_are_swapped(self):
        forward=change_row("X",15,31,100,120)
        reverse=change_row("X",31,15,120,100)
        self.assertAlmostEqual(forward["share_delta_pp"],-reverse["share_delta_pp"])
        self.assertAlmostEqual(forward["ci_low_pp"],-reverse["ci_high_pp"])
        self.assertAlmostEqual(forward["ci_high_pp"],-reverse["ci_low_pp"])
        self.assertEqual(wilson(0,100)[0],0)
        self.assertAlmostEqual(wilson(0,100)[1],0.0369934982,places=8)
        self.assertAlmostEqual(wilson(100,100)[0],0.9630065018,places=8)
        self.assertIsNone(wilson(101,100))

    def test_overlap_bad_dates_and_reversed_periods_are_rejected(self):
        for baseline in [{**PERIODS,"baseline_end":"2025-04-01"},{**PERIODS,"baseline_end":"2025-02-30"},
                         {**PERIODS,"baseline_start":"2025-03-31","baseline_end":"2025-03-01"},{}]:
            with self.assertRaises(ValueError):
                validate_periods(baseline,COHORT)
        self.assertEqual(validate_periods(PERIODS,COHORT),PERIODS)


class PeriodQueryTests(unittest.TestCase):
    class Client:
        def __init__(self,capped=False,missing_failure=False):
            self.calls=[]
            self.capped=capped
            self.missing_failure=missing_failure
        def count(self,query):
            self.calls.append(query)
            if '.exact:' in query:
                if self.missing_failure:
                    raise APIError("FDA unavailable",503)
                return 5
            return 100 if '20250101' in query else 200
        def aggregate(self,query,field,limit):
            self.calls.append(query)
            if '20250101' in query:
                return [{"term":f"OTHER{i}","count":10} for i in range(1000)] if self.capped else [{"term":"NAUSEA","count":10}]
            return [{"term":"NAUSEA","count":20}]

    def test_both_periods_keep_patient_and_reporter_filters(self):
        client=self.Client()
        result=DashboardService(client=client).period_changes({**COHORT,**PERIODS})
        self.assertEqual(result["periods"]["baseline"]["days"],90)
        self.assertEqual(result["periods"]["current"]["days"],90)
        row=result["rows"][0]
        self.assertEqual(row["share_delta_pp"],0)
        for query in client.calls:
            self.assertIn('medicinalproduct:"METFORMIN"',query)
            self.assertIn('patient.patientsex:2',query)
            self.assertIn('primarysource.qualification:1',query)
            self.assertNotIn('IBUPROFEN',query)

    def test_capped_missing_term_is_queried_exactly_before_labeling_current_only(self):
        client=self.Client(capped=True)
        result=DashboardService(client=client).period_changes({**COHORT,**PERIODS})
        row=next(row for row in result["rows"] if row["reaction"]=="NAUSEA")
        self.assertEqual(row["baseline_count"],5)
        self.assertFalse(row["current_only"])
        self.assertTrue(any('reactionmeddrapt.exact:"NAUSEA"' in query for query in client.calls))

    def test_failed_missing_count_remains_unknown(self):
        result=DashboardService(client=self.Client(capped=True,missing_failure=True)).period_changes({**COHORT,**PERIODS})
        row=next(row for row in result["rows"] if row["reaction"]=="NAUSEA")
        self.assertIsNone(row["baseline_count"])
        self.assertIsNone(row["share_delta_pp"])
        self.assertFalse(row["current_only"])
        self.assertTrue(result["meta"]["partial"])

    def test_upstream_failure_and_overlap_do_not_become_zero_periods(self):
        service=DashboardService(client=Mock())
        service.client.count.side_effect=APIError("upstream failure",503)
        with self.assertRaisesRegex(APIError,"upstream failure"):
            service.period_changes({**COHORT,**PERIODS})
        service.client.reset_mock()
        with self.assertRaisesRegex(APIError,"Overlapping"):
            service.period_changes({**COHORT,**PERIODS,"baseline_end":"2025-04-02"})
        service.client.count.assert_not_called()

    def test_empty_period_does_not_get_a_share_or_new_reaction_flag(self):
        client=self.Client()
        original=client.count
        client.count=lambda query:0 if '20250101' in query else original(query)
        result=DashboardService(client=client).period_changes({**COHORT,**PERIODS})
        self.assertEqual(result["periods"]["baseline"]["total_reports"],0)
        self.assertEqual(result["rows"][0]["baseline_count"],0)
        self.assertIsNone(result["rows"][0]["baseline_share"])
        self.assertFalse(result["rows"][0]["current_only"])

    def test_archive_uses_same_subject_and_exact_inclusive_windows(self):
        service=DashboardService()
        service.reviews=Mock(return_value=[{"created_at":day,"drug":drug,"review_text":text} for day,drug,text in [
            ("2025-03-31","METFORMIN","nausea"),("2025-04-01","METFORMIN","nausea"),
            ("2025-06-29","METFORMIN","headache"),("2025-06-30","METFORMIN","nausea"),
            ("2025-05-01","IBUPROFEN","nausea")]])
        result=service.period_changes({**COHORT,**PERIODS,"mode":"reference","sex":"","reporters":""})
        self.assertEqual(result["periods"]["baseline"]["total_reports"],1)
        self.assertEqual(result["periods"]["current"]["total_reports"],2)
        self.assertIn("Synthetic",result["meta"]["source"])
        self.assertEqual(next(row for row in result["rows"] if row["reaction"]=="NAUSEA")["current_share"],50)


class SavedPeriodTests(unittest.TestCase):
    def test_previous_schema_migrates_without_losing_notes_and_saves_periods(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"investigations.sqlite3"
            identifier="a"*32
            with closing(sqlite3.connect(path)) as conn,conn:
                conn.execute("CREATE TABLE investigations (id TEXT PRIMARY KEY,name TEXT,notes TEXT,cohort TEXT,view TEXT,reaction TEXT,retrieved_at TEXT,created_at TEXT,updated_at TEXT,revision INTEGER)")
                conn.execute("INSERT INTO investigations VALUES (?,?,?,?,?,?,?,?,?,?)",(identifier,"Previous research","Keep these notes",json.dumps(COHORT),"signals","NAUSEA","","now","now",1))
            store=InvestigationStore(path,validate_params)
            previous=store.get(identifier)
            self.assertEqual(previous["notes"],"Keep these notes")
            self.assertEqual(previous["periods"],{})
            payload={key:previous[key] for key in ("id","revision","name","notes","cohort","view","reaction","retrieved_at")}
            payload.update(view="changes",periods=PERIODS)
            saved=store.save(payload)
            reopened=InvestigationStore(path,validate_params).get(identifier)
            self.assertEqual(reopened["periods"],PERIODS)
            self.assertEqual(reopened["view"],"changes")
            self.assertEqual(reopened["notes"],"Keep these notes")
            self.assertEqual(saved["revision"],2)
            with self.assertRaises(InvestigationError):
                store.save({**payload,"periods":{**PERIODS,"baseline_end":"2025-04-01"}})


if __name__=='__main__':
    unittest.main()

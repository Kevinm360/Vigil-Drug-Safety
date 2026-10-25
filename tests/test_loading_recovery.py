import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend import freshness
from backend.server import APIError, DashboardService, OpenFDAClient
from backend.sqlite_cache import SQLiteResponseCache
from test_backend import FakeClient, ComparisonClient

COHORT={"mode":"live","drug":"METFORMIN","compare":"IBUPROFEN","start":"2025-01-01","end":"2025-01-31","age":"All","sex":"Female","reporters":"Physician"}


class SectionTests(unittest.TestCase):
    def test_section_requests_preserve_cohort_and_skip_unrelated_tasks(self):
        client=FakeClient();service=DashboardService(client=client)
        with patch.object(service,'fetch_report_sample',side_effect=AssertionError('Reports must not load for signal retry')):
            core=service.dashboard_section({**COHORT,'section':'core'})
            signal=service.dashboard_section({**COHORT,'section':'signals'})
        self.assertEqual(core['basis'],signal['basis'])
        self.assertEqual(signal['status'],'ready')
        self.assertTrue(signal['data']['signals'])
        self.assertNotIn('severity',signal['data'])
        self.assertNotIn('reports',signal['data'])
        self.assertFalse(any('serious:' in query or 'seriousness' in query for query in client.queries))
        self.assertFalse(any('medicinalproduct:"IBUPROFEN"' in query for query in client.queries))
        self.assertTrue(all('patient.patientsex:2' in query and 'primarysource.qualification:1' in query for query in client.queries))

    def test_signal_failure_is_explicit_and_does_not_break_core(self):
        class Client(FakeClient):
            def aggregate(self,query,field,limit=1000):
                if 'medicinalproduct' not in query and field=='patient.reaction.reactionmeddrapt.exact':
                    raise APIError('Background temporarily unavailable',503)
                return super().aggregate(query,field,limit)
        service=DashboardService(client=Client())
        result=service.dashboard_section({**COHORT,'section':'signals'})
        self.assertEqual(result['status'],'error')
        self.assertIn('Background temporarily unavailable',result['errors'])
        self.assertEqual(service.dashboard_section({**COHORT,'section':'core'})['data']['summary']['total_reports'],10)

    def test_comparison_partial_failure_retains_available_counts_and_true_zero(self):
        service=DashboardService(client=ComparisonClient(compare_total=0,failed={'timeseries'}))
        result=service.dashboard_section({**COHORT,'section':'comparison'})
        self.assertEqual(result['status'],'partial')
        self.assertEqual(result['data']['summary']['compare_total'],0)
        self.assertEqual(result['data']['comparison_reactions'][0]['compare_reports'],0)
        self.assertFalse(result['data']['comparison']['timeseries_available'])
        self.assertTrue(result['data']['comparison']['total_available'])

    def test_changed_counts_change_the_calculation_basis(self):
        client=ComparisonClient();service=DashboardService(client=client)
        first=service.dashboard_section({**COHORT,'section':'core'})
        client.primary_total=0
        second=service.dashboard_section({**COHORT,'section':'signals'})
        self.assertNotEqual(first['basis'],second['basis'])
        self.assertEqual(second['data']['signals'],[])
        with self.assertRaises(APIError):service.dashboard_section({**COHORT,'section':'unknown'})


class ProvenanceTests(unittest.TestCase):
    def test_period_workers_keep_fda_retrieval_provenance(self):
        class Client(FakeClient):
            def count(self,query):
                freshness.record('memory',1000,1300)
                return super().count(query)
            def aggregate(self,query,field,limit=1000):
                freshness.record('memory',1000,1300)
                return super().aggregate(query,field,limit)
        result=DashboardService(client=Client()).period_changes({**COHORT,'baseline_start':'2024-12-01','baseline_end':'2024-12-31'})
        self.assertEqual(result['meta']['freshness']['source'],'cache')
        self.assertEqual(result['meta']['freshness']['memory_hits'],4)

    def test_a_delayed_cache_write_keeps_the_retrieval_time_and_expiry(self):
        with tempfile.TemporaryDirectory() as folder:
            store=SQLiteResponseCache(Path(folder)/'cache.sqlite3',clock=lambda:1002)
            self.assertTrue(store.put('delayed',{'results':[]},300,created_at=1000.9))
            entry=store.get('delayed')
            self.assertEqual(entry.created_at,1000.9)
            self.assertEqual(entry.expires_at,1300.9)

    def test_network_memory_and_sqlite_preserve_the_original_retrieval_time(self):
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,limit):return json.dumps({'results':[{'term':'NAUSEA','count':3}]}).encode()
        with tempfile.TemporaryDirectory() as folder:
            store=SQLiteResponseCache(Path(folder)/'cache.sqlite3')
            client=OpenFDAClient(opener=lambda *args,**kwargs:Response(),cache_store=store)
            with freshness.capture() as trace:client.aggregate('cohort','field')
            original=freshness.describe(trace)
            self.assertEqual(original['source'],'network')
            with freshness.capture() as trace:client.aggregate('cohort','field')
            memory=freshness.describe(trace)
            self.assertEqual(memory['memory_hits'],1)
            self.assertEqual(memory['retrieved_at'],original['retrieved_at'])
            reopened=OpenFDAClient(opener=lambda *args,**kwargs:self.fail('No new FDA request expected'),cache_store=SQLiteResponseCache(store.path))
            with freshness.capture() as trace:reopened.aggregate('cohort','field')
            disk=freshness.describe(trace)
            self.assertEqual(disk['sqlite_hits'],1)
            self.assertEqual(disk['retrieved_at'],original['retrieved_at'])
            self.assertEqual(disk['expires_at'],original['expires_at'])

    def test_worker_requests_share_only_the_current_provenance_context(self):
        with freshness.capture() as trace:
            DashboardService.parallel({'first':lambda:freshness.record('memory',1000,1300),'second':lambda:freshness.record('network',1200,1500)},{'meta':{'warnings':[]}})
        result=freshness.describe(trace)
        self.assertEqual(result['source'],'mixed')
        self.assertEqual(result['requests'],2)
        self.assertEqual(result['retrieved_at'],freshness.timestamp(1000))
        with freshness.capture() as other:self.assertEqual(freshness.describe(other)['source'],'unknown')

import tempfile
import unittest
from backend.server import DashboardService
from backend.web import create_app

class PublicDemoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.service = DashboardService(storage_root=self.tmp.name)
        self.origin = 'https://demo.example'
        self.settings = {'VIGIL_PUBLIC_DEMO':'1','VIGIL_PUBLIC_ORIGIN': self.origin}
        self.client = create_app(self.settings, self.service).test_client()

    def test_anonymous_read_and_mode(self):
        self.assertEqual(self.client.get('/healthz', base_url=self.origin).status_code, 200)
        self.assertEqual(self.client.get('/api/workspace-mode', base_url=self.origin).json, {'public_demo':True})

    def test_no_investigation_reads_or_writes_even_with_credentials(self):
        for path in ['/api/investigations','/api/investigations?id=secret','/api/investigations/history?id=secret']:
            self.assertEqual(self.client.get(path, base_url=self.origin).status_code, 403)
        for path in ['/api/investigations/save','/api/investigations/delete','/api/model/train','/api/narratives','/api/narratives/fetch']:
            self.assertEqual(self.client.post(path, base_url=self.origin,json={}).status_code, 403)

    def test_host_origin_and_private_config_fail_closed(self):
        self.assertEqual(self.client.get('/api/health',base_url='https://evil.example').status_code,403)
        self.assertEqual(self.client.get('/api/health',base_url=self.origin,headers={'Origin':'https://evil.example'}).status_code,403)
        for extra in [{'VIGIL_AUTH_USER':'owner'},{'VIGIL_DATABASE_URL':'private'}, {'VIGIL_PUBLIC_ORIGIN':''}]:
            with self.assertRaises(ValueError): create_app({**self.settings,**extra},self.service)

    def test_global_budget_is_bounded(self):
        for _ in range(60):
            self.assertEqual(self.client.get('/api/health',base_url=self.origin).status_code,200)
        response=self.client.get('/api/health',base_url=self.origin)
        self.assertEqual(response.status_code,429)
        self.assertEqual(response.headers['Retry-After'],'15')

if __name__ == '__main__': unittest.main()

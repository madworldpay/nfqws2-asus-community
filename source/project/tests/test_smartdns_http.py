"""Exercise the actual router route; only detach/download is substituted."""
import unittest
import test_support_mail_api as mail_api
from test_dpi_normalize import PUBLIC


class SmartDnsHttpTests(unittest.TestCase):
    def setUp(self):
        self.fixture = mail_api.SupportMailApiTests('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.base = self.fixture.base
        for name in ['smartdns-api.php','smartdns-install.php','dpi-install.php','openwrt-dpi.php','dpi-runtime.php','dpi-store.php','dpi-catalog.php','dpi-options.php']:
            (self.base/name).write_text((PUBLIC/name).read_text())
        p=self.base/'smartdns-api.php'
        p.write_text(p.read_text().replace('$jobs=new AsusSmartDnsJobs();', '''$jobs=new AsusSmartDnsJobs(
            new AsusSmartDnsInstaller(__DIR__.'/engine',fileowner(__DIR__),['version'=>'1.2026.08.05-0921']),
            ['available'=>fn()=>['available'=>true,'code'=>'ready'],'launch'=>function($id){file_put_contents(__DIR__.'/launched',$id);}]);'''))

    def test_login_csrf_origin_and_consent_are_required_before_launch(self):
        request=self.fixture.request
        post={'cmd':'smartdnsinstall','request_id':'a'*32,'consent':'install','csrf_token':'bad'}
        self.assertEqual(request(post)[0],401)
        token=self.fixture.login();post['csrf_token']=token
        self.assertEqual(request(post|{'csrf_token':'bad'})[0],403)
        self.fixture.origin='https://evil.invalid'
        self.assertEqual(request(post)[0],403)
        self.fixture.origin='http://localhost'
        for value in [post|{'url':'https://evil.invalid'},post|{'consent':'no'}]:
            self.assertEqual(request(value)[0],400)
        self.assertFalse((self.base/'launched').exists())
        self.assertEqual(request(post)[0],200)
        self.assertEqual((self.base/'launched').read_text(),'a'*32)

    def test_package_update_lock_blocks_install_but_not_status(self):
        token=self.fixture.login();(self.base/'update-busy').touch()
        post={'cmd':'smartdnsinstall','request_id':'a'*32,'consent':'install','csrf_token':token}
        self.assertEqual(self.fixture.request(post)[0],409)
        self.assertFalse((self.base/'launched').exists())
        code,data=self.fixture.request({'cmd':'smartdnsstatus','csrf_token':token})
        self.assertEqual(code,200)
        self.assertIsNone(data['job'])

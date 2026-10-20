"""Use the real authenticated route; substitute only local paths and launching."""
import json
import unittest
import test_support_mail_api as mail_api
from test_dpi_normalize import PUBLIC
from test_smartdns_profile import profile

class SmartDnsConfigHttpTests(unittest.TestCase):
    def setUp(self):
        self.fixture=mail_api.SupportMailApiTests('runTest');self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.base=self.fixture.base
        for f in PUBLIC.glob('*.php'):
            if not (self.base/f.name).exists():
                (self.base/f.name).write_text(f.read_text())
        path=self.base/'index.php';text=path.read_text()
        text=text.replace('AsusSmartDnsConfigApi::dispatch($_POST)', '''AsusSmartDnsConfigApi::dispatch($_POST,[
          'writer'=>fn($fn)=>(new AsusImportStore(__DIR__.'/import-state',fileowner(__DIR__)))->locked($fn),
          'store'=>new AsusSmartDnsStore(__DIR__.'/dns-state',fileowner(__DIR__)),
          'jobs_deps'=>['owner'=>fileowner(__DIR__),'native'=>fn()=>null,'baseline'=>fn()=>['hash'=>str_repeat('a',64)],
            'lease'=>fn()=>fopen(__DIR__.'/lease','c'),
            'launch'=>function($id){file_put_contents(__DIR__.'/launched',$id);},
            'validation_owner'=>fn($job)=>['known'=>true,'guard_alive'=>is_file(__DIR__.'/launched'),'anchor_alive'=>is_file(__DIR__.'/launched'),'worker_alive'=>false,'code'=>null]],
          'lease'=>function(){if(file_exists(__DIR__.'/update-busy'))throw new RuntimeException('busy');return fopen(__DIR__.'/lease','c');}
        ])''')
        path.write_text(text)

    def test_auth_csrf_origin_and_closed_keys_before_any_draft_or_launch(self):
        request=self.fixture.request;post={'cmd':'smartdnsdraft','csrf_token':'bad','profile':json.dumps(profile())}
        self.assertEqual(request(post)[0],401);token=self.fixture.login();post['csrf_token']=token
        self.assertEqual(request(post|{'csrf_token':'bad'})[0],403)
        self.fixture.origin='https://evil.invalid';self.assertEqual(request(post)[0],403);self.fixture.origin='http://localhost'
        self.assertEqual(request(post|{'shell':'PRIVATE_CANARY'})[0],400)
        self.assertFalse((self.base/'dns-state').exists())
        code,result=request(post);self.assertEqual(code,200);self.assertEqual(len(result['profile_hash']),64)
        code,data=request({'cmd':'smartdnsvalidate','csrf_token':token,'request_id':'c'*32,'profile_hash':result['profile_hash']})
        self.assertEqual(code,200);self.assertEqual(data['state'],'validating');self.assertEqual((self.base/'launched').read_text(),'c'*32)

    def test_status_is_readonly_and_draft_mutation_is_blocked_during_update(self):
        token=self.fixture.login();(self.base/'update-busy').touch()
        code,result=self.fixture.request({'cmd':'smartdnsconfigstatus','csrf_token':token})
        self.assertEqual(code,200);self.assertEqual(result['status']['state'],'idle');self.assertIsNone(result['draft'])
        self.assertFalse((self.base/'dns-state').exists())
        self.assertEqual(self.fixture.request({'cmd':'smartdnsdraft','csrf_token':token,'profile':json.dumps(profile())})[0],409)
        self.assertFalse((self.base/'dns-state').exists())

    def test_preview_cannot_be_read_before_successful_validation(self):
        token=self.fixture.login();code,data=self.fixture.request({'cmd':'smartdnspreview','csrf_token':token,'preview_id':'b'*32})
        self.assertEqual(code,409);self.assertEqual(data,{'error':'stale_preview'})



    def test_wan_read_requires_auth_csrf_origin_and_does_not_create_dns_jobs(self):
        request=self.fixture.request;post={'cmd':'wanaddresses','csrf_token':'bad'}
        self.assertEqual(request(post)[0],401)
        token=self.fixture.login();post['csrf_token']=token
        self.assertEqual(request(post|{'csrf_token':'bad'})[0],403)
        self.fixture.origin='https://evil.invalid';self.assertEqual(request(post)[0],403);self.fixture.origin='http://localhost'
        self.assertEqual(request(post|{'interface':'PRIVATE_CANARY'})[0],400)
        code,data=request(post);self.assertEqual(code,200)
        self.assertEqual(data['schema_version'],1);self.assertIsInstance(data['addresses'],list)
        self.assertFalse((self.base/'dns-state').exists());self.assertFalse((self.base/'launched').exists())

if __name__=='__main__':unittest.main()

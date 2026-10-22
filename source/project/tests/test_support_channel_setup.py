"""Connecting the packaged public channel is explicit, closed and never sends."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_package_update_guard import NATIVE
from test_dpi_normalize import PUBLIC,ROOT

@unittest.skipUnless(NATIVE.is_file(),'native PHP fixture required')
class SupportChannelSetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name);self.base.chmod(0o700)
        self.config=self.base/'support-relay.json';self.template=self.base/'factory.json';self.raw=(ROOT/'asus/support-relay.json').read_bytes();self.template.write_bytes(self.raw);self.template.chmod(0o644)
    def call(self,action,disable=""):
        code='''$p=$argv[1].'/support-channel-setup.php';if(!is_file($p)){echo json_encode(['error'=>'missing_setup']);exit;}require $p;
        try{$v=new AsusSupportChannelSetup($argv[2],$argv[3],(int)$argv[4]);echo json_encode(['value'=>$v->{$argv[5]}()]);}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        p=subprocess.run([str(NATIVE),'-n','-d','allow_url_fopen=0','-d','disable_functions='+disable,'-r',code,str(PUBLIC),str(self.config),str(self.template),str(os.getuid()),action],capture_output=True,text=True,timeout=5)
        self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(p.stderr,'');return json.loads(p.stdout)
    def write(self,raw):self.config.write_bytes(raw);self.config.chmod(0o600)
    def test_legacy_or_missing_channel_needs_explicit_connect_and_is_idempotent(self):
        for old in [None,b'{"enabled":false,"url":""}\n']:
            if old is None:
                if self.config.exists():self.config.unlink()
            else:self.write(old)
            self.assertEqual(self.call('available'),{'value':True});self.assertEqual(self.config.read_bytes() if self.config.exists() else None,old)
            self.assertEqual(self.call('connect'),{'value':{'connected':True}});self.assertEqual(self.config.read_bytes(),self.raw);self.assertEqual(self.config.stat().st_mode&0o777,0o600)
            self.assertEqual(self.call('available'),{'value':False});self.assertEqual(self.call('connect'),{'value':{'connected':True}})
    def test_custom_disabled_enabled_and_malformed_are_never_overridden(self):
        for raw in [b'{"enabled":false,"url":"https://operator.example/nfqws-support/v1/reports"}',b'{"enabled":true,"url":"https://operator.example/nfqws-support/v1/reports"}',b'{"enabled":false,"url":"","sharing_v4_enabled":false}',b'INVALID']:
            with self.subTest(raw=raw):
                self.write(raw);self.assertEqual(self.call('available'),{'value':False});self.assertIn('error',self.call('connect'));self.assertEqual(self.config.read_bytes(),raw)
    def test_template_hash_permissions_and_links_cannot_supply_a_different_endpoint(self):
        self.write(b'{"enabled":false,"url":""}\n')
        for raw,mode in [(b'{"enabled":true,"url":"https://evil.invalid/nfqws-support/v1/reports"}',0o644),(self.raw,0o666)]:
            self.template.write_bytes(raw);self.template.chmod(mode);self.assertEqual(self.call('available'),{'value':False});self.assertIn('error',self.call('connect'));self.assertFalse(json.loads(self.config.read_text())['enabled'])
        self.template.unlink();self.template.symlink_to(self.config);self.assertIn('error',self.call('connect'))
    def test_interrupted_publication_leaves_legacy_choice_and_retries_safely(self):
        old=b'{"enabled":false,"url":""}\n';self.write(old);self.assertIn('error',self.call('connect','fsync'));self.assertEqual(self.config.read_bytes(),old)
        self.assertEqual(list(self.base.glob('.support-relay-*')),[]);self.assertEqual(self.call('connect'),{'value':{'connected':True}})
    def test_config_link_and_lock_tampering_fail_without_writing(self):
        outside=self.base/'outside';outside.write_bytes(b'KEEP');self.config.symlink_to(outside);self.assertEqual(self.call('available'),{'value':False});self.assertIn('error',self.call('connect'));self.assertEqual(outside.read_bytes(),b'KEEP')
        self.config.unlink();self.write(b'{"enabled":false,"url":""}\n');lock=self.base/'support-relay-setup.lock';lock.symlink_to(outside);self.assertIn('error',self.call('connect'));self.assertEqual(outside.read_bytes(),b'KEEP')


# Exercise the real index.php authorization/CSRF/command boundary. Only paths and
# the update admission fixture are substituted; no mail transport is invoked.
import test_auth_api as auth
import test_share_router_http as share_http

@unittest.skipUnless(auth.PHP,'matching PHP runtime required for HTTP authorization')
class SupportChannelRouterTests(unittest.TestCase):
    login=auth.PasswordApiTests.login
    request=share_http.ShareRouterTests.request
    def setUp(self):
        auth.PasswordApiTests.setUp(self);self.origin='http://localhost';self.base.chmod(0o700)
        self.active=self.base/'relay.json';self.active.write_bytes(b'{"enabled":false,"url":""}\n');self.active.chmod(0o600)
        self.factory=self.base/'factory.json';self.factory.write_bytes((ROOT/'asus/support-relay.json').read_bytes());self.factory.chmod(0o644)
        for p in PUBLIC.glob('*.php'):
            if p.name in ['index.php','asus.php','ark.php','update-guard.php']:continue
            text=p.read_text().replace("dirname(__DIR__,3).'/support'",repr(str(ROOT/'support')))
            if p.name=='support-channel-setup.php':
                text=text.replace('private ?string $config=null', 'private ?string $config='+repr(str(self.active))).replace('private ?string $template=null','private ?string $template='+repr(str(self.factory))).replace('private int $owner=0','private int $owner='+str(os.getuid()))
            (self.base/p.name).write_text(text)
    def test_connect_requires_auth_csrf_origin_no_url_and_update_admission(self):
        params={'cmd':'sharechannelconnect','csrf_token':'bad'}
        self.assertEqual(self.request(params)[0],401);token=self.login()
        self.assertEqual(self.request(params)[0],403);params['csrf_token']=token
        self.origin='https://evil.invalid';self.assertEqual(self.request(params)[0],403);self.origin='http://localhost'
        self.assertEqual(self.request(params|{'url':'https://evil.invalid'})[0],400)
        (self.base/'update-busy').touch();self.assertEqual(self.request(params)[0],409);(self.base/'update-busy').unlink()
        self.assertFalse(json.loads(self.active.read_text())['enabled']);self.assertEqual(self.request(params),(200,{'connected':True}));self.assertEqual(self.request(params),(200,{'connected':True}))
        self.assertEqual(self.active.read_bytes(),self.factory.read_bytes());self.assertFalse((self.base/'sent-share.json').exists())
    def test_explicit_custom_disabled_cannot_be_replaced_even_via_direct_api(self):
        raw=b'{"enabled":false,"url":"https://operator.example/nfqws-support/v1/reports"}\n';self.active.write_bytes(raw)
        token=self.login();code,value=self.request({'cmd':'sharechannelconnect','csrf_token':token});self.assertEqual(code,503);self.assertNotIn('url',json.dumps(value));self.assertEqual(self.active.read_bytes(),raw)

if __name__=='__main__':unittest.main()

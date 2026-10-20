"""Real PHP router authorization/proof boundary, with SMTP alone substituted."""
import json,os,subprocess,unittest,urllib.parse,uuid
import test_auth_api as auth
from test_dpi_normalize import PHP,PUBLIC,ROOT
from test_share_bundle_api import share_files

class ShareRouterTests(unittest.TestCase):
    login=auth.PasswordApiTests.login
    change=auth.PasswordApiTests.change
    def setUp(self):
        auth.PasswordApiTests.setUp(self);self.origin='http://localhost'
        for p in PUBLIC.glob('*.php'):
            if p.name in ['index.php','asus.php','ark.php','update-guard.php']:continue
            s=p.read_text().replace("dirname(__DIR__,3).'/support'",repr(str(ROOT/'support')))
            if p.name=='share-api.php':
                s=s.replace('new AsusShareResources()','new AsusShareResources(__DIR__ . "/resources",fileowner(__DIR__))').replace('new AsusShareDns()','new AsusShareDns(__DIR__ . "/missing-smartdns.conf",fileowner(__DIR__))')
            (self.base/p.name).write_text(s)
        (self.base/'resources').mkdir(mode=0o755)
        (self.base/'support-mail.php').write_text('''<?php class AsusSupportMail {
        function shareAvailability(){return ['configured'=>true,'sharing_v3'=>true,'code'=>'ready'];}
        function sendShare($raw,$id){file_put_contents(__DIR__.'/sent-share.json',$raw);return ['state'=>'accepted','code'=>'smtp_accepted','submission_id'=>$id];}
        }''')
    def request(self,params,session='user-one'):
        code='''ini_set('session.save_path',$argv[1]);session_name('nfqws_asus_session');session_id($argv[2]);session_start();session_write_close();
        $_SERVER['REQUEST_METHOD']='POST';$_SERVER['HTTP_HOST']='localhost';$_SERVER['HTTP_ORIGIN']=$argv[3];$_POST=json_decode(stream_get_contents(STDIN),true);
        register_shutdown_function(function(){echo '\nHTTP_META='.json_encode(['code'=>http_response_code(),'session'=>session_id()]);});require $argv[1].'/index.php';'''
        p=subprocess.run([PHP,'-n','-r',code,str(self.base),self.sessions.get(session,session),self.origin],input=json.dumps(params),capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr+p.stdout);self.assertEqual(p.stderr,'')
        body,meta=p.stdout.rsplit('\nHTTP_META=',1);meta=json.loads(meta);self.sessions[session]=meta['session'] or session
        return int(meta['code']),json.loads(body) if body else None
    def signed(self,token,session='user-one'):
        sid=str(uuid.uuid4());files=share_files(('strategy',))
        code='''ini_set('session.save_path',$argv[1]);session_name('nfqws_asus_session');session_id($argv[2]);session_start();$_SESSION['support_report_key']=str_repeat('a',64);session_write_close();require $argv[1].'/share-bundle.php';echo AsusShareBundle::prepare(json_decode(stream_get_contents(STDIN),true),str_repeat('a',64),time())['proof'];'''
        p=subprocess.run([PHP,'-n','-r',code,str(self.base),self.sessions[session]],input=json.dumps(files),capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        return {'cmd':'sharesend','csrf_token':token,'consent':'send','submission_id':sid,'proof':p.stdout,'envelope':json.dumps({'version':3,'submission_id':sid,'files':files})}
    def test_shared_send_requires_auth_origin_csrf_consent_and_own_snapshot(self):
        self.assertEqual(self.request({'cmd':'sharesend','csrf_token':'bad'})[0],401)
        token=self.login();params=self.signed(token)
        self.assertEqual(self.request(params|{'csrf_token':'bad'})[0],403)
        self.origin='https://evil.invalid';self.assertEqual(self.request(params)[0],403);self.origin='http://localhost'
        self.assertEqual(self.request(params|{'consent':'no'})[0],400)
        self.assertEqual(self.request(params|{'url':'https://evil.invalid'})[0],400)
        forged=params['proof'][:-1]+('0' if params['proof'][-1]!='0' else '1')
        self.assertEqual(self.request(params|{'proof':forged})[0],403)
        self.assertFalse((self.base/'sent-share.json').exists())
        code,v=self.request(params);self.assertEqual((code,v['state']),(200,'accepted'))
        self.assertEqual((self.base/'sent-share.json').read_text(),params['envelope'])
    def test_disabled_password_still_requires_own_session_and_csrf(self):
        token=self.login();self.change('',token)
        token=self.request({'cmd':'login'},'visitor')[1]['csrf_token'];params=self.signed(token,'visitor')
        self.assertEqual(self.request(params,'other')[0],403)
        self.assertEqual(self.request(params,'visitor')[0],200)
    def test_old_start_cannot_launch_and_updater_blocks_new_mutations(self):
        token=self.login()
        p={'cmd':'dpistart','csrf_token':token,'request_id':'11111111-1111-4111-8111-111111111111','tests':'12','heavy_consent':''}
        code,v=self.request(p);self.assertEqual((code,v['error']),(410,'workflow_changed'))
        (self.base/'update-busy').touch()
        self.assertEqual(self.request({'cmd':'sharesavedrefresh','csrf_token':token})[0],409)
    def test_real_cgi_shared_send_preserves_exact_preview_bytes(self):
        cgi=os.environ.get('PHP_CGI_TEST_BINARY')
        if not cgi:self.skipTest('matching CGI runtime required')
        token=self.login();params=self.signed(token);data=urllib.parse.urlencode(params)
        env=os.environ|{'REDIRECT_STATUS':'200','SCRIPT_FILENAME':str(self.base/'index.php'),'REQUEST_METHOD':'POST','CONTENT_TYPE':'application/x-www-form-urlencoded','CONTENT_LENGTH':str(len(data.encode())),'HTTP_HOST':'localhost','HTTP_ORIGIN':'http://localhost','HTTP_COOKIE':'nfqws_asus_session='+self.sessions['user-one'],'QUERY_STRING':''}
        p=subprocess.run([cgi,'-n','-d','session.save_path='+str(self.base)],input=data,text=True,capture_output=True,env=env)
        self.assertEqual(p.returncode,0,p.stderr+p.stdout)
        head,body=p.stdout.split('\n\n',1);self.assertIn('Cache-Control: no-store',head)
        self.assertEqual(json.loads(body)['state'],'accepted')
        self.assertEqual((self.base/'sent-share.json').read_text(),params['envelope'])

    def test_resource_commands_share_same_auth_origin_and_csrf_boundary(self):
        params={'cmd':'shareanalyze','csrf_token':'bad','selection':json.dumps({'resource_ids':[]})}
        self.assertEqual(self.request(params)[0],401)
        token=self.login()
        self.assertEqual(self.request(params)[0],403)
        params['csrf_token']=token
        self.origin='https://evil.invalid';self.assertEqual(self.request(params)[0],403);self.origin='http://localhost'
        code,value=self.request(params);self.assertEqual(code,200);self.assertTrue(value['audit']['complete']);self.assertEqual(value['audit']['scope'],'files_only')
        self.assertEqual(self.request(params|{'path':'/etc/shadow'})[0],400)

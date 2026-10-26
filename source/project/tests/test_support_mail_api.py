import base64
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.parse
import uuid

import test_auth_api as auth_api
import test_support_report_api as report_api
from test_support_relay_validation import fixture, FILENAME


PHP,ROOT=report_api.PHP,report_api.ROOT


class SupportMailApiTests(auth_api.PasswordApiTests):
    __unittest_skip__=False

    def request(self,params,session='user-one'):
        code='''ini_set('session.save_path',$argv[1]);session_name('nfqws_asus_session');session_id($argv[2]);session_start();session_write_close();
        $_SERVER['REQUEST_METHOD']='POST';$_SERVER['HTTP_HOST']='localhost';$_SERVER['HTTP_ORIGIN']=$argv[3];
        $_POST=json_decode(stream_get_contents(STDIN),true);
        register_shutdown_function(function(){echo '\\nHTTP_META='.json_encode(['code'=>http_response_code(),'session'=>session_id()]);});
        require $argv[1].'/index.php';'''
        r=subprocess.run([PHP,'-n','-r',code,str(self.base),self.sessions.get(session,session),self.origin],input=json.dumps(params),capture_output=True,text=True,timeout=25)
        self.assertEqual(r.returncode,0,r.stderr+r.stdout);self.assertEqual(r.stderr,'')
        body,meta=r.stdout.rsplit('\\nHTTP_META=',1);meta=json.loads(meta)
        self.sessions[session]=meta['session'] or session
        return int(meta['code']),json.loads(body) if body else None

    def setUp(self):
        super().setUp()
        self.origin='http://localhost'
        for source in (ROOT/'webui/web/public').glob('support-*.php'):
            (self.base/source.name).write_text(source.read_text())
        for name in ['smartdns-report.php','smartdns-store.php','smartdns-profile.php','smartdns-install.php','dpi-store.php','dpi-install.php','openwrt-dpi.php','dpi-runtime.php','dpi-catalog.php','dpi-options.php']:
            (self.base/name).write_text((ROOT/'webui/web/public'/name).read_text())
        self.marker=self.base/'sent.json'
        (self.base/'support-mail.php').write_text('''<?php
        class AsusSupportMail {
          function availability(){return ['configured'=>true,'code'=>'ready'];}
          function send($raw,$filename,$id){
            file_put_contents(__DIR__.'/sent.json',json_encode([base64_encode($raw),$filename,$id]));
            if(file_exists(__DIR__.'/delay'))usleep(2000000);
            return ['state'=>'accepted','submission_id'=>$id,'code'=>'smtp_accepted'];
          }
        }''')

    def signed(self, token, session='user-one'):
        raw=fixture().decode()
        code='''ini_set('session.save_path',$argv[1]);session_name('nfqws_asus_session');session_id($argv[2]);session_start();
        $_SESSION['support_report_key']=str_repeat('a',64);session_write_close();
        require $argv[1].'/support-mail-proof.php';echo AsusReportProof::issue($argv[3],$argv[4],str_repeat('a',64),time());'''
        proof=subprocess.check_output([PHP,'-n','-r',code,str(self.base),self.sessions[session],raw,FILENAME],text=True)
        return {'cmd':'supportsend','csrf_token':token,'consent':'send','filename':FILENAME,
                'report':raw,'report_proof':proof,'submission_id':str(uuid.uuid4())}

    def test_mail_status_auth_exact_fields_csrf_and_origin(self):
        self.assertEqual(self.request({'cmd':'supportmailstatus','csrf_token':'bad'})[0],401)
        token=self.login()
        self.assertEqual(self.request({'cmd':'supportmailstatus','csrf_token':token}), (200,{'configured':True,'code':'ready'}))
        self.assertEqual(self.request({'cmd':'supportmailstatus','csrf_token':token,'url':'https://PRIVATE_CANARY'})[0],400)
        self.assertEqual(self.request({'cmd':'supportmailstatus','csrf_token':'bad'})[0],403)
        self.origin='http://evil.invalid'
        self.assertEqual(self.request({'cmd':'supportmailstatus','csrf_token':token})[0],403)
        self.assertFalse(self.marker.exists())

    def test_only_explicit_consent_and_unmodified_session_proof_can_send(self):
        token=self.login(); params=self.signed(token)
        for key,value,code in [('consent','',400),('consent',None,400),('report',params['report']+' ',403),
                               ('report_proof','v1.bad',403),('csrf_token','bad',403),
                               ('filename',FILENAME+'\r\nPRIVATE_CANARY',400),('submission_id','bad',400),
                               ('report',' '*1048577,400)]:
            bad=params.copy()
            if value is None: del bad[key]
            else: bad[key]=value
            self.assertEqual(self.request(bad)[0],code)
            self.assertFalse(self.marker.exists())
        self.assertEqual(self.request(params|{'url':'https://PRIVATE_CANARY'})[0],400)
        code,result=self.request(params)
        self.assertEqual((code,result['state']),(200,'accepted'))
        sent=json.loads(self.marker.read_text())
        self.assertEqual(base64.b64decode(sent[0]),params['report'].encode())
        self.assertEqual(sent[1:], [FILENAME,params['submission_id']])

    def test_anonymous_mode_still_needs_session_csrf_and_its_own_proof(self):
        token=self.login(); self.change('',token)
        token=self.request({'cmd':'login'},'visitor')[1]['csrf_token']
        params=self.signed(token,'visitor')
        self.assertEqual(self.request(params,'other')[0],403)
        self.assertFalse(self.marker.exists())
        self.assertEqual(self.request(params,'visitor')[0],200)

    def test_send_releases_session_before_waiting_for_transport(self):
        token=self.login(); params=self.signed(token); (self.base/'delay').touch()
        code='''ini_set('session.save_path',$argv[1]);session_name('nfqws_asus_session');session_id($argv[2]);
        $_SERVER['REQUEST_METHOD']='POST';$_SERVER['HTTP_HOST']='localhost';$_SERVER['HTTP_ORIGIN']='http://localhost';
        $_POST=json_decode($argv[3],true);require $argv[1].'/index.php';'''
        process=subprocess.Popen([PHP,'-n','-r',code,str(self.base),self.sessions['user-one'],json.dumps(params)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            until=time.monotonic()+5
            while not self.marker.exists() and time.monotonic()<until:time.sleep(.02)
            self.assertTrue(self.marker.exists())
            start=time.monotonic(); self.assertEqual(self.request({'cmd':'login'})[0],200)
            self.assertLess(time.monotonic()-start,1)
            out,err=process.communicate(timeout=5)
            self.assertEqual(err,b'');self.assertEqual(json.loads(out)['state'],'accepted')
        finally:
            if process.poll() is None:process.kill();process.communicate()

    def test_real_cgi_sends_signed_bytes_and_safe_response(self):
        cgi=os.environ.get('PHP_CGI_TEST_BINARY')
        if not cgi:self.skipTest('matching PHP CGI runtime required')
        token=self.login();params=self.signed(token)
        data=urllib.parse.urlencode(params)
        env=os.environ|{'REDIRECT_STATUS':'200','SCRIPT_FILENAME':str(self.base/'index.php'),
                        'REQUEST_METHOD':'POST','CONTENT_TYPE':'application/x-www-form-urlencoded',
                        'CONTENT_LENGTH':str(len(data)),'HTTP_HOST':'localhost','HTTP_ORIGIN':'http://localhost',
                        'HTTP_COOKIE':'nfqws_asus_session='+self.sessions['user-one'],'QUERY_STRING':''}
        r=subprocess.run([cgi,'-n','-d','session.save_path='+str(self.base)],input=data,text=True,capture_output=True,env=env,timeout=10)
        self.assertEqual(r.returncode,0,r.stderr+r.stdout);self.assertEqual(r.stderr,'')
        headers,body=r.stdout.split('\n\n',1)
        self.assertIn('Cache-Control: no-store',headers)
        self.assertNotIn('Status: 4',headers)
        self.assertEqual(json.loads(body),{'state':'accepted','submission_id':params['submission_id'],'code':'smtp_accepted'})
        self.assertEqual(base64.b64decode(json.loads(self.marker.read_text())[0]),params['report'].encode())

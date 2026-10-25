"""Authenticated native panel requests in an isolated official rootfs only."""
import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]
CONTAINER=os.environ.get('NFQWS_TEST_DOCKER')

@unittest.skipUnless(CONTAINER,'Requires an isolated OpenWrt test container')
class NativeWebRequests(unittest.TestCase):
    @classmethod
    def sh(cls,script,input=None):
        return subprocess.run(['docker','exec','-i',CONTAINER,'sh','-c',script],input=input,text=True,
                              capture_output=True,check=True,timeout=30)

    @classmethod
    def setUpClass(cls):
        spec=json.loads(subprocess.check_output(['docker','inspect',CONTAINER]))[0]
        if not CONTAINER.startswith('nfqws-openwrt') or spec['HostConfig']['NetworkMode']=='host':
            raise RuntimeError('Refusing a non-test or host-network container')
        cls.base='/tmp/nfqws-native-web-fixture'
        cls.sh('mkdir -p '+cls.base+' /etc/nfqws2/lists /etc/nfqws2/lua; chmod 700 '+cls.base)
        for p in (ROOT/'webui/web/public').glob('*.php'):
            source=p.read_text()
            if p.name=='asus.php':
                for a,b in [('/opt/etc/nfqws-asus-web/auth.json',cls.base+'/auth.json'),('/etc/passwd',cls.base+'/passwd'),('/etc/shadow',cls.base+'/shadow')]:source=source.replace(a,b)
            cls.sh('cat > '+cls.base+'/'+p.name,input=source)
        for name,value in [('platform-profile.json','{"schema_version":1,"platform":"openwrt"}'),
                           ('index.html','<!doctype html><html><body>native-shell-version</body></html>'),
                           ('auth.json','{"mode":"system","username":"root","password_hash":""}'),
                           ('passwd','root:x:0:0:root:/root:/bin/ash\n')]:
            cls.sh('cat > '+cls.base+'/'+name,input=value)
        cls.sh("php-cli -r 'echo \"root:\",crypt(\"native-test-password\",\"\\$6\\$native-http\\$\"),\":0:0:99999:7:::\\n\";' > "+cls.base+'/shadow')
        cls.sh('chmod 600 '+cls.base+'/*; printf "USER=nobody\\nNFQUEUE_NUM=300\\n" > /etc/nfqws2/nfqws2.conf; chmod 600 /etc/nfqws2/nfqws2.conf')

    def request(self,post,session='native-web-tests'):
        code='''ini_set('session.save_path',$argv[1]);session_id($argv[2]);
$_SERVER['REQUEST_METHOD']='POST';$_SERVER['HTTP_HOST']='localhost';$_SERVER['HTTP_ORIGIN']='http://localhost';$_POST=json_decode($argv[3],true);
register_shutdown_function(function(){echo "\\nHTTP_META=".json_encode(['code'=>http_response_code(),'session'=>session_id()]);});
require $argv[1].'/index.php';'''
        r=subprocess.run(['docker','exec',CONTAINER,'php-cli','-r',code,self.base,getattr(self,'session',session),json.dumps(post)],text=True,capture_output=True,timeout=30)
        self.assertEqual(r.returncode,0,r.stderr+r.stdout[-1000:]);self.assertEqual(r.stderr,'')
        body,meta=r.stdout.rsplit('\nHTTP_META=',1);meta=json.loads(meta);self.session=meta['session']
        return meta['code'],json.loads(body)if body else None

    def login(self):
        status,data=self.request({'cmd':'login','user':'root','password':'native-test-password'})
        self.assertEqual(status,200);return data['csrf_token']

    def test_native_auth_config_and_status(self):
        self.session='native-read';self.login()
        status,data=self.request({'cmd':'filecontent','filename':'nfqws2.conf'})
        self.assertEqual(status,200);self.assertIn('NFQUEUE_NUM=300',data['content'])
        status,data=self.request({'cmd':'status'})
        self.assertEqual(status,200);self.assertFalse(data['service']);self.assertFalse(data['ark_loaded'])
        self.assertEqual(data['platform'],'openwrt')
        _,checkup=self.request({'cmd':'routercheckup','csrf_token':data['csrf_token']})
        platform=next(x['facts']for x in checkup['items']if x['id']=='platform')
        self.assertEqual(platform['package_arch'],'x86_64')

    def test_unconfigured_native_auth_reports_setup_instead_of_opening_panel(self):
        shadow=self.sh('cat '+self.base+'/shadow').stdout
        self.sh('cat > '+self.base+'/shadow',input='root::0:0:99999:7:::\n')
        try:
            code,data=self.request({'cmd':'status'},'native-unconfigured')
            self.assertEqual(code,503);self.assertEqual(data,{'error':'auth_unconfigured'})
        finally:self.sh('cat > '+self.base+'/shadow',input=shadow)

    def test_native_shell_is_served_without_stale_html_validators(self):
        r=subprocess.run(['docker','exec','-e','REQUEST_METHOD=GET','-e','REDIRECT_STATUS=200',
                          '-e','SCRIPT_FILENAME='+self.base+'/index.php','-e','HTTP_IF_MODIFIED_SINCE=Thu, 01 Jan 1970 00:00:00 GMT',
                          CONTAINER,'php-cgi'],text=True,capture_output=True,timeout=15)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('Cache-Control: no-store',r.stdout)
        self.assertIn('native-shell-version',r.stdout)
        self.assertNotIn('Location:',r.stdout)

    def test_native_file_writer_and_symlink_rejection(self):
        self.session='native-write';token=self.login()
        for post in [{'cmd':'filecreate','filename':'native-http.list'},
                     {'cmd':'filesave','filename':'native-http.list','content':'example.org'}]:
            code,data=self.request(post|{'csrf_token':token});self.assertEqual((code,data['status']),(200,0))
        self.assertEqual(self.sh('cat /etc/nfqws2/lists/native-http.list').stdout,'example.org\n')
        code,data=self.request({'cmd':'fileremove','filename':'native-http.list','csrf_token':token})
        self.assertEqual((code,data['status']),(200,0))
        self.sh('ln -sf /etc/passwd /etc/nfqws2/lists/native-http-alias.list')
        try:
            code,_=self.request({'cmd':'filecontent','filename':'native-http-alias.list'})
            self.assertEqual(code,400)
        finally:self.sh('rm -f /etc/nfqws2/lists/native-http-alias.list')

if __name__=='__main__':unittest.main()

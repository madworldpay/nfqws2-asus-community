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
        cls.sh('mkdir -p '+cls.base+' /etc/nfqws2/lists /etc/nfqws2/lua /etc/nfqws2/blobs /usr/share/nfqws2; chmod 700 '+cls.base+'; rm -rf /tmp/nfqws2-native-state')
        for p in (ROOT/'webui/web/public').glob('*.php'):
            source=p.read_text()
            if p.name=='asus.php':
                for a,b in [('/opt/etc/nfqws-asus-web/auth.json',cls.base+'/auth.json'),('/etc/passwd',cls.base+'/passwd'),('/etc/shadow',cls.base+'/shadow')]:source=source.replace(a,b)
            cls.sh('cat > '+cls.base+'/'+p.name,input=source)
        for p in (ROOT/'support').glob('*.json'):cls.sh('cat > /usr/share/nfqws2/'+p.name,input=p.read_text())
        from test_openwrt_builder import builder
        cls.sh('mkdir -p /usr/share/nfqws2/defaults; cat > /usr/share/nfqws2/defaults/nfqws2.conf',input=builder.native_defaults().decode())
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

    def test_native_export_uses_the_saved_native_configuration(self):
        self.session='native-export';token=self.login()
        code,draft=self.request({'cmd':'sharestrategydraft','csrf_token':token})
        self.assertEqual(code,200,draft)
        self.assertIn('NFQUEUE_NUM=300',draft['config'])

    def test_native_reset_reads_the_packaged_default_template(self):
        self.session='native-defaults';self.login()
        code,default=self.request({'cmd':'filecontent','filename':'nfqws2.conf.notactive'})
        self.assertEqual(code,200);self.assertIn('/etc/nfqws2/lua/zapret-lib.lua',default['content'])
        self.assertNotIn('/opt/',default['content'])

    def test_native_dpi_metadata_reads_installed_native_defaults(self):
        self.session='native-dpi-metadata';token=self.login()
        code,value=self.request({'cmd':'dpimetadata','csrf_token':token})
        self.assertEqual(code,200,value);self.assertIn('MAX_CONCURRENT',value['config']);self.assertIn('rustls',value['fingerprints'])

    def test_native_strategy_export_binds_files_and_omits_packaged_lua(self):
        import base64,hashlib
        self.session='native-export-resources';token=self.login()
        before=self.sh('cat /etc/nfqws2/nfqws2.conf').stdout
        baseline=self.sh('test ! -f /usr/share/nfqws2/report-baseline.json || cat /usr/share/nfqws2/report-baseline.json').stdout
        raw='NFQWS_BASE_ARGS="--lua-init=@/etc/nfqws2/lua/native-builtin.lua --blob=demo:@/etc/nfqws2/blobs/native-export.bin"\nNFQWS_ARGS="--filter-tcp=443 --lua-desync=fake:blob=demo"\nNFQWS_ARGS_QUIC=""\n'
        self.sh('cat > /etc/nfqws2/nfqws2.conf',input=raw)
        self.sh('cat > /etc/nfqws2/lua/native-builtin.lua',input='return 1\n')
        self.sh('cat > /etc/nfqws2/blobs/native-export.bin',input='native-blob')
        self.sh('chmod 644 /etc/nfqws2/lua/native-builtin.lua /etc/nfqws2/blobs/native-export.bin')
        self.sh('cat > /usr/share/nfqws2/report-baseline.json',input=json.dumps({'schema_version':1,'package_version':'1.3.2-12','web_version':'0.1.4','resources':{'lua/native-builtin.lua':{'bytes':9,'sha256':hashlib.sha256(b'return 1\n').hexdigest()}}}))
        try:
            code,inv=self.request({'cmd':'shareinventory','csrf_token':token});self.assertEqual(code,200,inv)
            blob=next(x for x in inv['files']if x['name']=='native-export.bin')
            context={'purpose':'Native export','operator':'Local verification','comment':'','share_location':False}
            selection={'version':4,'context':context,'analysis_config_sha256':hashlib.sha256(raw.encode()).hexdigest(),
              'strategy':{'mode':'config','config':raw,'context':context},'resources':{'files':[{'id':blob['id'],'source_sha256':blob['sha256']}],'missing_reason':''}}
            code,value=self.request({'cmd':'shareprepare','csrf_token':token,'selection':json.dumps(selection)})
            if code!=200:
                diagnostic=self.sh('php-cli -r \'require "'+self.base+'/share-api.php"; try{(new AsusShareApi())->handle(json_decode(stream_get_contents(STDIN),true),str_repeat("a",64),time());}catch(Throwable $e){echo $e->getMessage(),"\\n",$e->getTraceAsString();}\'',input=json.dumps({'cmd':'shareprepare','csrf_token':token,'selection':json.dumps(selection)}))
                value['trace']=diagnostic.stdout+diagnostic.stderr
            self.assertEqual(code,200,value)
            documents={x['type']:json.loads(base64.b64decode(x['data_base64']))for x in value['files']}
            self.assertIn('@/opt/etc/nfqws2/lua/native-builtin.lua',documents['strategy']['config'])
            resources=documents['resources'];self.assertTrue(resources['audit']['complete'],resources['audit'])
            self.assertEqual(len(resources['files']),1);self.assertTrue(resources['files'][0]['aliases'])
        finally:
            self.sh('cat > /etc/nfqws2/nfqws2.conf',input=before)
            self.sh('rm -f /etc/nfqws2/lua/native-builtin.lua /etc/nfqws2/blobs/native-export.bin')
            if baseline:self.sh('cat > /usr/share/nfqws2/report-baseline.json',input=baseline)
            else:self.sh('rm -f /usr/share/nfqws2/report-baseline.json')

    def test_native_diagnostic_report_is_schema_valid_and_has_no_host_identifiers(self):
        self.session='native-report';token=self.login()
        self.sh('printf private-domain.invalid > /etc/nfqws2/lists/private-diagnostic-canary.list; chmod 644 /etc/nfqws2/lists/private-diagnostic-canary.list')
        try:code,report=self.request({'cmd':'supportreport','csrf_token':token})
        finally:self.sh('rm -f /etc/nfqws2/lists/private-diagnostic-canary.list')
        self.assertEqual(code,200,report)
        self.assertEqual(report['model'],'OpenWrt')
        self.assertEqual(report['sections']['dns']['data']['platform'],'openwrt')
        self.assertIn('managed_smartdns',report['sections']['dns']['data'])
        platform=report['sections']['platform']['data']
        self.assertEqual(platform['platform'],'openwrt')
        self.assertEqual(platform['package_arch'],'x86_64')
        self.assertGreaterEqual(report['sections']['resources']['data']['count'],1)
        self.assertNotIn('private-diagnostic-canary',json.dumps(report));self.assertNotIn('private-domain.invalid',json.dumps(report))
        self.assertNotIn('hostname',json.dumps(report));self.assertNotIn('macaddr',json.dumps(report))
        r=self.sh('php-cli -r \'require "'+self.base+'/support-json-schema.php"; AsusSupportSchema::validate(stream_get_contents(STDIN),"report"); echo "valid";\'',input=json.dumps(report))
        self.assertEqual(r.stdout,'valid',r.stderr)

    def test_native_share_channel_can_be_configured_locally_without_network(self):
        self.sh('mkdir -p /etc/nfqws2-web; chmod 700 /etc/nfqws2-web; rm -f /etc/nfqws2-web/support-relay.json')
        self.sh('cat > /usr/share/nfqws2/support-relay-default.json',input=(ROOT/'asus/support-relay.json').read_text())
        self.session='native-channel';token=self.login()
        code,value=self.request({'cmd':'sharechannelconnect','csrf_token':token})
        self.assertEqual((code,value),(200,{'connected':True}))
        code,value=self.request({'cmd':'sharestates','csrf_token':token})
        self.assertEqual(code,200,value);self.assertTrue(value['mail']['sharing_v4'])

    def test_native_json_preview_apply_and_undo_preserve_settings_and_files(self):
        from test_import_plan import documents,selection,BLOB,LUA
        self.session='native-import';token=self.login()
        before=self.sh('cat /etc/nfqws2/nfqws2.conf').stdout
        post={'cmd':'importprepare','csrf_token':token,'documents':json.dumps(documents()),'selection':json.dumps(selection())}
        code,preview=self.request(post)
        self.assertEqual(code,200,preview);self.assertTrue(preview['ready'],preview['problems'])
        self.assertIn('--blob=hello:@/etc/nfqws2/blobs/hello.bin',preview['config'])
        code,result=self.request(post|{'cmd':'importapply','proof':preview['proof'],'request_id':'1'*32})
        self.assertEqual((code,result['state']),(200,'committed'))
        for name,raw in [('blobs/hello.bin',BLOB),('lua/custom.lua',LUA)]:
            actual=subprocess.check_output(['docker','exec',CONTAINER,'cat','/etc/nfqws2/'+name])
            self.assertEqual(actual,raw)
        code,status=self.request({'cmd':'importstatus','csrf_token':token});self.assertEqual(code,200)
        code,result=self.request({'cmd':'importundo','csrf_token':token,'id':status['id'],'proof':status['undo_proof']})
        self.assertEqual((code,result['state']),(200,'undone'))
        self.assertEqual(self.sh('cat /etc/nfqws2/nfqws2.conf').stdout,before)
        self.sh('test ! -e /etc/nfqws2/blobs/hello.bin; test ! -e /etc/nfqws2/lua/custom.lua')

if __name__=='__main__':unittest.main()

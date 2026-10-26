"""Read verified native archive metadata without executing maintainer scripts."""
import gzip,hashlib,io,json,os,subprocess,tarfile,tempfile,unittest,uuid,shlex
from pathlib import Path
from test_openwrt_builder import builder

ROOT=Path(__file__).resolve().parents[1];PHP=os.environ.get('PHP_TEST_BINARY')
APK_CONTAINER=os.environ.get('NFQWS_TEST_DOCKER25');CACHE=os.environ.get('NFQWS_TEST_SMARTDNS_CACHE');APK_TOOL=os.environ.get('NFQWS_TEST_APK_TOOL')
def archive(files):
    out=io.BytesIO()
    with tarfile.open(fileobj=out,mode='w:gz')as t:
        for name,raw in files.items():
            m=tarfile.TarInfo(name);m.size=len(raw);m.mode=0o644;t.addfile(m,io.BytesIO(raw))
    return out.getvalue()

@unittest.skipUnless(PHP,'Requires matching PHP test runtime')
class NativeIpkPreflight(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.path=self.root/'package.ipk';self.marker=self.root/'hook-must-not-run'
    def package(self,**fields):
        info={'Package':'nfqws2-native','Version':'1.3.2-72','Architecture':'x86_64','Depends':'libc, php8-cgi'}|fields
        control=archive({'control':''.join(k+': '+v+'\n'for k,v in info.items()).encode(),'preinst':('#!/bin/sh\ntouch '+str(self.marker)+'\n').encode()})
        self.path.write_bytes(archive({'debian-binary':b'2.0\n','control.tar.gz':control,'data.tar.gz':archive({'usr/share/nfqws2/fixture':b'inert bytes'})}));self.path.chmod(0o600)
        self.candidate={'package_version':'1.3.2-72','package':{'series':'24.10','arch':'x86_64','format':'ipk','version':'1.3.2-72','filename':'nfqws2-native_1.3.2-72_x86_64.ipk','size':self.path.stat().st_size,'installed_size':1048576,'sha256':hashlib.sha256(self.path.read_bytes()).hexdigest()}}
    def call(self):
        script='require $argv[1];$p=json_decode(stream_get_contents(STDIN),true);try{echo json_encode(["value"=>NfqwsOpenWrtUpdatePackage::inspect($argv[2],$p["candidate"],$p["environment"],null,(int)$argv[3])]);}catch(Throwable $e){echo json_encode(["error"=>$e->getMessage()]);}'
        r=subprocess.run([PHP,'-n','-r',script,str(ROOT/'webui/web/public/openwrt-update-package.php'),str(self.path),str(os.getuid())],input=json.dumps({'candidate':self.candidate,'environment':{'platform':'openwrt','series':'24.10','arch':'x86_64','format':'ipk'}}),text=True,capture_output=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stderr,'');self.assertFalse(self.marker.exists(),'Archive inspection ran a maintainer script');return json.loads(r.stdout)
    def test_native_control_is_read_and_bound_before_hooks(self):
        self.package();r=self.call();self.assertIn('value',r,r);self.assertEqual(r['value']['name'],'nfqws2-native');self.assertEqual(r['value']['depends'],['libc','php8-cgi'])
    def test_wrong_package_version_architecture_or_conflict_cannot_reach_install(self):
        for delta in [{'Package':'nfqws2-asus'},{'Version':'1.3.2-71'},{'Architecture':'mips_24kc'},{'Conflicts':'amneziawg'},{'Replaces':'dnsmasq'}]:
            with self.subTest(delta=delta):self.package(**delta);self.assertEqual(self.call(),{'error':'invalid_package'})
    def test_official_native_control_root_directory_is_inert_but_other_directories_are_rejected(self):
        for name,accepted in [('.',True),('unexpected',False)]:
            self.package();
            with tarfile.open(self.path)as outer:parts={m.name:outer.extractfile(m).read()for m in outer}
            stream=io.BytesIO()
            with tarfile.open(fileobj=stream,mode='w:gz')as out:
                root=tarfile.TarInfo(name);root.type=tarfile.DIRTYPE;root.mode=0o755;out.addfile(root)
                with tarfile.open(fileobj=io.BytesIO(parts['control.tar.gz']))as inner:
                    for member in inner:out.addfile(member,inner.extractfile(member))
            parts['control.tar.gz']=stream.getvalue();self.path.write_bytes(archive(parts));self.candidate['package'].update(size=self.path.stat().st_size,sha256=hashlib.sha256(self.path.read_bytes()).hexdigest())
            result=self.call()
            if accepted:self.assertIn('value',result,result)
            else:self.assertEqual(result,{'error':'invalid_package'})
    def test_byte_tamper_and_incomplete_download_are_rejected_before_reading_control(self):
        self.package();raw=bytearray(self.path.read_bytes());raw[len(raw)//2]^=1;self.path.write_bytes(raw);self.assertEqual(self.call(),{'error':'download_hash'})
        self.path.write_bytes(raw[:-1]);self.assertEqual(self.call(),{'error':'download_size'})

@unittest.skipUnless(APK_CONTAINER and CACHE and APK_TOOL,'Requires isolated25.12 rootfs, pinned SDK and cache')
class NativeApkPreflight(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec=json.loads(subprocess.check_output(['docker','inspect',APK_CONTAINER]))[0]
        if not APK_CONTAINER.startswith('nfqws-openwrt')or spec['HostConfig']['NetworkMode']=='host':raise RuntimeError('Refusing non-test container')
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name);key=cls.root/'private.pem';cls.public=cls.root/'public.pem';cls.marker='/tmp/nfqws-apk-hook-'+uuid.uuid4().hex
        subprocess.run(['openssl','genpkey','-algorithm','RSA','-pkeyopt','rsa_keygen_bits:3072','-out',str(key)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);key.chmod(0o600)
        subprocess.run(['openssl','pkey','-in',str(key),'-pubout','-out',str(cls.public)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        target=builder.native_metadata('25.12','x86_64',72);target['dependencies']=[];stage=cls.root/'payload';out=cls.root/'out';out.mkdir()
        builder.write_files(stage,{'usr/share/nfqws2/not-executed.txt':(b'inert native fixture\n',0o644)})
        hooks={name:('#!/bin/sh\ntouch '+cls.marker+'\n').encode()for name in ['preinst','postinst','prerm','postrm']}
        cls.pkg=builder.build_apk(target,stage,hooks,CACHE,out,True,sign_key=key)
    @classmethod
    def tearDownClass(cls):
        subprocess.run(['docker','exec',APK_CONTAINER,'rm','-f',cls.marker],check=True);cls.tmp.cleanup()
    def sh(self,code,input=None):
        r=subprocess.run(['docker','exec','-i',APK_CONTAINER,'sh','-c',code],input=input,text=True,capture_output=True,timeout=30)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr);return r
    def setUp(self):
        self.remote='/tmp/nfqws-native-apk-reader-'+uuid.uuid4().hex
        self.sh('umask 077; mkdir -p '+self.remote);self.addCleanup(lambda:self.sh('rm -rf '+self.remote))
        for src,dst in [(self.pkg,'package.apk'),(self.public,'public.pem')]:subprocess.run(['docker','cp',str(src),APK_CONTAINER+':'+self.remote+'/'+dst],check=True,capture_output=True)
        self.sh('chown 0:0 '+self.remote+'/package.apk '+self.remote+'/public.pem; chmod 600 '+self.remote+'/package.apk '+self.remote+'/public.pem; mkdir -m 700 '+self.remote+'/empty')
        code='require $argv[1];NfqwsOpenWrtApkTrust::stage($argv[2]."/keys",file_get_contents($argv[2]."/public.pem"));'
        self.sh('php-cli -r '+shlex.quote(code)+' '+shlex.quote(str(ROOT/'webui/web/public/openwrt-apk-trust.php'))+' '+self.remote)
        self.candidate={'package_version':'1.3.2-r72','package':{'series':'25.12','arch':'x86_64','format':'apk','version':'1.3.2-r72','filename':self.pkg.name,'size':self.pkg.stat().st_size,'installed_size':1048576,'sha256':hashlib.sha256(self.pkg.read_bytes()).hexdigest()}}
    def call(self,keys='keys'):
        script='require $argv[1];$p=json_decode(stream_get_contents(STDIN),true);try{echo json_encode(["value"=>NfqwsOpenWrtUpdatePackage::inspect($argv[2]."/package.apk",$p["candidate"],$p["environment"],$argv[2]."/".$argv[3])]);}catch(Throwable $e){echo json_encode(["error"=>$e->getMessage()]);}'
        r=self.sh('php-cli -r '+shlex.quote(script)+' '+shlex.quote(str(ROOT/'webui/web/public/openwrt-update-package.php'))+' '+self.remote+' '+keys,json.dumps({'candidate':self.candidate,'environment':{'platform':'openwrt','series':'25.12','arch':'x86_64','format':'apk'}}))
        self.assertEqual(r.stderr,'');self.sh('test ! -e '+self.marker);return json.loads(r.stdout)
    def test_signed_apk_metadata_is_read_by_native_tool_without_running_hooks(self):
        r=self.call();self.assertIn('value',r,r);self.assertEqual(r['value']['name'],'nfqws2-native');self.assertEqual(r['value']['version'],'1.3.2-r72')
    def test_missing_key_cannot_be_bypassed_by_archive_reader(self):
        self.assertEqual(self.call('empty'),{'error':'invalid_signature'})
    def test_signed_wrong_package_revision_is_rejected(self):
        self.candidate['package_version']='1.3.2-r73';self.candidate['package']['version']='1.3.2-r73'
        self.assertEqual(self.call(),{'error':'invalid_package'})

if __name__=='__main__':unittest.main()

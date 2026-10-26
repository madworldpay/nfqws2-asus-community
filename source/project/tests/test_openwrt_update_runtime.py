"""Execute staged native PHP code after the original package tree disappears."""
import json,os,shlex,subprocess,unittest,uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CONTAINER=os.environ.get('NFQWS_TEST_DOCKER')

@unittest.skipUnless(CONTAINER,'Requires isolated native rootfs')
class NativeUpdateRuntime(unittest.TestCase):
    def sh(self,code,input=None,check=True):
        r=subprocess.run(['docker','exec','-i',CONTAINER,'sh','-c',code],input=input,text=True,capture_output=True,timeout=25)
        if check:self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        return r
    def setUp(self):
        spec=json.loads(subprocess.check_output(['docker','inspect',CONTAINER]))[0]
        if not CONTAINER.startswith('nfqws-openwrt')or spec['HostConfig']['NetworkMode']=='host':raise RuntimeError('Refusing non-test container')
        self.base='/tmp/nfqws-native-update-runtime-'+uuid.uuid4().hex
        self.addCleanup(lambda:self.sh('rm -rf '+self.base,check=False))
        self.sh('umask 077; mkdir -p '+self.base+'/source/app '+self.base+'/source/resources; cp '+shlex.quote(str(ROOT/'webui/web/public'))+'/*.php '+self.base+'/source/app/; chmod 644 '+self.base+'/source/app/*.php')
        self.sh('printf %s '+shlex.quote('{"schema_version":1,"platform":"openwrt"}')+' > '+self.base+'/source/app/platform-profile.json; chmod 644 '+self.base+'/source/app/platform-profile.json')
        for src,dst in [('trusted-release-key.pem','update-release-key.pem'),('openwrt-package-manifest.schema.json','openwrt-package-manifest.schema.json')]:self.sh('cp '+shlex.quote(str(ROOT/'updates'/src))+' '+self.base+'/source/resources/'+dst+'; chmod 600 '+self.base+'/source/resources/'+dst)
        self.sh('umask 077; cat > '+self.base+'/source/worker.php','<?php require __DIR__."/app/platform.php";echo json_encode(["native"=>NfqwsPlatform::native(),"entry"=>"staged"]);')
    def call(self,operation='stage',**options):
        source=self.base+('/source/app'if operation=='stage'else'/runtime/app')
        code='require $argv[1]."/openwrt-update-runtime.php";$p=json_decode(stream_get_contents(STDIN),true);try{$r=$p["operation"]==="stage"?NfqwsOpenWrtUpdateRuntime::stage($argv[2],$p["options"]):NfqwsOpenWrtUpdateRuntime::load($argv[2]);echo json_encode(["value"=>$r]);}catch(Throwable $e){echo json_encode(["error"=>$e->getMessage()]);}'
        config={'application':self.base+'/source/app','resources':self.base+'/source/resources','entry':self.base+'/source/worker.php'}|options
        r=self.sh('php-cli -r '+shlex.quote(code)+' '+shlex.quote(source)+' '+self.base+'/runtime',json.dumps({'operation':operation,'options':config}))
        self.assertEqual(r.stderr,'');return json.loads(r.stdout)
    def test_code_runs_from_verified_staging_after_original_sources_are_removed(self):
        staged=self.call();self.assertIn('value',staged,staged)
        self.sh('rm -rf '+self.base+'/source')
        self.assertEqual(self.call('load')['value']['digest'],staged['value']['digest'])
        r=self.sh(self.base+'/runtime/run.sh prepare '+'a'*32)
        self.assertEqual(json.loads(r.stdout),{'native':True,'entry':'staged'})
        self.sh('printf %s corrupt >> '+self.base+'/runtime/app/index.php')
        self.assertEqual(self.call('load'),{'error':'runtime_changed'})
    def test_low_space_refuses_staging_before_creating_an_execution_tree(self):
        self.assertEqual(self.call(free=1024),{'error':'insufficient_space'})
        self.assertNotEqual(self.sh('test -e '+self.base+'/runtime',check=False).returncode,0)
    def test_manifest_cannot_omit_the_executable_worker(self):
        self.assertIn('value',self.call())
        code='$p=$argv[1];$v=json_decode(file_get_contents($p),true);$v["bytes"]-=$v["files"]["worker.php"]["size"];unset($v["files"]["worker.php"]);file_put_contents($p,json_encode($v));'
        self.sh('php-cli -r '+shlex.quote(code)+' '+self.base+'/runtime/closure.json')
        self.assertEqual(self.call('load'),{'error':'runtime_changed'})

if __name__=='__main__':unittest.main()

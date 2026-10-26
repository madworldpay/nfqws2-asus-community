"""Native updater proof must identify staged CGI and its manager, never HTTP flags."""
import json,os,shlex,subprocess,unittest,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];CONTAINER=os.environ.get('NFQWS_TEST_DOCKER')
@unittest.skipUnless(CONTAINER,'Requires isolated native PHP CGI')
class NativeGuard(unittest.TestCase):
 def sh(self,code,input=None):
  p=subprocess.run(['docker','exec','-i',CONTAINER,'sh','-c',code],input=input,text=True,capture_output=True,timeout=25);self.assertEqual(p.returncode,0,p.stdout+p.stderr);return p.stdout
 def test_staged_worker_proof_and_phase_are_required(self):
  module=ROOT/'webui/web/public/openwrt-update-guard.php';self.assertTrue(module.exists(),'native updater guard missing')
  spec=json.loads(subprocess.check_output(['docker','inspect',CONTAINER]))[0];self.assertNotEqual(spec['HostConfig']['NetworkMode'],'host');self.assertTrue(CONTAINER.startswith('nfqws-openwrt'))
  base='/tmp/native-update-guard-'+uuid.uuid4().hex;self.addCleanup(lambda:self.sh('rm -rf '+base))
  self.sh('umask 077; mkdir -p '+base+'/source/app '+base+'/source/resources; cp '+shlex.quote(str(ROOT/'webui/web/public'))+'/*.php '+base+'/source/app/; chmod 644 '+base+'/source/app/*.php')
  self.sh('printf %s '+shlex.quote('{"schema_version":1,"platform":"openwrt"}')+' > '+base+'/source/app/platform-profile.json')
  for name,dst in [('openwrt-package-manifest.schema.json','openwrt-package-manifest.schema.json'),('trusted-release-key.pem','update-release-key.pem')]:self.sh('cp '+shlex.quote(str(ROOT/'updates'/name))+' '+base+'/source/resources/'+dst)
  worker='''<?php
require __DIR__.'/app/openwrt-update-guard.php';require __DIR__.'/app/update-guard.php';
$s=new AsusUpdateStore(dirname(__DIR__,3));$id=basename(dirname(__DIR__));$g=new NfqwsOpenWrtUpdateGuard($s);
$t=['schema'=>1,'id'=>$id,'boot_id'=>AsusUpdateStore::boot(),'worker'=>AsusUpdateLifecycle::identity(getmypid()),'manager'=>null,'phase'=>'validating','format'=>'ipk','intent'=>['mode'=>'stopped']];
$s->writeFile('native-transaction.json',json_encode($t));$s->update($id,['identity'=>$t['worker']]);
if($g->context($id)!==$t||$g->authorize('dns-restore'))throw new RuntimeException('bad worker proof');
$t['phase']='starting';$s->writeFile('native-transaction.json',json_encode($t));if(!$g->authorize('web-start')||$g->authorize('core-start'))throw new RuntimeException('wrong phase or intent');
$resumeLease=$g->mutationLease();flock($resumeLease,LOCK_UN);fclose($resumeLease);
if(!(new AsusUpdateGuard($s))->authorize('web-start'))throw new RuntimeException('common guard did not select native boundary');
$t['worker']['start_ticks']='1';$s->writeFile('native-transaction.json',json_encode($t));if($g->authorize('web-start'))throw new RuntimeException('stale process accepted');echo 'PASS';
'''
  self.sh('cat > '+base+'/source/worker.php',worker)
  setup='require $argv[1]."/openwrt-update-guard.php";$s=new AsusUpdateStore($argv[2]."/store");$rev=str_repeat("a",64);$j=$s->reserve($rev,str_repeat("b",32),["revision"=>$rev,"package_version"=>"1.3.2-72"]);$r=NfqwsOpenWrtUpdateRuntime::stage($s->path("operations/".$j["id"]."/runtime"),["application"=>$argv[1],"resources"=>$argv[2]."/source/resources","entry"=>$argv[2]."/source/worker.php"]);$s->update($j["id"],["state"=>"prepared","runtime_digest"=>$r["digest"]]);$s->claimApply($j["id"],$rev,str_repeat("c",32));echo $j["id"];'
  ident=self.sh('php-cli -r '+shlex.quote(setup)+' '+base+'/source/app '+base)
  self.assertEqual(self.sh(base+'/store/operations/'+ident+'/runtime/run.sh apply '+ident),'PASS')
if __name__=='__main__':unittest.main()

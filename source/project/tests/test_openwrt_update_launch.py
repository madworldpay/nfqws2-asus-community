"""Native background update launch uses system BusyBox/PHP and sealed staged code."""
import json,os,shlex,time,unittest
import test_openwrt_update_runtime as runtime
ROOT=runtime.ROOT;CONTAINER=runtime.CONTAINER
class NativeUpdateLaunch(runtime.NativeUpdateRuntime):
 test_code_runs_from_verified_staging_after_original_sources_are_removed=None
 test_low_space_refuses_staging_before_creating_an_execution_tree=None
 test_manifest_cannot_omit_the_executable_worker=None
 def setUp(self):
  super().setUp();self.assertTrue((ROOT/'webui/web/public/openwrt-update-launch.php').exists(),'native detached launcher missing')
  self.sh('test ! -e /usr/lib/nfqws2/update/worker.sh; test ! -e /usr/lib/nfqws2/update/worker.php')
  self.sh('mkdir -p /usr/lib/nfqws2/update; cat > /usr/lib/nfqws2/update/worker.sh',(ROOT/'openwrt/update/worker.sh').read_text());self.sh('chmod 755 /usr/lib/nfqws2/update/worker.sh')
  self.sh('cat > /usr/lib/nfqws2/update/worker.php','<?php file_put_contents('+json.dumps(self.base+'/installed-mode')+',json_encode(array_slice($argv,-2)));')
  self.sh('chmod 644 /usr/lib/nfqws2/update/worker.php');self.addCleanup(lambda:self.sh('rm -f /usr/lib/nfqws2/update/worker.sh /usr/lib/nfqws2/update/worker.php',check=False))
 def poll(self,name):
  for _ in range(100):
   r=self.sh('cat '+self.base+'/'+name,check=False)
   if r.returncode==0:return json.loads(r.stdout)
   time.sleep(.02)
  self.fail('Detached native worker did not publish mode')
 def test_native_check_is_detached_and_does_not_probe_entware_channel(self):
  code='require $argv[1]."/openwrt-update-prepare.php";require $argv[1]."/update-check.php";$s=new AsusUpdateStore($argv[2]."/store");$p=new NfqwsOpenWrtUpdatePrepare($s,null,["platform"=>"openwrt","series"=>"24.10","arch"=>"x86_64","format"=>"ipk","installed"=>"1.3.2-71","build"=>71]);echo json_encode((new AsusUpdateCheck($s,$p))->request(true));'
  r=self.sh('php-cli -r '+shlex.quote(code)+' '+self.base+'/source/app '+self.base);self.assertEqual(json.loads(r.stdout)['state'],'checking',r.stdout);mode,ident=self.poll('installed-mode');self.assertEqual(mode,'guard-check');self.assertRegex(ident,'^[a-f0-9]{32}$')
 def test_installed_prepare_uses_fixed_native_entry(self):
  code='require $argv[1]."/openwrt-update-launch.php";$s=new AsusUpdateStore($argv[2]."/store");NfqwsOpenWrtUpdateLaunch::launch($s,"prepare",str_repeat("a",32));'
  self.sh('php-cli -r '+shlex.quote(code)+' '+self.base+'/source/app '+self.base);self.assertEqual(self.poll('installed-mode'),['guard-prepare','a'*32])
 def test_apply_guard_runs_from_verified_stage_after_installed_sources_are_gone(self):
  self.sh('cat > '+self.base+'/source/worker.php','<?php file_put_contents('+json.dumps(self.base+'/staged-mode')+',json_encode(array_slice($argv,-2)));')
  code='require $argv[1]."/openwrt-update-launch.php";$s=new AsusUpdateStore($argv[2]."/store");$r=str_repeat("a",64);$j=$s->reserve($r,str_repeat("b",32),["revision"=>$r,"package_version"=>"1.3.2-72"]);$v=NfqwsOpenWrtUpdateRuntime::stage($s->path("operations/".$j["id"]."/runtime"),["application"=>$argv[1],"resources"=>$argv[2]."/source/resources","entry"=>$argv[2]."/source/worker.php"]);$s->update($j["id"],["state"=>"prepared","runtime_digest"=>$v["digest"]]);$s->claimApply($j["id"],$r,str_repeat("c",32));NfqwsOpenWrtUpdateLaunch::launch($s,"apply",$j["id"]);echo $j["id"];'
  r=self.sh('php-cli -r '+shlex.quote(code)+' '+self.base+'/source/app '+self.base);self.sh('rm -rf '+self.base+'/source');self.assertEqual(self.poll('staged-mode'),['guard-apply',r.stdout])
if __name__=='__main__':unittest.main()

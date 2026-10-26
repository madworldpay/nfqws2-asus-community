"""Real native managers: only our fixture changes; system database and world stay put."""
import json,os,shlex,subprocess,tempfile,unittest,uuid
from pathlib import Path
from test_openwrt_update_package import NativeApkPreflight,ROOT,builder,APK_CONTAINER,CACHE,APK_TOOL
CONTAINER24=os.environ.get('NFQWS_TEST_DOCKER24')or(os.environ.get('NFQWS_TEST_DOCKER')if'24'in os.environ.get('NFQWS_TEST_DOCKER','')else None)

@unittest.skipUnless(os.environ.get('PHP_TEST_BINARY'),'Requires matching PHP runtime')
class NativeManagerContracts(unittest.TestCase):
    def test_native_state_flags_and_own_service_health_scope(self):
        p=subprocess.run([os.environ['PHP_TEST_BINARY'],'-n','-f',str(ROOT/'tests/test_openwrt_update_manager.php')],text=True,capture_output=True,timeout=10)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'');self.assertIn('PASS:',p.stdout)

@unittest.skipUnless(os.environ.get('NFQWS_TEST_DOCKER'),'Requires isolated native package database')
class NativeVirtualDependencies(unittest.TestCase):
    def test_installed_native_provider_satisfies_virtual_dependency_without_installing_system_packages(self):
        container=os.environ['NFQWS_TEST_DOCKER'];spec=json.loads(subprocess.check_output(['docker','inspect',container]))[0]
        self.assertTrue(container.startswith('nfqws-openwrt'));self.assertNotEqual(spec['HostConfig']['NetworkMode'],'host')
        fmt='apk'if'25'in container else'ipk'
        code='require $argv[1];$e=["format"=>$argv[2]];$d=NfqwsOpenWrtUpdateManager::installed($e);if(!isset($d["libgcc1"])||isset($d["libgcc"]))throw new RuntimeException("fixture requires real libgcc1 virtual provider");$out=[];foreach(["libgcc","nfqws-missing-dependency-fixture"]as $name){try{$a=NfqwsOpenWrtUpdateManager::argv("/tmp/inert-package",$e,$d,["name"=>"nfqws2-native","depends"=>[$name]],"/tmp/inert-keys",true);$out[$name]="accepted";}catch(RuntimeException $ex){$out[$name]=$ex->getMessage();}}echo json_encode($out);'
        r=subprocess.run(['docker','exec',container,'php-cli','-r',code,str(ROOT/'webui/web/public/openwrt-update-manager.php'),fmt],text=True,capture_output=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(json.loads(r.stdout),{'libgcc':'accepted','nfqws-missing-dependency-fixture':'missing_dependencies'})
        requirements='require $argv[1];echo json_encode(NfqwsOpenWrtUpdateManager::missing(["format"=>$argv[2]],["libgcc","nfqws-missing-dependency-fixture"]));'
        p=subprocess.run(['docker','exec',container,'php-cli','-r',requirements,str(ROOT/'webui/web/public/openwrt-update-manager.php'),fmt],capture_output=True,text=True,timeout=10)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(json.loads(p.stdout),['nfqws-missing-dependency-fixture'])

@unittest.skipUnless(APK_CONTAINER and CACHE and APK_TOOL,'Requires isolated signed native25 package fixture')
class NativeApkTransaction(NativeApkPreflight):
    # Reuse fixture setup, not archive-reader test methods.
    test_signed_apk_metadata_is_read_by_native_tool_without_running_hooks=None
    test_missing_key_cannot_be_bypassed_by_archive_reader=None
    test_signed_wrong_package_revision_is_rejected=None
    def setUp(self):
        super().setUp();self.sh('rm -f '+self.marker)

    def test_reconstructed_simulation_cannot_be_overridden_or_cross_end_of_options(self):
        before=self.sh('sha256sum /lib/apk/db/installed /etc/apk/world').stdout
        script='require $argv[1]."/openwrt-apk-command.php";require_once $argv[1]."/platform.php";$args=json_decode(stream_get_contents(STDIN),true);$cmd=NfqwsOpenWrtApkCommand::simulation($args);$p=NfqwsPlatform::run($cmd,20);if($p["status"]!==0)throw new RuntimeException(json_encode($p));echo NfqwsOpenWrtApkCommand::affects(implode("\\n",$p["output"]));'
        for options in [[],['--simulate=no']]:
            with self.subTest(options=options):
                argv=['/usr/bin/apk','add','--keys-dir',self.remote+'/keys','--network=no','--cache=no','--repositories-file','/dev/null']+options+['--',self.remote+'/package.apk']
                p=self.sh('php-cli -r '+shlex.quote(script)+' '+shlex.quote(str(ROOT/'webui/web/public')),json.dumps(argv));self.assertEqual(p.stdout,'upgrade')
                self.assertEqual(self.sh('sha256sum /lib/apk/db/installed /etc/apk/world').stdout,before);self.sh('test ! -e '+self.marker)

    def test_native_manager_changes_only_application_and_own_world_entry(self):
        r=self.sh("apk query --installed --format json --fields name,version '*'");before=json.loads(r.stdout)
        self.assertNotIn('nfqws2-native',[p['name']for p in before],'Refusing to replace an existing package in test container')
        world=self.sh('cat /etc/apk/world').stdout.splitlines()
        script='require $argv[1];$e=["format"=>"apk"];$d=NfqwsOpenWrtUpdateManager::installed($e);$r=["name"=>"nfqws2-native","version"=>"1.3.2-r72","depends"=>[]];$a=NfqwsOpenWrtUpdateManager::argv($argv[2]."/package.apk",$e,$d,$r,$argv[2]."/keys",true);$p=NfqwsPlatform::run($a,20);if($p["status"]!==0)throw new RuntimeException(json_encode($p));NfqwsOpenWrtUpdateManager::plan(implode("\\n",$p["output"]),"apk",$r);echo json_encode($d);'
        out=self.sh('php-cli -r '+shlex.quote(script)+' '+shlex.quote(str(ROOT/'webui/web/public/openwrt-update-manager.php'))+' '+self.remote)
        self.assertEqual(len(json.loads(out.stdout)),len(before));self.sh('test ! -e '+self.marker)
        try:
            self.sh('apk add --network=no --cache=no --repositories-file /dev/null --keys-dir '+self.remote+'/keys '+self.remote+'/package.apk')
            self.sh('test -f '+self.marker)
            inventory='require $argv[1];$v=NfqwsOpenWrtUpdatePayload::capture("apk");if(!NfqwsOpenWrtUpdatePayload::unchanged($v))throw new RuntimeException("original package inventory mismatch");echo json_encode(array_keys($v["files"]));'
            paths=json.loads(self.sh('php-cli -r '+shlex.quote(inventory)+' '+shlex.quote(str(ROOT/'webui/web/public/openwrt-update-payload.php'))).stdout)
            self.assertEqual(set(paths),{'/usr/share/nfqws2/not-executed.txt','/lib/apk/packages/nfqws2-native.list'})
            after=json.loads(self.sh("apk query --installed --format json --fields name,version '*'").stdout)
            self.assertEqual([p for p in after if p['name']!='nfqws2-native'],before)
            later=self.sh('cat /etc/apk/world').stdout.splitlines();self.assertEqual([s for s in later if not s.startswith('nfqws2-native')],world)
            self.assertEqual(sum(s.startswith('nfqws2-native')for s in later),1)
        finally:self.sh('apk del --network=no nfqws2-native')
        self.assertEqual(self.sh('cat /etc/apk/world').stdout.splitlines(),world)

@unittest.skipUnless(CONTAINER24 and CACHE,'Requires isolated24 native opkg rootfs')
class NativeIpkTransaction(unittest.TestCase):
    def test_native_manager_dry_run_and_install_keep_system_packages(self):
        spec=json.loads(subprocess.check_output(['docker','inspect',CONTAINER24]))[0]
        self.assertTrue(CONTAINER24.startswith('nfqws-openwrt'));self.assertNotEqual(spec['HostConfig']['NetworkMode'],'host')
        def sh(code):
            r=subprocess.run(['docker','exec',CONTAINER24,'sh','-c',code],text=True,capture_output=True,timeout=30);self.assertEqual(r.returncode,0,r.stdout+r.stderr);return r.stdout
        remote='/tmp/nfqws-ipk-manager-'+uuid.uuid4().hex;sh('umask 077; mkdir '+remote)
        before=sh('opkg list-installed');self.assertNotIn('nfqws2-native - ',before,'Refusing to replace an existing fixture')
        with tempfile.TemporaryDirectory()as td:
            root=Path(td);stage=root/'payload';out=root/'out';out.mkdir();marker=remote+'/hook'
            metadata='Package: nfqws2-native\nVersion: 1.3.2-72\nArchitecture: x86_64\nMaintainer: madworldpay\nDescription: Inert native fixture\n'
            builder.write_files(stage,{'CONTROL/control':(metadata.encode(),0o644),'CONTROL/preinst':(('#!/bin/sh\ntouch '+marker+'\n').encode(),0o755),'usr/share/nfqws2/inert-fixture':(b'inert bytes',0o644)})
            tool=builder.pinned_asset(builder.ASSETS['ipkg_build'],CACHE,True)
            subprocess.run(['fakeroot','sh',str(tool),str(stage),str(out)],check=True,capture_output=True)
            subprocess.run(['docker','cp',str(next(out.glob('*.ipk'))),CONTAINER24+':'+remote+'/package.ipk'],check=True,capture_output=True)
        try:
            code='require $argv[1];$e=["format"=>"ipk"];$d=NfqwsOpenWrtUpdateManager::installed($e);$r=["name"=>"nfqws2-native","version"=>"1.3.2-72","depends"=>[]];$p=NfqwsPlatform::run(NfqwsOpenWrtUpdateManager::argv($argv[2],$e,$d,$r,null,true),20);if($p["status"]!==0)throw new RuntimeException(json_encode($p));NfqwsOpenWrtUpdateManager::plan(implode("\\n",$p["output"]),"ipk",$r);echo "PASS";'
            self.assertEqual(sh('php-cli -r '+shlex.quote(code)+' '+shlex.quote(str(ROOT/'webui/web/public/openwrt-update-manager.php'))+' '+remote+'/package.ipk'),'PASS')
            sh('test ! -e '+marker)
            sh('opkg --nodeps install '+remote+'/package.ipk');sh('test -f '+marker)
            inventory='require $argv[1];$v=NfqwsOpenWrtUpdatePayload::capture("ipk");if(!NfqwsOpenWrtUpdatePayload::unchanged($v))throw new RuntimeException("original package inventory mismatch");echo json_encode(array_keys($v["files"]));'
            self.assertEqual(json.loads(sh('php-cli -r '+shlex.quote(inventory)+' '+shlex.quote(str(ROOT/'webui/web/public/openwrt-update-payload.php')))),['/usr/share/nfqws2/inert-fixture'])
            after=sh('opkg list-installed');self.assertEqual(''.join(x+'\n'for x in after.splitlines()if not x.startswith('nfqws2-native - ')),before)
        finally:
            sh('opkg remove nfqws2-native');sh('rm -rf '+remote)
        self.assertEqual(sh('opkg list-installed'),before)

if __name__=='__main__':unittest.main()

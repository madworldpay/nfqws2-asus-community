"""Private worker facts and real HTTP admission; no router or firewall writes."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
import unittest

import test_auth_api as auth

PUBLIC=Path(__file__).resolve().parents[1]/'webui/web/public'
PHP=auth.PHP


class IpHealthRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.private=self.root/'private';self.private.mkdir(mode=0o700)
        self.run=self.root/'run';self.run.mkdir(mode=0o755)
        self.events=self.run/'events';self.events.mkdir(mode=0o700)
        self.log=self.events/'events.log';self.log.write_text('');self.log.chmod(0o600)
        self.proc=self.root/'proc';(self.proc/'sys/kernel/random').mkdir(parents=True)
        self.boot='11111111-2222-3333-4444-555555555555'
        (self.proc/'sys/kernel/random/boot_id').write_text(self.boot+'\n')
        (self.proc/'net/netfilter').mkdir(parents=True)
        self.queue=self.proc/'net/netfilter/nfnetlink_queue';self.queue.write_text('301 42 0 2 65535 0 0 0 1\n')
        self.engine=self.root/'nfqws2';self.engine.write_text('fixture');self.engine.chmod(0o755)
        for pid,ticks in [(41,500),(42,600)]:
            p=self.proc/str(pid);p.mkdir()
            (p/'stat').write_text(f'{pid} (nfqws2 observer) S '+'0 '*18+str(ticks)+' 0\n')
            (p/'exe').symlink_to(self.engine)
            (p/'status').write_text('Uid:\t'+('\t'.join([str(os.getuid())]*4))+'\n')
            (p/'cmdline').write_bytes(str(self.engine).encode()+b'\0--qnum=301\0')
        self.now=int(time.time())
        self.facts={'schema_version':1,'boot_id':self.boot,'core_pid':41,'core_start_ticks':'500',
                    'observer_pid':42,'observer_start_ticks':'600','queue':301,'interface':'eth0',
                    'generation':'a'*64,'ipv6':False,'engine_uid':os.getuid()}
        self.write_facts()

    def write_facts(self):
        path=self.private/'runtime.json';path.write_text(json.dumps(self.facts));path.chmod(0o600)

    def tick(self, available=True, busy=False):
        source=PUBLIC/'ip-health-runtime.php'
        self.assertTrue(source.is_file(),'IP health runtime is missing')
        code=r'''require $argv[1].'/ip-health-runtime.php';
        class RuntimeProbe extends NfqwsIpHealthProbe {public array $calls=[];
          public function availability(string $interface):bool{return $GLOBALS['available'];}
          public function check(string $ip,string $sni,string $interface):string{$this->calls[]=$ip;return count($this->calls)%3===1?'replied':'silent';}}
        $GLOBALS['available']=$argv[8]==='1';$probe=new RuntimeProbe();
        $store=new NfqwsIpHealthStore($argv[2].'/state',$argv[2].'/run');
        $lease=function(){if($GLOBALS['busy'])throw new RuntimeException('busy');return null;};$GLOBALS['busy']=$argv[9]==='1';
        $runtime=new NfqwsIpHealthRuntime($store,$argv[2].'/private',$argv[2].'/run',$argv[2].'/proc',$argv[3],(int)$argv[4],$probe,$lease);
        $runtime->tick((int)$argv[5]);echo json_encode(['status'=>$store->status((int)$argv[5]),'calls'=>$probe->calls]);'''
        p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(self.root),str(self.engine),str(os.getuid()),str(self.now),'unused','unused','1'if available else'0','1'if busy else'0'],capture_output=True,text=True,timeout=5)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'');return json.loads(p.stdout)

    def observe(self):
        self.log.write_text(f'silent|{self.now}|93.184.216.34|40001|example.com\nsilent|{self.now}|93.184.216.34|40002|example.com\n')

    def test_live_owned_queue_consumes_observations_and_publishes_expiring_manifest(self):
        self.observe();v=self.tick();self.assertEqual(v['status']['runtime']['state'],'active')
        self.assertEqual(len(v['calls']),3);self.assertEqual(v['status']['entries'][0]['until'],self.now+86400)
        self.assertEqual(self.log.read_text(),'');manifest=self.run/'active.txt'
        self.assertIn(f'expires {self.now+15}',manifest.read_text());self.assertEqual(manifest.stat().st_mode&0o777,0o644)

    def test_entware_opt_alias_matches_the_actual_process_executable(self):
        alias=self.root/'opt-alias';alias.symlink_to(self.root,target_is_directory=True)
        self.engine=alias/'nfqws2';self.observe()
        self.assertEqual(self.tick()['status']['runtime']['state'],'active')

    def test_worker_stop_identity_accepts_only_the_same_entry_through_opt_alias(self):
        entry=self.root/'entry.php';entry.write_text('<?php');alias=self.root/'opt-alias';alias.symlink_to(self.root,target_is_directory=True)
        proc=self.proc/'43';proc.mkdir();(proc/'stat').write_text('43 (php-cgi) S '+'0 '*18+'700 0\n')
        (proc/'exe').symlink_to(Path(PHP).resolve());(proc/'status').write_text('Uid:\t'+('\t'.join([str(os.getuid())]*4))+'\n')
        (proc/'cmdline').write_bytes(str(PHP).encode()+b'\0'+str(alias/'entry.php').encode()+b'\0loop\0')
        identity=self.private/'worker.json';identity.write_text(json.dumps({'pid':43,'start_ticks':'700','boot_id':self.boot}));identity.chmod(0o600)
        script='''require $argv[1].'/ip-health-runtime.php';$s=new NfqwsIpHealthStore($argv[2].'/state',$argv[2].'/run');
        $r=new NfqwsIpHealthRuntime($s,$argv[2].'/private',$argv[2].'/run',$argv[2].'/proc',$argv[2].'/nfqws2',(int)$argv[3]);echo json_encode($r->ownedPids($argv[2].'/entry.php',PHP_BINARY));'''
        def owned():
            p=subprocess.run([PHP,'-n','-r',script,str(PUBLIC),str(self.root),str(os.getuid())],capture_output=True,text=True,timeout=3)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr);return json.loads(p.stdout)
        self.assertEqual(owned(),[42,43])
        (proc/'stat').write_text('43 (reused pid) S '+'0 '*18+'701 0\n');self.assertEqual(owned(),[42])

    def test_missing_socket_capability_or_busy_updater_never_probe_or_enforce(self):
        for opts,code in [({'available':False},'socket_unavailable'),({'busy':True},'update_busy')]:
            with self.subTest(opts=opts):
                self.observe();v=self.tick(**opts);self.assertEqual(v['calls'],[])
                self.assertEqual(v['status']['runtime']['state'],'unavailable');self.assertEqual(v['status']['runtime']['code'],code)
                self.assertIn('enabled 0', (self.run/'active.txt').read_text())

    def test_dead_core_or_foreign_queue_fails_open_without_consuming_evidence(self):
        self.observe();(self.proc/'41/stat').write_text('41 (reused pid) S '+'0 '*18+'999 0\n')
        v=self.tick();self.assertEqual(v['calls'],[]);self.assertEqual(v['status']['runtime']['code'],'core_stopped')
        self.assertTrue(self.log.read_text());self.queue.write_text('301 900 0 2 65535 0 0 0 1\n')
        (self.proc/'41/stat').write_text('41 (nfqws2) S '+'0 '*18+'500 0\n')
        v=self.tick();self.assertEqual(v['calls'],[]);self.assertEqual(v['status']['runtime']['code'],'queue_in_use')

    def test_untrusted_event_links_are_never_followed_or_truncated(self):
        outside=self.root/'outside';outside.write_text('OWNER DATA');outside.chmod(0o600)
        for kind in ['symlink','hardlink']:
            with self.subTest(kind=kind):
                self.log.unlink()
                if kind=='symlink':self.log.symlink_to(outside)
                else:os.link(outside,self.log)
                v=self.tick();self.assertEqual(v['calls'],[]);self.assertEqual(outside.read_text(),'OWNER DATA')
                self.assertIn('enabled 0',(self.run/'active.txt').read_text())

    def test_changed_boot_invalid_facts_and_idle_ticks_do_not_create_incidents(self):
        v=self.tick();self.assertEqual(v['status']['entries'],[])
        state=self.root/'state/bans.json';stamp=state.stat().st_mtime_ns;self.tick();self.assertEqual(state.stat().st_mtime_ns,stamp)
        self.facts['boot_id']='aaaaaaaa-2222-3333-4444-555555555555';self.write_facts()
        v=self.tick();self.assertEqual(v['calls'],[]);self.assertNotEqual(v['status']['runtime']['state'],'active')

    def test_actual_worker_survives_hup_and_duplicate_keeps_held_lease(self):
        source=PUBLIC.parents[2]/'ip-health/worker.php';self.assertTrue(source.exists())
        app=self.root/'app';app.mkdir()
        for path in PUBLIC.glob('*.php'):shutil.copyfile(path,app/path.name)
        root_status=self.root/'root-status';root_status.write_text('Uid:\t0\t0\t0\t0\n')
        code=source.read_text().replace('/proc/self/status',str(root_status)).replace('/opt/share/nfqws-asus-web',str(app))
        code=code.replace('/tmp/nfqws2-asus/ip-health-private',str(self.private)).replace('/tmp/nfqws2-asus-ip-health',str(self.run))
        code=code.replace('$store=new NfqwsIpHealthStore();',f'$store=new NfqwsIpHealthStore({json.dumps(str(self.root/"state"))},{json.dumps(str(self.run))});')
        code=code.replace('$runtime=new NfqwsIpHealthRuntime($store,$private,$public);',f'$runtime=new NfqwsIpHealthRuntime($store,$private,$public,{json.dumps(str(self.proc))},{json.dumps(str(self.engine))},{os.getuid()});')
        code=code.replace("$s['uid']!==0",f"$s['uid']!=={os.getuid()}")
        worker=self.root/'worker.php';worker.write_text(code)
        # This matches the adapter's pre-fork ignored HUP, with all stdio closed.
        p=subprocess.Popen(['sh','-c','trap "" HUP; exec "$@"','worker',PHP,'-n',str(worker),'loop'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        try:
            deadline=time.monotonic()+2
            while not (self.private/'worker.json').exists() and p.poll()is None and time.monotonic()<deadline:time.sleep(.01)
            self.assertTrue((self.private/'worker.json').exists(),'actual worker must acquire/register its private lease')
            original=(self.private/'worker.json').read_bytes();os.killpg(p.pid,signal.SIGHUP);time.sleep(.05)
            self.assertIsNone(p.poll(),'detached worker survives SSH process-group HUP')
            duplicate=subprocess.run([PHP,'-n',str(worker),'loop'],capture_output=True,text=True,timeout=2)
            self.assertEqual(duplicate.returncode,0,duplicate.stdout+duplicate.stderr)
            self.assertEqual((self.private/'worker.json').read_bytes(),original)
            self.assertFalse((self.root/'state/bans.json').exists(),'missing sockets must not create a persistent journal')
        finally:p.terminate();p.wait(timeout=3)


class IpHealthHttpTests(unittest.TestCase):
    def setUp(self):
        self.fixture=auth.PasswordApiTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.root=self.fixture.base
        for path in PUBLIC.glob('*.php'):
            if not (self.root/path.name).exists():shutil.copyfile(path,self.root/path.name)
        api=self.root/'ip-health-api.php'
        api.write_text(api.read_text().replace('new NfqwsIpHealthStore()',"new NfqwsIpHealthStore(__DIR__.'/state',__DIR__.'/run')"))
        index=self.root/'index.php';index.write_text(index.read_text().replace('function main(): void\n{',"function main(): void\n{\n$_SERVER['HTTP_HOST']='router.lan';$_SERVER['HTTP_ORIGIN']=$_POST['origin_fixture']??'http://router.lan';unset($_POST['origin_fixture']);"))

    def test_real_route_requires_auth_csrf_origin_and_strict_fields(self):
        p={'cmd':'iphealthstatus','csrf_token':'wrong'}
        self.assertEqual(self.fixture.request(p)[0],401)
        token=self.fixture.login();self.assertEqual(self.fixture.request(p)[0],403)
        p['csrf_token']=token;p['origin_fixture']='http://evil.test';self.assertEqual(self.fixture.request(p)[0],403)
        p.pop('origin_fixture');p['unexpected']='x';self.assertEqual(self.fixture.request(p)[0],400)
        p.pop('unexpected');code,data=self.fixture.request(p);self.assertEqual(code,200);self.assertEqual(data['entries'],[])
        self.assertFalse((self.root/'state').exists(),'status read must not create persistent storage')

    def test_native_route_is_closed_after_auth_and_csrf_before_any_asus_action(self):
        token=self.fixture.login()
        platform=self.root/'platform.php'
        platform.write_text(platform.read_text().replace('return $profile;', "return 'openwrt';",1))
        status={'cmd':'iphealthstatus','csrf_token':token}
        self.assertEqual(self.fixture.request({**status,'csrf_token':'wrong'})[0],403)
        self.assertEqual(self.fixture.request(status),(503,{'error':'unsupported_runtime'}))
        for command,extra in [('iphealthconfigure',{'enabled':'1'}),('iphealthremove',{'id':'a'*32}),('iphealthclear',{}),('iphealthrecheck',{'id':'all'})]:
            self.assertEqual(self.fixture.request({'cmd':command,'csrf_token':token,'revision':'a'*64,**extra}),(503,{'error':'unsupported_runtime'}))
        self.assertFalse((self.root/'state').exists())
        self.assertFalse((self.root/'http-mutation.lock').exists())

    def test_update_mutex_blocks_mutation_but_not_status(self):
        token=self.fixture.login();code,status=self.fixture.request({'cmd':'iphealthstatus','csrf_token':token});self.assertEqual(code,200)
        (self.root/'update-busy').touch()
        self.assertEqual(self.fixture.request({'cmd':'iphealthconfigure','csrf_token':token,'revision':status['revision'],'enabled':'0'}),(409,{'error':'busy'}))
        self.assertFalse((self.root/'state').exists())

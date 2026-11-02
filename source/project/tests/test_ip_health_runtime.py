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
        self.netlink=self.proc/'net/netlink';self.netlink.write_text('sk Eth Pid Groups Rmem Wmem Dump Locks Drops Inode\n00000000 12 42 00000000 0 0 0 2 0 123456\n')
        self.engine=self.root/'nfqws2';self.engine.write_text('fixture');self.engine.chmod(0o755)
        for pid,ticks in [(41,500),(42,600)]:
            p=self.proc/str(pid);p.mkdir()
            (p/'stat').write_text(f'{pid} (nfqws2 observer) S '+'0 '*18+str(ticks)+' 0\n')
            (p/'exe').symlink_to(self.engine)
            (p/'status').write_text('Uid:\t'+('\t'.join([str(os.getuid())]*4))+'\n')
            (p/'cmdline').write_bytes(str(self.engine).encode()+b'\0--qnum=301\0')
            (p/'fd').mkdir()
        (self.proc/'42/fd/5').symlink_to('socket:[123456]')
        self.now=int(time.time())
        self.facts={'schema_version':1,'boot_id':self.boot,'core_pid':41,'core_start_ticks':'500',
                    'observer_pid':42,'observer_start_ticks':'600','queue':301,'interface':'eth0',
                    'generation':'a'*64,'ipv6':False,'engine_uid':os.getuid()}
        self.write_facts()

    def write_facts(self):
        path=self.private/'runtime.json';path.write_text(json.dumps(self.facts));path.chmod(0o600)

    def tick(self, available=True, busy=False, runtime_public=PUBLIC):
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
        p=subprocess.run([PHP,'-n','-r',code,str(runtime_public),str(self.root),str(self.engine),str(os.getuid()),str(self.now),'unused','unused','1'if available else'0','1'if busy else'0'],capture_output=True,text=True,timeout=5)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'');return json.loads(p.stdout)

    def observe(self):
        self.log.write_text(f'silent|{self.now}|93.184.216.34|40001|example.com\nsilent|{self.now}|93.184.216.34|40002|example.com\n')

    def test_live_owned_queue_consumes_observations_and_publishes_expiring_manifest(self):
        self.observe();v=self.tick();self.assertEqual(v['status']['runtime']['state'],'active')
        self.assertEqual(len(v['calls']),3);self.assertEqual(v['status']['entries'][0]['until'],self.now+86400)
        self.assertEqual(self.log.read_text(),'');manifest=self.run/'active.txt'
        self.assertIn(f'expires {self.now+15}',manifest.read_text());self.assertEqual(manifest.stat().st_mode&0o777,0o644)

    def test_daemon_owns_queue_by_netlink_socket_not_parent_port_id(self):
        # nfqws2 binds before --daemon forks; the peer port remains the parent PID.
        self.queue.write_text('301 40 0 2 65535 0 0 0 1\n')
        self.netlink.write_text('sk Eth Pid Groups Rmem Wmem Dump Locks Drops Inode\n00000000 12 40 00000000 0 0 0 2 0 123456\n')
        self.observe();v=self.tick()
        self.assertEqual(v['status']['runtime']['state'],'active')
        self.assertEqual(len(v['calls']),3)

    def test_queue_socket_requires_unambiguous_netfilter_inode_owned_by_daemon(self):
        header='sk Eth Pid Groups Rmem Wmem Dump Locks Drops Inode\n'
        row='00000000 12 42 00000000 0 0 0 2 0 123456\n'
        cases={
            'foreign inode':header+row.replace('123456','999999'),
            'wrong netlink protocol':header+row.replace(' 12 ',' 0 '),
            'duplicate port':header+row+row.replace('123456','999999'),
            'duplicate inode':header+row+row.replace(' 42 ',' 99 '),
            'bad header':header.replace('Inode','Unknown')+row,
            'truncated row':header+'00000000 12 42\n',
            'oversized table':header+row+'x'*65536,
        }
        for name,table in cases.items():
            with self.subTest(name=name):
                self.netlink.write_text(table);self.observe();v=self.tick()
                self.assertEqual(v['calls'],[])
                self.assertEqual(v['status']['runtime']['code'],'queue_in_use')
                self.assertTrue(self.log.read_text())
                self.assertIn('enabled 0',(self.run/'active.txt').read_text())

    def test_queue_socket_missing_or_unreadable_fd_fails_open(self):
        descriptor=self.proc/'42/fd/5'
        for kind in ['foreign socket','plain file','missing fd directory','missing netlink','duplicate queue','oversized queue']:
            with self.subTest(kind=kind):
                if descriptor.is_symlink() or descriptor.exists():descriptor.unlink()
                if not descriptor.parent.exists():descriptor.parent.mkdir()
                self.netlink.write_text('sk Eth Pid Groups Rmem Wmem Dump Locks Drops Inode\n00000000 12 42 00000000 0 0 0 2 0 123456\n')
                self.queue.write_text('301 42 0 2 65535 0 0 0 1\n')
                if kind=='foreign socket':descriptor.symlink_to('socket:[999999]')
                elif kind=='plain file':descriptor.write_text('socket:[123456]')
                else:
                    descriptor.symlink_to('socket:[123456]')
                    if kind=='missing fd directory':descriptor.unlink();descriptor.parent.rmdir()
                    elif kind=='missing netlink':self.netlink.unlink()
                    elif kind=='duplicate queue':self.queue.write_text(self.queue.read_text()*2)
                    else:self.queue.write_text(self.queue.read_text()+'x'*65536)
                self.observe();v=self.tick();self.assertEqual(v['calls'],[])
                self.assertEqual(v['status']['runtime']['code'],'queue_in_use')
                self.assertTrue(self.log.read_text())

    def instrumented_runtime(self, marker, inserted):
        # Mutate the real fixture proc boundary at a deterministic read checkpoint.
        # Production has no hooks; dependency classes remain their unmodified sources.
        app=self.root/'runtime-app';app.mkdir(exist_ok=True)
        source=(PUBLIC/'ip-health-runtime.php').read_text()
        source=source.replace("require_once __DIR__.'/ip-health-controller.php';",'require_once '+json.dumps(str(PUBLIC/'ip-health-controller.php'))+';')
        self.assertEqual(source.count(marker),1)
        (app/'ip-health-runtime.php').write_text(source.replace(marker,inserted+marker))
        return app

    def test_queue_proof_rechecks_socket_tuple_and_descriptor_before_use(self):
        for changed in ['queue','netlink','descriptor']:
            with self.subTest(changed=changed):
                self.queue.write_text('301 42 0 2 65535 0 0 0 1\n')
                self.netlink.write_text('sk Eth Pid Groups Rmem Wmem Dump Locks Drops Inode\n00000000 12 42 00000000 0 0 0 2 0 123456\n')
                descriptor=self.proc/'42/fd/5'
                if descriptor.is_symlink():descriptor.unlink()
                descriptor.symlink_to('socket:[123456]')
                if changed=='queue':mutate='file_put_contents('+json.dumps(str(self.queue))+',"301 99 0 2 65535 0 0 0 1\\n");'
                elif changed=='netlink':mutate='file_put_contents('+json.dumps(str(self.netlink))+',"sk Eth Pid Groups Rmem Wmem Dump Locks Drops Inode\\n00000000 12 42 00000000 0 0 0 2 0 999999\\n");'
                else:mutate='unlink('+json.dumps(str(descriptor))+');symlink("socket:[999999]",'+json.dumps(str(descriptor))+');'
                app=self.instrumented_runtime('// Re-read the selected tuple',mutate)
                self.observe();v=self.tick(runtime_public=app)
                self.assertEqual(v['calls'],[]);self.assertEqual(v['status']['runtime']['code'],'queue_in_use')
                self.assertTrue(self.log.read_text())

    def test_queue_proof_rechecks_process_identity_and_boot_after_fd_walk(self):
        for changed in ['observer','core','boot']:
            with self.subTest(changed=changed):
                for pid,ticks in [(41,500),(42,600)]:
                    (self.proc/str(pid)/'stat').write_text(f'{pid} (nfqws2) S '+'0 '*18+str(ticks)+' 0\n')
                (self.proc/'sys/kernel/random/boot_id').write_text(self.boot+'\n')
                if changed=='boot':path=self.proc/'sys/kernel/random/boot_id';content='aaaaaaaa-2222-3333-4444-555555555555\n'
                else:
                    pid=42 if changed=='observer' else 41;path=self.proc/str(pid)/'stat';content=f'{pid} (reused pid) S '+'0 '*18+'999 0\n'
                mutate='file_put_contents('+json.dumps(str(path))+','+json.dumps(content)+');'
                marker="        if(trim((string)@file_get_contents($this->proc.'/sys/kernel/random/boot_id'))!==$v['boot_id']||"
                app=self.instrumented_runtime(marker,'        '+mutate)
                self.observe();v=self.tick(runtime_public=app)
                self.assertEqual(v['calls'],[])
                self.assertEqual(v['status']['runtime']['code'],'unavailable'if changed=='observer'else'core_stopped')
                self.assertTrue(self.log.read_text())

    def test_large_socket_numbers_and_legacy_netlink_dump_pointer_are_supported(self):
        for port in ['4294967295','-2147483648']:
            with self.subTest(port=port):
                inode='18446744073709551615'
                self.queue.write_text(f'301 {port} 0 2 65535 0 0 0 1\n')
                # Linux2.6 uses signed port IDs and a pointer in the Dump column.
                self.netlink.write_text(f'sk Eth Pid Groups Rmem Wmem Dump Locks Drops Inode\n00000000 12 {port} 00000000 0 0 deadbeef 2 0 {inode}\n00000000 0 {port} 00000000 0 0 0 2 0 98\n')
                descriptor=self.proc/'42/fd/5';descriptor.unlink();descriptor.symlink_to(f'socket:[{inode}]')
                self.assertEqual(self.tick()['status']['runtime']['state'],'active')

    def test_noncanonical_or_out_of_range_port_ids_fail_closed(self):
        for port in ['0','-0','042','4294967296','-2147483649']:
            with self.subTest(port=port):
                self.queue.write_text(f'301 {port} 0 2 65535 0 0 0 1\n')
                self.netlink.write_text(f'sk Eth Pid Groups Rmem Wmem Dump Locks Drops Inode\n00000000 12 {port} 00000000 0 0 0 2 0 123456\n')
                v=self.tick();self.assertEqual(v['status']['runtime']['code'],'queue_in_use')

    def test_fd_walk_is_bounded_and_duplicate_owned_descriptors_are_valid(self):
        fd=self.proc/'42/fd'
        (fd/'6').symlink_to('socket:[123456]')
        self.assertEqual(self.tick()['status']['runtime']['state'],'active')
        for number in range(10,1034):(fd/str(number)).symlink_to('/dev/null')
        self.observe();v=self.tick();self.assertEqual(v['calls'],[])
        self.assertEqual(v['status']['runtime']['code'],'queue_in_use')

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

    def test_actual_worker_enabled_read_is_inert_and_respects_saved_disable(self):
        source=PUBLIC.parents[2]/'ip-health/worker.php';app=self.root/'enabled-app';app.mkdir()
        for path in PUBLIC.glob('*.php'):shutil.copyfile(path,app/path.name)
        root_status=self.root/'root-status';root_status.write_text('Uid:\t0\t0\t0\t0\n')
        code=source.read_text().replace('/proc/self/status',str(root_status)).replace('/opt/share/nfqws-asus-web',str(app))
        code=code.replace('$store=new NfqwsIpHealthStore();',f'$store=new NfqwsIpHealthStore({json.dumps(str(self.root/"state"))},{json.dumps(str(self.run))});')
        entry=self.root/'enabled.php';entry.write_text(code)
        def enabled():return subprocess.run([PHP,'-n',str(entry),'enabled'],capture_output=True,text=True,timeout=2)
        result=enabled();self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertFalse((self.root/'state').exists(),'reading default enabled must not create a journal or lock')
        script='require $argv[1]."/ip-health-store.php";$s=new NfqwsIpHealthStore($argv[2]."/state",$argv[2]."/run");$s->configure(false,$s->status()["revision"]);'
        subprocess.run([PHP,'-n','-r',script,str(PUBLIC),str(self.root)],check=True,capture_output=True)
        saved=(self.root/'state/bans.json').read_bytes();result=enabled()
        self.assertEqual(result.returncode,1,result.stdout+result.stderr);self.assertEqual((self.root/'state/bans.json').read_bytes(),saved)

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
        index.write_text(index.read_text().replace('new NfqwsIpHealthApi()', "new NfqwsIpHealthApi(null,null,fn()=>false,fn()=>['state'=>'unavailable'])"))

    def test_password_free_session_can_read_and_explicitly_configure_without_auth_change(self):
        token=self.fixture.login();self.assertEqual(self.fixture.change('',token)[0],200)
        code,login=self.fixture.request({'cmd':'login'},'anonymous-health');self.assertEqual(code,200)
        token=login['csrf_token'];auth_before=self.fixture.auth.read_bytes()
        status={'cmd':'iphealthstatus','csrf_token':token}
        code,value=self.fixture.request(status,'anonymous-health');self.assertEqual(code,200)
        self.assertFalse((self.root/'state').exists(),'anonymous status remains read only')
        for enabled in ['0','1']:
            code,value=self.fixture.request({'cmd':'iphealthconfigure','csrf_token':token,'revision':value['revision'],'enabled':enabled},'anonymous-health')
            self.assertEqual(code,200);self.assertEqual(value['enabled'],enabled=='1')
            self.assertEqual(self.fixture.auth.read_bytes(),auth_before)
        for command,extra in [('iphealthrecheck',{'id':'all'}),('iphealthclear',{})]:
            code,value=self.fixture.request({'cmd':command,'csrf_token':token,'revision':value['revision'],**extra},'anonymous-health')
            self.assertEqual(code,200);self.assertEqual(self.fixture.auth.read_bytes(),auth_before)
        self.assertEqual(self.fixture.request({'cmd':'iphealthremove','csrf_token':token,'revision':value['revision'],'id':'a'*32},'anonymous-health'),(409,{'error':'not_found'}))
        journal=(self.root/'state/bans.json').read_bytes()
        commands=[status]+[{'cmd':command,'csrf_token':token,'revision':value['revision'],**extra} for command,extra in [('iphealthconfigure',{'enabled':'0'}),('iphealthclear',{}),('iphealthrecheck',{'id':'all'}),('iphealthremove',{'id':'a'*32})]]
        for command in commands:
            for invalid,session,want in [({**command,'csrf_token':'wrong'},'anonymous-health',403),({**command,'origin_fixture':'http://evil.test'},'anonymous-health',403),(command,'different-anonymous-session',403),({k:v for k,v in command.items() if k!='csrf_token'},'anonymous-health',400)]:
                self.assertEqual(self.fixture.request(invalid,session)[0],want)
                self.assertEqual((self.root/'state/bans.json').read_bytes(),journal)
                self.assertEqual(self.fixture.auth.read_bytes(),auth_before)
        (self.root/'update-busy').touch()
        self.assertEqual(self.fixture.request({'cmd':'iphealthconfigure','csrf_token':token,'revision':value['revision'],'enabled':'0'},'anonymous-health'),(409,{'error':'busy'}))
        self.assertEqual((self.root/'state/bans.json').read_bytes(),journal)

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

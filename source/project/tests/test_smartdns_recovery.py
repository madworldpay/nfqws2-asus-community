"""Run native recovery against real files/processes; replace firmware boundaries."""
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from test_dpi_normalize import ROOT, PHP, PUBLIC

LIB=ROOT/'asus/smartdns'
JOB='c'*32


class SmartDnsRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.shell=['/bin/busybox','ash'] if os.environ.get('SMARTDNS_TEST_BUSYBOX') else ['/bin/sh']
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.jffs=self.root/'jffs';self.jffs.mkdir(mode=0o700)
        self.opt=self.root/'opt';self.opt.mkdir();self.hooks=self.root/'scripts';self.hooks.mkdir()
        self.boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        self.uptime=self.root/'uptime';self.uptime.write_text('100.000 0\n')
        self.events=self.root/'events';self.events.touch()
        (self.root/'dns-generation').write_text('1\n')
        self.foreign=subprocess.Popen(['/bin/sleep','60'])
        self.runtime=subprocess.Popen(['/bin/sleep','60'])
        self.ticks=Path(f'/proc/{self.runtime.pid}/stat').read_text().rsplit(') ',1)[1].split()[19]
        self.exe=os.readlink(f'/proc/{self.runtime.pid}/exe')
        self.hook=self.hooks/'dnsmasq.postconf'
        self.block=subprocess.run([PHP,'-n','-r',"require $argv[1].'/smartdns-connect.php';echo AsusSmartDnsHook::BLOCK;",str(PUBLIC)],capture_output=True,check=True).stdout
        # Fixed installed paths are substituted only in this confined copy.
        self.block=self.block.replace(b'/jffs/nfqws2-asus-smartdns',str(self.jffs).encode())
        self.hook.write_bytes(b'#!/bin/sh\n# foreign\n'+self.block+b'\n# later foreign edit');self.hook.chmod(0o751)
        (self.jffs/'owned-block').write_bytes(self.block);(self.jffs/'state.lock').touch()
        self.service=self.root/'service'
        apply_dns=self.root/'apply-dns.sh'
        apply_dns.write_text('#!/bin/sh\nvalue=$(cat "'+str(self.root/'dns-generation')+'")\nprintf "%s\\n" "$((value+1))" > "'+str(self.root/'dns-generation')+'"\nif /bin/busybox grep -q "NFQWS2 SMARTDNS MANAGED" "'+str(self.hook)+'";then printf "no-resolv\\nserver=127.0.0.1#6054\\n";else printf "server=9.9.9.9\\n";fi > "'+str(self.root/'dnsmasq.conf')+'"\nchmod 600 "'+str(self.root/'dnsmasq.conf')+'"\nprintf "configured\\n" >> "'+str(self.events)+'"\n');apply_dns.chmod(0o700)
        self.service.write_text('#!/bin/sh\nprintf "restart\\n" >> "'+str(self.events)+'"\n[ ! -e "'+str(self.root/'restart-fail')+'" ] || exit 1\nif [ -f "'+str(self.root/'restart-deferred')+'" ];then (sleep 1;/bin/sh "'+str(apply_dns)+'") </dev/null >/dev/null 2>&1 &\nelse /bin/sh "'+str(apply_dns)+'";fi\n');self.service.chmod(0o700)
        self.probe=self.jffs/'dns-probe'
        self.probe.write_text('#!/bin/sh\n[ "$1" = 127.0.0.1 ] && [ "$2" = 53 ] || exit 9\nprintf "probe\\n" >> "'+str(self.events)+'"\n[ ! -e "'+str(self.root/'dns-fail')+'" ]\n');self.probe.chmod(0o700)
        self.state(phase='prepared')
        self.guards=[]
        self.library=self.root/'lib';self.library.mkdir()
        for source in ['native-state.sh','native-common.sh','recovery.sh','hook-edit.awk','runtime.sh','primary-dns.sh']:
            if (LIB/source).is_file():
                text=(LIB/source).read_text().replace('/jffs/nfqws2-asus-smartdns',str(self.jffs)).replace('/jffs/scripts',str(self.hooks)).replace('/opt/var/lib/nfqws2-asus/updates',str(self.opt/'updates')).replace('/opt/etc/nfqws-asus-web',str(self.opt)).replace('/opt/lib/nfqws2-asus',str(self.library)).replace('/tmp/etc/dnsmasq.conf',str(self.root/'dnsmasq.conf')).replace('/proc/uptime',str(self.uptime)).replace('/sbin/service',str(self.service)).replace('sd_owner=0','sd_owner='+str(os.getuid()))
                if source=='native-common.sh':
                    # Firmware primary-process identification is tested against
                    # real daemons separately. Here the boundary is a generation.
                    text+='\nsd_primary_identity() { printf "123 %s\\n" "$(cat "'+str(self.root/'dns-generation')+'")"; }\n'
                (self.jffs/source).write_text(text);(self.jffs/source).chmod(0o700)
                if source=='runtime.sh':
                    (self.library/'smartdns').mkdir();(self.library/'smartdns/runtime.sh').write_text(text);(self.library/'smartdns/runtime.sh').chmod(0o700)
        for f in self.jffs.iterdir():
            if f.name in ['state','owned-block','state.lock']:f.chmod(0o600)

    def tearDown(self):
        for p in self.guards+[self.runtime,self.foreign]:
            if p.poll() is None:p.kill()
            p.wait()
            if p.stdout:p.stdout.close()
            if p.stderr:p.stderr.close()
        self.temp.cleanup()

    def state(self,**patch):
        d=dict(schema='1',request_id=JOB,boot_id=self.boot,phase='prepared',deadline='0.000',guard_pid='0',guard_ticks='0',runtime_pid=str(self.runtime.pid),runtime_ticks=self.ticks,runtime_exe=self.exe,hook_created='0',profile_hash='d'*64)
        d.update(patch);(self.jffs/'state').write_text(''.join(k+'\t'+v+'\n' for k,v in d.items()));(self.jffs/'state').chmod(0o600)

    def read_state(self):return dict(line.split('\t',1) for line in (self.jffs/'state').read_text().splitlines())
    def run_recovery(self,command):
        if not (self.jffs/'recovery.sh').is_file():return 2,b'missing_native_recovery'
        r=subprocess.run(self.shell+[str(self.jffs/'recovery.sh'),command,JOB],capture_output=True,timeout=22)
        self.assertEqual(r.stderr,b'');return r.returncode,r.stdout

    def wait_for(self,predicate,seconds=7):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            if predicate():return
            time.sleep(.03)
        self.fail('bounded recovery event not observed')

    def guard(self):
        self.assertTrue((self.jffs/'recovery.sh').is_file(),'missing_native_recovery')
        (self.opt/'updates').mkdir(mode=0o700);(self.opt/'updates/apply.lock').touch(mode=0o600)
        (self.opt/'smartdns').mkdir(mode=0o700,exist_ok=True);(self.opt/'smartdns').chmod(0o700);(self.opt/'smartdns/config.lock').touch(mode=0o600)
        p=subprocess.Popen(['/bin/sh',str(self.jffs/'recovery.sh'),'guard',JOB],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        self.guards.append(p);self.wait_for(lambda:(self.jffs/'ready').exists())
        return p

    def test_missing_usb_restores_native_dns_before_stopping_own_runtime(self):
        # Recovery must have no executable or data dependency under /opt.
        self.opt.rmdir();rc,_=self.run_recovery('rollback');self.assertEqual(rc,0)
        self.assertEqual(self.hook.read_bytes(),b'#!/bin/sh\n# foreign\n\n# later foreign edit')
        self.assertEqual(self.hook.stat().st_mode&0o777,0o751)
        self.assertEqual(self.read_state()['phase'],'rolled_back')
        self.assertEqual(self.events.read_text(),'restart\nconfigured\nprobe\n')
        self.runtime.wait(timeout=2);self.assertIsNone(self.foreign.poll())
        self.assertEqual(self.run_recovery('rollback')[0],0)
        self.assertEqual(self.events.read_text(),'restart\nconfigured\nprobe\n')

    def test_foreign_owned_block_edit_stays_conflict_and_runtime_alive(self):
        body=self.hook.read_bytes().replace(b'postconf',b'CHANGED');self.hook.write_bytes(body)
        self.assertNotEqual(self.run_recovery('rollback')[0],0)
        self.assertEqual(self.read_state()['phase'],'conflict');self.assertEqual(self.hook.read_bytes(),body)
        self.assertEqual(self.events.read_text(),'');self.assertIsNone(self.runtime.poll())
        code=r'''require $argv[1].'/smartdns-native.php';$s=new AsusSmartDnsStore($argv[2].'/unused',(int)$argv[4]);$b=new AsusSmartDnsNativeBackend($s,new AsusSmartDnsInstaller(),['native'=>$argv[2],'library'=>$argv[3]],['owner'=>(int)$argv[4]]);echo $b->lastCode(str_repeat('c',32))??'missing';'''
        p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(self.jffs),str(LIB),str(os.getuid())],capture_output=True,text=True,timeout=4)
        self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(p.stdout,'hook_conflict')

    def test_unconfirmed_dns_or_failed_restart_keeps_candidate_alive(self):
        for failure in ['restart-fail','dns-fail']:
            with self.subTest(failure=failure):
                self.state();(self.root/failure).touch()
                self.assertNotEqual(self.run_recovery('rollback')[0],0)
                self.assertEqual(self.read_state()['phase'],'conflict');self.assertIsNone(self.runtime.poll())
                (self.root/failure).unlink()

    def test_remaining_conditional_route_keeps_runtime_alive_on_rollback(self):
        path=self.root/'apply-dns.sh'
        body=path.read_text().replace('server=9.9.9.9\\n','server=9.9.9.9\\nserver=/private.example/127.0.0.1#6054\\n')
        path.write_text(body)
        rc,_=self.run_recovery('rollback')
        self.assertNotEqual(rc,0)
        self.assertEqual(self.read_state()['phase'],'conflict')
        self.assertIsNone(self.runtime.poll())
        self.assertIn('server=/private.example/127.0.0.1#6054',(self.root/'dnsmasq.conf').read_text())

    def test_restored_config_rejects_unknown_includes_and_checks_native_server_files(self):
        server_file=self.root/'native-servers'
        source=self.jffs/'native-common.sh'
        source.write_text(source.read_text().replace('/tmp/resolv.dnsmasq',str(server_file)))
        script='. "'+str(source)+'"; sd_restored_config'
        for config,servers in [
            ('server=9.9.9.9\nservers-file='+str(server_file)+'\n','server=/private.example/127.0.0.1#6054\n'),
            ('server=9.9.9.9\nconf-file='+str(self.root/'foreign')+'\n',''),
            ('server=9.9.9.9\nrev-server=10.0.0.0/8,127.0.0.1#6054\n',''),
            ('server=9.9.9.9\nserver=/private.example/0.0.0.0#6054\n',''),
            ('server=9.9.9.9\nserver=/private.example/::ffff:0:0#6054\n',''),
        ]:
            with self.subTest(config=config):
                (self.root/'dnsmasq.conf').write_text(config);(self.root/'dnsmasq.conf').chmod(0o600)
                server_file.write_text(servers);server_file.chmod(0o600)
                r=subprocess.run(['/bin/sh','-c',script],capture_output=True,timeout=3)
                self.assertNotEqual(r.returncode,0)
        server_file.write_text('server=9.9.9.9\nserver=2606:4700:4700::1111\n')
        (self.root/'dnsmasq.conf').write_text('server=9.9.9.9\nservers-file='+str(server_file)+'\n')
        self.assertEqual(subprocess.run(['/bin/sh','-c',script],capture_output=True,timeout=3).returncode,0)

    def test_merlin_world_writable_native_resolver_data_still_gets_inspected(self):
        source=self.jffs/'native-common.sh'
        servers=self.root/'native-servers';resolver=self.root/'native-resolver'
        source.write_text(source.read_text().replace('/tmp/resolv.dnsmasq',str(servers)).replace('/tmp/resolv.conf',str(resolver)))
        config=self.root/'dnsmasq.conf'
        config.write_text('no-resolv\nservers-file='+str(servers)+'\nresolv-file='+str(resolver)+'\n');config.chmod(0o600)
        servers.write_text('server=192.0.2.1\n');servers.chmod(0o666)
        resolver.write_text('nameserver 192.0.2.1\n');resolver.chmod(0o666)
        command=['/bin/sh','-c','. "'+str(source)+'"; sd_restored_config']
        def check():return subprocess.run(command,capture_output=True,timeout=3).returncode
        self.assertEqual(check(),0,'Merlin creates native resolver data with mode 666')
        servers.write_text('server=/private.example/127.0.0.1#6054\n');self.assertNotEqual(check(),0)
        servers.write_text('server=192.0.2.1\n')
        resolver.write_text('nameserver ::1\n');self.assertNotEqual(check(),0)
        resolver.write_text('nameserver 192.0.2.1\n')
        saved=servers.read_text();servers.unlink();servers.symlink_to(resolver);self.assertNotEqual(check(),0)
        servers.unlink();servers.write_text(saved);servers.chmod(0o666)
        linked=self.root/'hardlink';os.link(servers,linked);self.assertNotEqual(check(),0)
        linked.unlink();self.assertEqual(check(),0)
        # The exception is data-only: scripts/config/hooks retain their strict permissions.
        self.hook.chmod(0o777)
        strict=subprocess.run(['/bin/sh','-c','. "'+str(source)+'"; sd_protected "'+str(self.hook)+'" -'],capture_output=True,timeout=3)
        self.assertNotEqual(strict.returncode,0)

    def config_check(self, text):
        config=self.root/'dnsmasq.conf';config.write_text(text);config.chmod(0o600)
        return subprocess.run(self.shell+['-c','. "'+str(self.jffs/'native-common.sh')+'"; sd_restored_config'],
                              capture_output=True,timeout=3)

    def test_restored_config_accepts_independent_vpn_dns_and_routing_include(self):
        include=self.root/'vpn routing.conf'
        body='filter-AAAA\nipset=/video.example/chat.example/awg_dst\nno-resolv\nserver=1.1.1.1@awg0\nserver=1.0.0.1@awg0\n'
        include.write_text(body);include.chmod(0o600)
        result=self.config_check('conf-file='+str(include)+'\n')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(include.read_text(),body)

    def test_restored_config_checks_nested_includes_for_remaining_own_routes(self):
        outer=self.root/'outer.conf';inner=self.root/'inner.conf'
        outer.write_text('conf-file='+str(inner)+'\n');outer.chmod(0o600)
        inner.write_text('server=1.1.1.1@awg0\n');inner.chmod(0o600)
        config='conf-file='+str(outer)+'\n'
        self.assertEqual(self.config_check(config).returncode,0)
        inner.write_text('server=/private.example/127.0.0.1#6054\n')
        self.assertNotEqual(self.config_check(config).returncode,0)

    def test_restored_config_accepts_include_comments_and_simple_quoted_paths(self):
        include=self.root/'vpn routing.conf';include.write_text('server=1.1.1.1@awg0\n');include.chmod(0o600)
        for value in [str(include)+' # VPN routing','"'+str(include)+'" # VPN routing']:
            with self.subTest(value=value):
                self.assertEqual(self.config_check('conf-file='+value+'\n').returncode,0)

    def test_restored_config_rejects_alternative_local_upstream_spellings(self):
        include=self.root/'local.conf';include.chmod(0o600) if include.exists() else include.touch(mode=0o600)
        for address in ['"127.0.0.1"#6054','"127.0.0.1#6054"','2130706433#6054','0x7f000001#6054',
                        '::1%lo#6054','[::1%lo]#6054','0177.0.0.1#6054','127.1#6054','::ffff:7f00:1#6054',
                        '::0.0.0.1#6054','0:0:0:0:0:0:0.0.0.1#6054','::0.0.0.0#6054']:
            with self.subTest(address=address):
                include.write_text('server=/private.example/'+address+'\n')
                self.assertNotEqual(self.config_check('conf-file='+str(include)+'\n').returncode,0)

    def test_restored_config_uses_exact_quoted_include_identity(self):
        ordinary=self.root/'include.conf';actual=self.root/'include.conf '
        ordinary.write_text('server=1.1.1.1\n');ordinary.chmod(0o600)
        actual.write_text('server=/private.example/127.0.0.1#6054\n');actual.chmod(0o600)
        config='conf-file="'+str(actual)+'"\n'
        self.assertNotEqual(self.config_check(config).returncode,0)
        actual.write_text('server=1.1.1.1\n');ordinary.write_text('server=127.0.0.1#6054\n')
        self.assertEqual(self.config_check(config).returncode,0)

    def test_restored_config_does_not_truncate_hash_inside_unquoted_path(self):
        ordinary=self.root/'include.conf';actual=self.root/'include.conf#other'
        ordinary.write_text('server=1.1.1.1\n');ordinary.chmod(0o600)
        actual.write_text('server=/private.example/127.0.0.1#6054\n');actual.chmod(0o600)
        self.assertNotEqual(self.config_check('conf-file='+str(actual)+'\n').returncode,0)

    def test_restored_config_accepts_public_numeric_upstreams_with_interface(self):
        include=self.root/'external.conf';include.touch(mode=0o600)
        for line in ['server="1.1.1.1"#53@awg0','server=2606:4700:4700::1111#53@awg0',
                     'server=/private.example/8.8.8.8','rev-server=192.0.2.0/24,8.8.8.8']:
            with self.subTest(line=line):
                include.write_text(line+'\n')
                self.assertEqual(self.config_check('conf-file='+str(include)+'\n').returncode,0)

    def test_restored_config_rejects_include_cycles(self):
        first=self.root/'first.conf';second=self.root/'second.conf'
        first.write_text('conf-file='+str(second)+'\n');first.chmod(0o600)
        second.write_text('conf-file='+str(first)+'\n');second.chmod(0o600)
        self.assertNotEqual(self.config_check('conf-file='+str(first)+'\n').returncode,0)

    def test_restored_config_bounds_include_depth_count_and_bytes(self):
        paths=[self.root/('level'+str(i)+'.conf') for i in range(33)]
        for i,path in enumerate(paths):
            path.write_text('conf-file='+str(paths[i+1])+'\n' if i+1<len(paths) else 'server=1.1.1.1\n')
            path.chmod(0o600)
        self.assertNotEqual(self.config_check('conf-file='+str(paths[0])+'\n').returncode,0)
        for path in paths:path.write_text('server=1.1.1.1\n')
        self.assertNotEqual(self.config_check(''.join('conf-file='+str(path)+'\n' for path in paths)).returncode,0)
        paths[0].write_text('#'+('x'*262144)+'\n')
        self.assertNotEqual(self.config_check('conf-file='+str(paths[0])+'\n').returncode,0)

    def test_restored_config_does_not_execute_dynamic_config(self):
        include=self.root/'dynamic.conf';marker=self.root/'executed'
        program=self.root/'generator';program.write_text('#!/bin/sh\ntouch "'+str(marker)+'"\n');program.chmod(0o700)
        include.write_text('conf-script='+str(program)+'\n');include.chmod(0o600)
        self.assertNotEqual(self.config_check('conf-file='+str(include)+'\n').returncode,0)
        self.assertFalse(marker.exists())

    def test_restored_config_rejects_unsafe_include_objects(self):
        include=self.root/'include.conf';target=self.root/'target.conf'
        target.write_text('server=1.1.1.1\n');target.chmod(0o600)
        config='conf-file='+str(include)+'\n'
        include.symlink_to(target)
        self.assertNotEqual(self.config_check(config).returncode,0);include.unlink()
        os.mkfifo(include)
        self.assertNotEqual(self.config_check(config).returncode,0);include.unlink()
        include.write_text('server=1.1.1.1\n');include.chmod(0o666)
        self.assertNotEqual(self.config_check(config).returncode,0);include.chmod(0o600)
        os.link(include,self.root/'linked.conf')
        self.assertNotEqual(self.config_check(config).returncode,0)

    def test_rollback_with_vpn_include_preserves_foreign_dns_and_routing(self):
        include=self.root/'vpn.conf';body='filter-AAAA\nipset=/video.example/awg_dst\nno-resolv\nserver=1.1.1.1@awg0\n'
        include.write_text(body);include.chmod(0o600)
        script=self.root/'apply-dns.sh'
        script.write_text(script.read_text()+'printf "conf-file=%s\\n" "'+str(include)+'" >> "'+str(self.root/'dnsmasq.conf')+'"\n')
        self.assertEqual(self.run_recovery('rollback')[0],0)
        self.assertEqual(self.read_state()['phase'],'rolled_back')
        self.assertEqual(include.read_text(),body)
        self.assertEqual(self.hook.read_bytes(),b'#!/bin/sh\n# foreign\n\n# later foreign edit')
        self.runtime.wait(timeout=2);self.assertIsNone(self.foreign.poll())

    def test_existing_exact_owned_block_is_not_duplicated_and_remains_removable(self):
        original=self.hook.read_bytes()
        (self.jffs/'hook-original').write_bytes(original);(self.jffs/'hook-original').chmod(0o600)
        script='. "'+str(self.jffs/'native-common.sh')+'"; sd_state_load && sd_install_hook'
        r=subprocess.run(['/bin/sh','-c',script],capture_output=True,timeout=3)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(self.hook.read_bytes(),original)
        self.assertEqual(self.run_recovery('rollback')[0],0)
        self.assertNotIn(b'NFQWS2 SMARTDNS MANAGED',self.hook.read_bytes())

    def test_pid_reuse_cannot_stop_an_unrelated_process(self):
        self.state(runtime_ticks=str(int(self.ticks)+1))
        self.assertEqual(self.run_recovery('rollback')[0],0)
        self.assertIsNone(self.runtime.poll());self.assertIsNone(self.foreign.poll())

    def test_guard_ready_before_forwarding_and_timeout_uses_uptime(self):
        p=self.guard();state=self.read_state();self.assertEqual(state['guard_pid'],str(p.pid))
        self.assertEqual(state['phase'],'prepared');self.assertEqual(self.events.read_text(),'')
        state['phase']='awaiting_confirmation';state['deadline']='220.000'
        (self.jffs/'state').write_text(''.join(k+'\t'+v+'\n' for k,v in state.items()))
        self.uptime.write_text('221.000 0\n');self.wait_for(lambda:self.read_state()['phase']=='rolled_back')
        self.runtime.wait(timeout=2);p.wait(timeout=3)

    def test_confirm_requires_fresh_dns_and_releases_updater_lease(self):
        import fcntl
        p=self.guard();self.arm_forward()
        with (self.opt/'updates/apply.lock').open('r+') as lease:
            with self.assertRaises(BlockingIOError):fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.assertEqual(self.run_recovery('confirm')[0],0)
            self.wait_for(lambda:self.read_state()['phase']=='confirmed')
            def released():
                try:fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB);return True
                except BlockingIOError:return False
            self.wait_for(released)
        self.assertIsNone(p.poll());self.assertIsNone(self.runtime.poll())
        # A confirmed guard stays alive and notices a lost runtime later.
        self.runtime.terminate();self.runtime.wait()
        self.wait_for(lambda:self.read_state()['phase']=='rolled_back')

    def test_guard_owns_runtime_launch_before_issuing_ready(self):
        self.assertTrue((LIB/'runtime.sh').is_file(),'missing_native_runtime')
        self.runtime.terminate();self.runtime.wait()
        engine=self.library/'smartdns-engine';engine.mkdir(mode=0o700)
        bundle=engine/('a'*64);bundle.mkdir(mode=0o700);(engine/'current').symlink_to('a'*64)
        code=self.root/'engine.c';code.write_text('#include <unistd.h>\nint main(void){for(;;)sleep(1);}\n')
        subprocess.run(['gcc',str(code),'-o',str(bundle/'smartdns')],capture_output=True,check=True)
        (bundle/'smartdns').chmod(0o700)
        run=self.opt/'smartdns/jobs'/JOB;run.mkdir(parents=True,mode=0o700)
        (run/'runtime.conf').write_text('bind 127.0.0.1:6054\n');(run/'runtime.conf').chmod(0o600)
        (run/'engine.digest').write_text('a'*64+'\n');(run/'engine.digest').chmod(0o600)
        self.state(runtime_pid='0',runtime_ticks='0',runtime_exe='')
        p=self.guard();state=self.read_state();pid=int(state['runtime_pid'])
        try:
            self.assertGreater(pid,1);self.assertEqual(state['runtime_exe'],str(bundle/'smartdns'))
            self.assertEqual(os.readlink(f'/proc/{pid}/exe'),str(bundle/'smartdns'))
            self.arm_forward()
            self.assertEqual(self.run_recovery('confirm')[0],0)
            # Mapped code may keep running after the USB file disappears.
            (bundle/'smartdns').unlink()
            self.wait_for(lambda:self.read_state()['phase']=='rolled_back')
            self.wait_for(lambda:not Path(f'/proc/{pid}').exists())
            p.wait(timeout=3)
        finally:
            if Path(f'/proc/{pid}').exists():os.kill(pid,9)

    def test_forward_installs_only_viewed_hook_and_sets_native_120_second_deadline(self):
        original=b'#!/bin/sh\n# foreign';self.hook.write_bytes(original)
        (self.jffs/'hook-original').write_bytes(original);(self.jffs/'hook-original').chmod(0o600)
        p=self.guard()
        self.assertEqual(self.run_recovery('forward')[0],0)
        self.assertEqual(self.hook.read_bytes(),original+self.block)
        state=self.read_state();self.assertEqual(state['phase'],'awaiting_confirmation');self.assertEqual(state['deadline'],'220.000')
        self.assertEqual(self.events.read_text(),'restart\nconfigured\nprobe\n')
        self.assertEqual(self.run_recovery('rollback')[0],0);p.wait(timeout=3)

    def arm_forward(self):
        original=b'#!/bin/sh\n# foreign';self.hook.write_bytes(original)
        (self.jffs/'hook-original').write_bytes(original);(self.jffs/'hook-original').chmod(0o600)
        self.assertEqual(self.run_recovery('forward')[0],0)

    def test_async_restart_cannot_confirm_an_answer_from_the_old_daemon(self):
        p=self.guard();(self.root/'restart-deferred').touch()
        try:
            self.arm_forward()
            self.assertEqual(self.events.read_text(),'restart\nconfigured\nprobe\n')
        finally:
            self.wait_for(lambda:'configured' in self.events.read_text())
            (self.root/'restart-deferred').unlink()
            self.run_recovery('rollback');p.wait(timeout=3)

    def test_failed_terminal_state_write_never_causes_a_restart_loop(self):
        import time
        file=self.jffs/'native-state.sh';text=file.read_text().replace('sd_state_save() {','sd_original_state_save() {')
        text+='\nsd_state_save() { if [ "$sd_phase" = rolled_back ] && [ -f "'+str(self.root/'state-write-fail')+'" ];then return 1;fi;sd_original_state_save; }\n'
        file.write_text(text)
        p=self.guard();self.arm_forward();(self.root/'state-write-fail').touch();self.uptime.write_text('221.000 0\n')
        try:
            self.wait_for(lambda:self.runtime.poll() is not None)
            time.sleep(2.5)
            self.assertEqual(self.events.read_text().count('restart\n'),2)
        finally:
            (self.root/'state-write-fail').unlink();self.run_recovery('rollback');p.wait(timeout=3)

    def test_foreign_edit_between_preview_and_forward_never_gets_overwritten(self):
        original=b'#!/bin/sh\n# foreign';changed=original+b'\n# newly edited'
        (self.jffs/'hook-original').write_bytes(original);(self.jffs/'hook-original').chmod(0o600);self.hook.write_bytes(changed)
        p=self.guard()
        self.assertNotEqual(self.run_recovery('forward')[0],0);self.assertEqual(self.hook.read_bytes(),changed)
        self.assertEqual(self.events.read_text(),'');self.assertIsNone(self.runtime.poll())
        self.assertEqual(self.run_recovery('rollback')[0],0);p.wait(timeout=3)


if __name__=='__main__':unittest.main()

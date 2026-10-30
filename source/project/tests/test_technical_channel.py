"""Signed temporary support links and exact, crash-safe public-key rollback."""
import base64
import json
import os
import shutil
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding, ed25519

ROOT = Path(__file__).resolve().parents[1]
PHP = os.environ.get('PHP_NATIVE_TEST_BINARY') or shutil.which('php')
PUBLIC = ROOT / 'webui/web/public'


def b64(v):
    return base64.urlsafe_b64encode(v).decode().rstrip('=')


@unittest.skipUnless(PHP, 'native PHP interpreter required')
class TechnicalChannelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.pem = cls.key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        cls.pub = ed25519.Ed25519PrivateKey.generate().public_key().public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH).decode()

    def php(self, script, data):
        call = "$v=json_decode(stream_get_contents(STDIN),true); require $argv[1].'/technical-channel.php'; try { $r=(function($v){" + script + "})($v); echo json_encode(['ok'=>$r]); } catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}"
        r = subprocess.run([PHP, '-n', '-r', call, str(PUBLIC)], input=json.dumps(data), text=True, capture_output=True, timeout=10)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr, '')
        return json.loads(r.stdout)

    def payload(self):
        now = int(time.time())
        # Actual Dropbear Ed25519 secret-key wire format, only a tunnel credential.
        priv = ed25519.Ed25519PrivateKey.generate()
        seed = priv.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
        pub = priv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        dbkey = b'\0\0\0\x0bssh-ed25519\0\0\0\x40' + seed + pub
        return dict(schema_version=1, purpose='technical_channel', session_id='a'*32,
                    issued_at=now-1, expires_at=now+600, server='94.103.80.201', server_port=22,
                    server_user='nfqs-'+('a'*12), remote_port=44900,
                    host_key=self.pub, operator_key=self.pub, tunnel_key=base64.b64encode(dbkey).decode())

    def link(self, data=None, raw=None):
        raw = raw if raw is not None else json.dumps(data or self.payload(), separators=(',', ':')).encode()
        sig = self.key.sign(raw, padding.PKCS1v15(), hashes.SHA256())
        return 'https://github.com/madworldpay/nfqws2-asus-community#technical-channel=v1.'+b64(raw)+'.'+b64(sig)

    def verify(self, link):
        return self.php("return AsusTechnicalInvite::verify($v['link'],$v['pem'],time());",dict(link=link,pem=self.pem))

    def test_valid_offline_link_and_migration(self):
        data=self.payload()
        self.assertEqual(self.verify(self.link(data))['ok'],data)
        data['server']='1.1.1.1'; data['server_port']=2200; data['host_key']=self.pub
        self.assertEqual(self.verify(self.link(data))['ok'],data)

    def test_reject_forged_expired_future_private_hosts_and_extra_fields(self):
        self.assertEqual(self.verify(self.link()[:-1]+'x').get('error'),'invalid_invitation')
        for patch in [dict(expires_at=int(time.time())-1),dict(issued_at=int(time.time())+600),
                      dict(expires_at=int(time.time())+90000),dict(server='127.0.0.1'),dict(server='192.168.1.1'),
                      dict(server='169.254.169.254'),dict(server='100.64.0.1'),dict(server='192.0.2.1'),dict(server='203.0.113.1'),dict(server='224.0.0.1'),dict(server='01.2.3.4'),dict(server='vps.example'),dict(server_user='root'),
                      dict(server_user='x;id'),dict(remote_port=22),dict(purpose='shell'),dict(command='id'),
                      dict(server_port=True),dict(tunnel_key='a'*100)]:
            data=self.payload(); data.update(patch)
            with self.subTest(patch=patch):
                self.assertIn('error',self.verify(self.link(data)))
        raw=json.dumps(self.payload()).encode().replace(b'"schema_version": 1',b'"schema_version": 1, "schema_version": 1')
        self.assertIn('error',self.verify(self.link(raw=raw)))
        self.assertIn('error',self.verify('x'*18000))
        self.assertIn('error',self.verify(self.link().replace('https://github.com/','https://evil.test/')))

    def journal(self, script, root, **data):
        return self.php("$j=new AsusTechnicalJournal($v['root'].'/journal.json', $v['owner']);"+script,
                        dict(root=str(root),owner=os.getuid(),**data))

    def test_restore_exact_original_missing_files_modes_and_final_newline(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); (root/'keys').write_bytes(b'existing-without-lf');(root/'keys').chmod(0o640)
            changes=[dict(path=str(root/'keys'),line='owned-key'),dict(path=str(root/'missing'),line='owned-host')]
            self.assertEqual(self.journal("$j->apply($v['changes']); return true;",root,changes=changes),{'ok':True})
            self.assertTrue((root/'journal.json').is_file())
            self.assertEqual(self.journal("$j->restore(); return true;",root),{'ok':True})
            self.assertEqual((root/'keys').read_bytes(),b'existing-without-lf')
            self.assertEqual((root/'keys').stat().st_mode&0o777,0o640)
            self.assertFalse((root/'missing').exists())
            self.assertFalse((root/'journal.json').exists())

    def test_rollback_preserves_unrelated_concurrent_key_and_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); f=root/'keys'; f.write_bytes(b'old-without-lf'); f.chmod(0o600)
            self.assertEqual(self.journal("$j->apply($v['changes']); return true;",root,changes=[dict(path=str(f),line='owned-key')]), {'ok':True})
            with f.open('ab') as o:o.write(b'unrelated-key\n')
            self.assertEqual(self.journal("$j->restore(); return true;",root),{'ok':True})
            self.assertEqual(f.read_bytes(),b'old-without-lf\nunrelated-key\n')
            (root/'link').symlink_to(f)
            r=self.journal("$j->apply($v['changes']); return true;",root,changes=[dict(path=str(root/'link'),line='bad')])
            self.assertEqual(r.get('error'),'unsafe_key_file')
            self.assertNotIn(b'bad',f.read_bytes())

    def test_runtime_status_exposes_no_invitation_and_unknown_stop_is_idempotent(self):
        # A private, trusted fixture directory avoids touching host router state.
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self.php("$c=new AsusTechnicalChannel(['runtime'=>$v['root'].'/run','journal'=>$v['root'].'/journal.json','owner'=>$v['owner']]);return [$c->status(),$c->stop()];",dict(root=d,owner=os.getuid())),
                             {'ok':[{'state':'idle','session_id':None,'expires_at':None,'code':None}, {'state':'idle','session_id':None,'expires_at':None,'code':None}]})

    def test_oversized_key_files_refused_before_any_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); f=root/'keys'; f.write_bytes(b'x'*65536); f.chmod(0o600)
            r=self.journal("$j->apply($v['changes']); return true;",root,changes=[dict(path=str(f),line='owned')])
            self.assertEqual(r.get('error'),'unsafe_key_file')
            self.assertEqual(f.read_bytes(),b'x'*65536)
            self.assertFalse((root/'journal.json').exists())

    def test_only_trusted_entware_alias_is_accepted_and_pinned(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); target=root/'entware'; target.mkdir(mode=0o700)
            alias=root/'opt'; alias.symlink_to(target, target_is_directory=True)
            module=root/'files.php'
            module.write_text((PUBLIC/'technical-channel-files.php').read_text().replace("'/opt'",repr(str(alias))))
            code="require $argv[1]; try { AsusTechnicalFiles::write($argv[2].'/etc/keys','original',0600,(int)$argv[3]); echo AsusTechnicalFiles::read($argv[2].'/etc/keys',(int)$argv[3])['raw']; } catch(Throwable $e){echo $e->getMessage();}"
            run=lambda script:subprocess.run([PHP,'-n','-r',script,str(module),str(alias),str(os.getuid())],text=True,capture_output=True,timeout=10)
            self.assertEqual(run(code).stdout,'original')
            (target/'child').symlink_to(target/'etc',target_is_directory=True)
            self.assertEqual(run(code.replace('/etc/keys','/child/keys')).stdout,'unsafe_key_file')
            # Pin the same boundary for the lifetime of the request/worker.
            other=root/'other'; other.mkdir(mode=0o700)
            change="require $argv[1]; AsusTechnicalFiles::directory($argv[2],(int)$argv[3]);unlink($argv[2]);symlink("+repr(str(other))+",$argv[2]);try{AsusTechnicalFiles::directory($argv[2],(int)$argv[3]);echo 'accepted';}catch(Throwable $e){echo $e->getMessage();}"
            self.assertEqual(run(change).stdout,'unsafe_key_file')

    def test_old_activation_cannot_cleanup_replacement_or_adopt_new_worker(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); runtime=root/'run'; runtime.mkdir(mode=0o700)
            session='a'*32
            identity=self.php("return AsusTechnicalProcess::identity($v['pid']);",dict(pid=os.getpid()))['ok']
            state=dict(state='connected',session_id=session,activation_id=session,identity=identity,expires_at=int(time.time())+30,uptime_deadline=1e12)
            statefile=runtime/'state.json'
            def save(v):
                tmp=runtime/'new';tmp.write_text(json.dumps(v));tmp.chmod(0o600);tmp.replace(statefile)
            save(state)
            marker=root/'marker'
            code="require $argv[1].'/technical-channel.php';$c=new AsusTechnicalChannel(['runtime'=>$argv[2],'journal'=>$argv[3],'owner'=>(int)$argv[4],'busybox'=>'/usr/bin/busybox']);exit($c->command($argv[5]));"
            env=os.environ|{'SSH_CONNECTION':'127.0.0.1 40000 127.0.0.1 40001','SSH_ORIGINAL_COMMAND':'sleep 2; touch '+str(marker)}
            guard=subprocess.Popen([PHP,'-n','-r',code,str(PUBLIC),str(runtime),str(root/'journal.json'),str(os.getuid()),session],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                time.sleep(.4)
                replacement=state|dict(activation_id='b'*32)
                save(replacement)
                out,err=guard.communicate(timeout=5)
                self.assertEqual(err,'');self.assertNotEqual(guard.returncode,0,out)
                time.sleep(2)
                self.assertFalse(marker.exists(),'old command survived invitation reuse')
                result=self.php("$c=new AsusTechnicalChannel(['runtime'=>$v['runtime'],'journal'=>$v['journal'],'owner'=>$v['owner']]);$m=new ReflectionMethod($c,'clean');return $m->invoke($c,$v['old'],'failed','interrupted');",dict(runtime=str(runtime),journal=str(root/'journal.json'),owner=os.getuid(),old=state))
                self.assertEqual(result['ok']['activation_id'],'b'*32)
                self.assertEqual(json.loads(statefile.read_text()),replacement)
            finally:
                if guard.poll() is None:guard.kill();guard.wait()

    def test_stock_temporary_parent_is_journaled_and_restored_after_stop_and_reboot(self):
        # Removing the permission lease breaks valid stock /tmp0777 starts;
        # restoring by pathname alone would alter a replacement directory.
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); temporary=root/'temporary'; temporary.mkdir(); temporary.chmod(0o777)
            cfg=dict(runtime=str(temporary/'run'),journal=str(root/'journal.json'),temporary_parent=str(temporary),owner=os.getuid())
            result=self.php("$c=new AsusTechnicalChannel($v);$m=new ReflectionMethod($c,'lock');$h=$m->invoke($c);$s=['state'=>'connecting','session_id'=>str_repeat('a',32),'activation_id'=>str_repeat('a',32),'identity'=>AsusTechnicalProcess::identity(getmypid()),'expires_at'=>time()+30,'uptime_deadline'=>AsusTechnicalProcess::uptime()+30];AsusTechnicalFiles::write($v['runtime'].'/state.json',json_encode($s),0600,$v['owner']);$u=new ReflectionMethod($c,'unlock');$u->invoke($c,$h);return [file_exists($v['journal'].'.permissions'),fileperms($v['temporary_parent'])&07777];",cfg)
            self.assertEqual(result,{'ok':[True,0o1777]})
            self.assertEqual(self.php("$c=new AsusTechnicalChannel($v);return $c->stop()['state'];",cfg),{'ok':'failed'})
            self.assertEqual(temporary.stat().st_mode&0o7777,0o777)
            self.assertFalse((root/'journal.json.permissions').exists())
            self.assertEqual(self.php("$p=new AsusTechnicalPermissions($v['journal'].'.permissions',$v['temporary_parent'],$v['owner']);$p->prepare();return true;",cfg),{'ok':True})
            # Simulate /tmp recreation while its persistent lease survives.
            temporary.rename(root/'old-temporary');temporary.mkdir(mode=0o755)
            self.assertEqual(self.php("$p=new AsusTechnicalPermissions($v['journal'].'.permissions',$v['temporary_parent'],$v['owner']);$p->restore();return true;",cfg),{'ok':True})
            self.assertEqual(temporary.stat().st_mode&0o7777,0o755)

    def test_failed_start_restores_stock_permissions_without_status_poll(self):
        # A failed credential/state write must roll back the newly admitted
        # activation before returning; no guardian or later status call exists.
        for failure in ['oversized_invitation','linked_invitation','oversized_state']:
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as d:
                root=Path(d);temporary=root/'temporary';temporary.mkdir();temporary.chmod(0o777)
                runtime=temporary/'run';runtime.mkdir(mode=0o700);library=root/'library';library.mkdir(mode=0o700)
                for name in ['session.sh','guard.sh']:(library/name).write_text('fixture must not launch')
                pem=root/'public.pem';pem.write_text(self.pem);pem.chmod(0o600)
                target=root/'unrelated';target.write_text('owner data');target.chmod(0o600)
                path=runtime/('state.json' if failure=='oversized_state' else 'invitation')
                if failure=='linked_invitation':path.symlink_to(target)
                else:path.write_text('x'*600000);path.chmod(0o600)
                cfg=dict(runtime=str(runtime),journal=str(root/'journal.json'),temporary_parent=str(temporary),owner=os.getuid(),public_key=str(pem),library=str(library),php=PHP,busybox='/usr/bin/busybox',ssh='/bin/true')
                result=self.php("$c=new AsusTechnicalChannel($v['config']);try{$c->start($v['link']);return 'accepted';}catch(Throwable $e){return $e->getMessage();}",dict(config=cfg,link=self.link()))
                self.assertEqual(result,{'ok':'unsafe_key_file'})
                self.assertEqual(temporary.stat().st_mode&0o7777,0o777,'failed start left the global permission repair active')
                self.assertFalse((root/'journal.json.permissions').exists())
                self.assertEqual(target.read_text(),'owner data')
                if failure!='oversized_state' and (runtime/'state.json').exists():
                    self.assertEqual(json.loads((runtime/'state.json').read_text())['state'],'failed')

    def test_busy_start_keeps_existing_activation_and_permission_lease(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);temporary=root/'temporary';temporary.mkdir();temporary.chmod(0o777)
            runtime=temporary/'run';runtime.mkdir(mode=0o700);pem=root/'public.pem';pem.write_text(self.pem);pem.chmod(0o600)
            identity=self.php("return AsusTechnicalProcess::identity($v['pid']);",dict(pid=os.getpid()))['ok']
            state=dict(state='connected',session_id='b'*32,activation_id='b'*32,identity=identity,expires_at=int(time.time())+60,uptime_deadline=1e12)
            statefile=runtime/'state.json';statefile.write_text(json.dumps(state));statefile.chmod(0o600)
            cfg=dict(runtime=str(runtime),journal=str(root/'journal.json'),temporary_parent=str(temporary),owner=os.getuid(),public_key=str(pem))
            result=self.php("$c=new AsusTechnicalChannel($v['config']);try{$c->start($v['link']);return 'accepted';}catch(Throwable $e){return $e->getMessage();}",dict(config=cfg,link=self.link()))
            self.assertEqual(result,{'ok':'busy'})
            self.assertEqual(json.loads(statefile.read_text()),state)
            self.assertEqual(temporary.stat().st_mode&0o7777,0o1777)
            self.assertTrue((root/'journal.json.permissions').exists())
            self.assertFalse((runtime/'invitation').exists())

    def test_permission_repair_rejects_links_and_other_unsafe_modes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); target=root/'target';target.mkdir();target.chmod(0o777)
            alias=root/'link';alias.symlink_to(target)
            script="$p=new AsusTechnicalPermissions($v['journal'],$v['temporary'],$v['owner']);$p->prepare();return true;"
            for path in [alias,target]:
                if path==target:target.chmod(0o775)
                self.assertEqual(self.php(script,dict(journal=str(root/'lease'),temporary=str(path),owner=os.getuid())).get('error'),'unsafe_key_file')
                self.assertFalse((root/'lease').exists())

    def test_command_without_setsid_runs_and_revocation_kills_descendants_only(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);runtime=root/'run';runtime.mkdir(mode=0o700)
            # This executable exposes only the measured packaged applets.
            busy=root/'busybox';busy.write_text('#!/bin/sh\ncase "$1" in sh|start-stop-daemon|usleep) exec /usr/bin/busybox "$@";; *) exit 127;; esac\n');busy.chmod(0o700)
            session='a'*32;identity=self.php("return AsusTechnicalProcess::identity($v['pid']);",dict(pid=os.getpid()))['ok']
            state=dict(state='connected',session_id=session,activation_id=session,identity=identity,expires_at=int(time.time())+30,uptime_deadline=1e12)
            statefile=runtime/'state.json';statefile.write_text(json.dumps(state));statefile.chmod(0o600)
            code="require $argv[1].'/technical-channel.php';$c=new AsusTechnicalChannel(['runtime'=>$argv[2],'journal'=>$argv[3],'owner'=>(int)$argv[4],'busybox'=>$argv[5]]);exit($c->command($argv[6]));"
            argv=[PHP,'-n','-r',code,str(PUBLIC),str(runtime),str(root/'journal.json'),str(os.getuid()),str(busy),session]
            env=os.environ|{'SSH_CONNECTION':'127.0.0.1 40000 127.0.0.1 40001','SSH_ORIGINAL_COMMAND':"printf ready; exit 7"}
            run=subprocess.run(argv,env=env,text=True,capture_output=True,timeout=10)
            self.assertEqual((run.returncode,run.stdout,run.stderr),(7,'ready',''))
            marker=root/'marker';started=root/'started'; unrelated=subprocess.Popen(['/bin/sleep','20'])
            env['SSH_ORIGINAL_COMMAND']=f'touch {started}; (sleep 2; touch {marker}) & wait'
            guard=subprocess.Popen(argv,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                deadline=time.monotonic()+3
                while not started.exists() and guard.poll() is None and time.monotonic()<deadline:time.sleep(.03)
                self.assertTrue(started.exists(),'command must really start before revocation')
                replacement=state|dict(activation_id='b'*32);tmp=runtime/'new';tmp.write_text(json.dumps(replacement));tmp.chmod(0o600);tmp.replace(statefile)
                out,err=guard.communicate(timeout=4)
                self.assertEqual((out,err),('',''));self.assertNotEqual(guard.returncode,0)
                time.sleep(2.1);self.assertFalse(marker.exists(),'a nested descendant survived cancellation')
                self.assertIsNone(unrelated.poll(),'unrelated process was killed')
            finally:
                if guard.poll() is None:guard.kill();guard.wait()
                unrelated.terminate();unrelated.wait()

    def test_cleanup_retains_only_bounded_stage_reason(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);runtime=root/'run';runtime.mkdir(mode=0o700)
            state=dict(state='connecting',activation_id='a'*32,session_id='a'*32,stage='local_server')
            (runtime/'state.json').write_text(json.dumps(state));(runtime/'state.json').chmod(0o600)
            (runtime/'ssh.log').write_text('Multicall binary: /secret/path\npassword=secret invitation=private\n');(runtime/'ssh.log').chmod(0o600)
            result=self.php("$c=new AsusTechnicalChannel(['runtime'=>$v['root'].'/run','journal'=>$v['root'].'/journal.json','owner'=>$v['owner']]);$m=new ReflectionMethod($c,'clean');$m->invoke($c,$v['state'],'failed','launch_failed');return $c->status();",dict(root=d,owner=os.getuid(),state=state))
            self.assertEqual(result['ok']['diagnostic'],dict(stage='local_server',reason='multicall_usage'))
            self.assertFalse((runtime/'ssh.log').exists())
            self.assertNotIn('secret',json.dumps(result))

    def test_oversized_transport_log_cannot_block_key_cleanup(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);runtime=root/'run';runtime.mkdir(mode=0o700)
            state=dict(state='connecting',activation_id='a'*32,session_id='a'*32,stage='transport')
            (runtime/'state.json').write_text(json.dumps(state));(runtime/'state.json').chmod(0o600)
            (runtime/'ssh.log').write_text('Permission denied\n'+'x'*1100000);(runtime/'ssh.log').chmod(0o600)
            result=self.php("$c=new AsusTechnicalChannel(['runtime'=>$v['root'].'/run','journal'=>$v['root'].'/journal.json','owner'=>$v['owner']]);$j=new AsusTechnicalJournal($v['root'].'/journal.json',$v['owner']);$j->apply([['path'=>$v['root'].'/keys','line'=>'owned']]);$m=new ReflectionMethod($c,'clean');$m->invoke($c,$v['state'],'failed','connection_failed');return $c->status();",dict(root=d,owner=os.getuid(),state=state))
            self.assertEqual(result.get('ok',{}).get('diagnostic'),dict(stage='transport',reason='authentication_failed'))
            self.assertFalse((root/'keys').exists());self.assertFalse((runtime/'ssh.log').exists())

    def test_guard_requires_live_matching_worker_tunnel_source_and_both_deadlines(self):
        data=self.php("return AsusTechnicalProcess::identity(getmypid());",{})['ok']
        # Previous PHP has exited, so a stale but correctly formatted identity fails closed.
        self.assertEqual(self.php("return AsusTechnicalProcess::active($v['state'],time(),AsusTechnicalProcess::uptime());",
          dict(state=dict(identity=data,expires_at=int(time.time())+100,uptime_deadline=1e12))),{'ok':False})
        script="""$s=['identity'=>AsusTechnicalProcess::identity(getmypid()),'expires_at'=>time()+10,'uptime_deadline'=>AsusTechnicalProcess::uptime()+10,'state'=>'connected'];
        $a=AsusTechnicalProcess::active($s,time(),AsusTechnicalProcess::uptime());
        $s['uptime_deadline']=0; $b=AsusTechnicalProcess::active($s,time()-1000,AsusTechnicalProcess::uptime());
        return [$a,$b];"""
        self.assertEqual(self.php(script,{}),{'ok':[True,False]})

if __name__=='__main__':unittest.main()

# Run against the real index.php admission code. Only router paths/service leases
# are substituted by the existing fixture; authentication is not mocked.
from test_auth_api import PasswordApiTests

@unittest.skipUnless(PHP, 'native PHP required')
class TechnicalChannelApiTests(PasswordApiTests):
    __unittest_skip__ = not bool(PHP)
    def setUp(self):
        import test_auth_api
        test_auth_api.PHP=PHP
        super().setUp()
        import shutil
        for name in [p.name for p in PUBLIC.glob('*.php') if not (self.base/p.name).exists()]:
            shutil.copyfile(PUBLIC/name,self.base/name)

    def test_channel_requires_password_csrf_and_same_origin(self):
        self.assertEqual(self.request({'cmd':'technicalstart','invitation':'bad','csrf_token':'x'},'visitor')[0],401)
        token=self.login()
        self.assertEqual(self.request({'cmd':'technicalstart','invitation':'bad','consent':'temporary_root_access','csrf_token':'0'*64})[0],403)
        self.assertEqual(self.request({'cmd':'technicalstart','invitation':'bad','consent':'temporary_root_access','csrf_token':token})[0],403)
        self.assertEqual(self.change('',token)[0],200)
        token=self.request({'cmd':'login'},'anonymous')[1]['csrf_token']
        for cmd in ['technicalstart','technicalstatus','technicalstop']:
            code,data=self.request({'cmd':cmd,'invitation':'bad','consent':'temporary_root_access','csrf_token':token},'anonymous')
            self.assertEqual((code,data),(403,{'error':'auth_required'}))

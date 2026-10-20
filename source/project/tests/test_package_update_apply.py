"""Run the actual worker, native lock launcher, services and installer as processes."""
import base64
import fcntl
import hashlib
import http.server
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from test_dpi_normalize import PUBLIC, ROOT
from test_package_update_guard import NATIVE
import test_package_update_prepare as prepare_fixtures
import test_package_update_worker as lifecycle_fixtures


@unittest.skipUnless(NATIVE.is_file(), 'native PHP fixture required')
class PackageUpdateApplyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.keys=tempfile.TemporaryDirectory();cls.key=Path(cls.keys.name)/'key'
        subprocess.run(['openssl','genpkey','-algorithm','RSA','-pkeyopt','rsa_keygen_bits:3072','-out',str(cls.key)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        cls.public=subprocess.check_output(['openssl','pkey','-in',str(cls.key),'-pubout']).decode()
    @classmethod
    def tearDownClass(cls):cls.keys.cleanup()
    def setUp(self):
        self.assertTrue((PUBLIC/'update-worker.php').is_file(), 'worker missing')
        self.fixture=prepare_fixtures.PackageUpdatePrepareTests('test_exact_ipk_and_installed_dependencies_are_required');self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.service=lifecycle_fixtures.PackageUpdateLifecycleTests('test_running_intent_stops_then_starts_exactly_once')
        # This helper supplies real executable init fixtures, not a mocked lifecycle.
        self.service.setUp();self.addCleanup(self.service.doCleanups)
        self.base=self.fixture.base;self.opt=self.fixture.fixture()[0];(self.opt/'lib/opkg').mkdir(parents=True)
        self.status=self.opt/'lib/opkg/status';self.status.write_text(self.fixture.status());self.status.chmod(0o600)
        self.state=self.base/'state';self.state.mkdir(mode=0o700);(self.state/'operations').mkdir(mode=0o700)
        self.id='a'*32;self.op=self.state/'operations'/self.id;self.op.mkdir(mode=0o700);self.runtime=self.op/'runtime';self.runtime.mkdir(mode=0o700)
        # Production stages top-level PHP files only, never frontend assets.
        self.application=self.runtime/'app';self.application.mkdir(mode=0o700)
        for source in PUBLIC.glob('*.php'):shutil.copyfile(source,self.application/source.name)
        for p in self.application.rglob('*'):
            if p.is_file():p.chmod(0o600)
        self.php=self.runtime/'php';shutil.copyfile(NATIVE,self.php);self.php.chmod(0o700)
        self.lock=self.base/'opkg.lock';self.lock.touch(mode=0o600)
        self.opkg=self.base/'opkg';self.body=self.base/'opkg-body'
        self.body.write_text('#!/bin/sh\nprintf opkg >> '+shlex.quote(str(self.base/'installs'))+'\n'
          'if [ -f '+shlex.quote(str(self.base/'install-fails'))+' ]; then exit 1; fi\n'
          'if [ -f '+shlex.quote(str(self.base/'pending-check'))+' ]; then sleep .4; fi\n'
          'sed "s/+b10/+b11/" '+shlex.quote(str(self.status))+' > '+shlex.quote(str(self.base/'new-status'))+'\n'
          'cat '+shlex.quote(str(self.base/'new-status'))+' > '+shlex.quote(str(self.status))+'\n')
        self.body.chmod(0o700)
        c=self.base/'opkg.c';c.write_text('#include <unistd.h>\n#include <sys/wait.h>\nint main(){int s;int p=fork();if(!p){execl("/bin/sh","sh",'+json.dumps(str(self.body))+',(char*)0);_exit(99);}if(p<0||waitpid(p,&s,0)!=p)return 99;return WIFEXITED(s)?WEXITSTATUS(s):99;}')
        subprocess.run(['gcc',str(c),'-o',str(self.opkg)],check=True,capture_output=True);self.opkg.chmod(0o700)
        subprocess.run(['gcc','-Os','-nostdlib','-static','-fno-builtin','-fno-stack-protector','-fno-pie','-no-pie',
          '-DUPDATE_ROOT="'+str(self.state)+'"','-DOPKG_LOCK="'+str(self.lock)+'"','-DOPKG_BIN="'+str(self.opkg)+'"','-DUPDATE_OWNER='+str(os.getuid()),str(ROOT/'asus/update/opkg-launch.c'),'-o',str(self.runtime/'update-launch')],check=True,capture_output=True)
        (self.runtime/'update-launch').chmod(0o700)
        resources=self.runtime/'resources';resources.mkdir(mode=0o700);(resources/'update-release-key.pem').write_text(self.public)
        shutil.copyfile(ROOT/'updates/package-manifest.schema.json',resources/'package-manifest.schema.json')
        (self.runtime/'lib').mkdir(mode=0o700)
        shutil.copyfile('/lib64/ld-linux-x86-64.so.2',self.runtime/'lib/ld-fixture.so');(self.runtime/'lib/ld-fixture.so').chmod(0o700)
        (self.runtime/'lib/openssl.so').write_bytes(b'')
        manifest={'schema_version':1,'package_version':'1.3.1-asus6+b11','core_version':'1.3.1-asus6','web_version':'0.1.4','build':11,'notes':'Executable fixture','packages':[self.fixture.candidate['package']]}
        raw=json.dumps(manifest,separators=(',',':')).encode();sig=base64.b64encode(subprocess.check_output(['openssl','dgst','-sha256','-sign',str(self.key)],input=raw)).decode();revision=hashlib.sha256(raw).hexdigest()
        for folder in [self.state,self.op]:
            (folder/'manifest.json').write_bytes(raw);(folder/'manifest.sig').write_text(sig)
        self.candidate={**{k:v for k,v in manifest.items() if k not in ['schema_version','packages']},'revision':revision,'package':self.fixture.candidate['package']}
        # Candidate projection uses the production verifier, not a duplicated test schema.
        project='require $argv[1]."/update-manifest.php";$m=AsusPackageManifest::verify(file_get_contents($argv[2]),file_get_contents($argv[3]),file_get_contents($argv[4]));echo json_encode(AsusPackageManifest::candidate($m,"aarch64-3.10","1.3.1-asus6+b10"));'
        self.candidate=json.loads(subprocess.check_output([str(NATIVE),'-n','-r',project,str(PUBLIC),str(self.op/'manifest.json'),str(self.op/'manifest.sig'),str(resources/'update-release-key.pem')]))
        (self.op/'candidate.json').write_text(json.dumps(self.candidate));shutil.copyfile(self.fixture.pkg,self.op/'package.ipk')
        self.env={'opt':str(self.opt),'resources':str(resources),'abi':'aarch64-3.10','machine':'aarch64','owner':os.getuid(),'free':100000000}
        config={'env':self.env,'service':self.service.options,'opkg':str(self.opkg)}
        (self.base/'config.json').write_text(json.dumps(config));(self.base/'config.json').chmod(0o600)
        self.entry=self.runtime/'worker.php';self.entry.write_text('''<?php
        require __DIR__.'/app/update-worker.php';
        $base='''+json.dumps(str(self.base))+''';$c=json_decode(file_get_contents($base.'/config.json'),true);
        $s=new AsusUpdateStore($base.'/state',$c['env']['owner']);
        $source=new class($base) implements AsusUpdateSource{public function __construct(private string $base){} public function manifest():array{file_put_contents($this->base.'/fetches','x',FILE_APPEND);if(is_file($this->base.'/stalled-check'))usleep(3000000);if(is_file($this->base.'/inject-pending')){file_put_contents($this->base.'/opt/lib/opkg/status',"Package: unrelated\\nVersion: 1\\nStatus: install ok unpacked\\n",FILE_APPEND);unlink($this->base.'/inject-pending');}return ['json'=>file_get_contents($this->base.'/state/manifest.json'),'signature'=>file_get_contents($this->base.'/state/manifest.sig')];}public function download(array $p,string $dest):void{throw new RuntimeException('not_expected');}};
        $prepare=new AsusUpdatePrepare($s,$source,$c['env']);
        if(in_array($argv[1],['client-check','client-check-status','guard-check','check'],true)){
            require __DIR__.'/app/update-check.php';$check=new AsusUpdateCheck($s,$prepare,['owner'=>$c['env']['owner'],'busybox'=>'/usr/bin/busybox','entry'=>$base.'/check.sh','channel_probe'=>function()use($base){if(is_file($base.'/missing-channel'))throw new RuntimeException('channel_unconfigured');return true;}]);
            if($argv[1]==='client-check')echo json_encode($check->request(false));
            elseif($argv[1]==='client-check-status'){try{echo json_encode($check->status());}catch(RuntimeException $e){if($e->getMessage()!=='busy')throw $e;echo json_encode(['error'=>'busy']);}}
            elseif($argv[1]==='guard-check')$check->guard($argv[2],[PHP_BINARY,'-n',__FILE__,'check',$argv[2]],1);
            else $check->complete($argv[2]);exit;
        }
        $health=isset($c['health_run'])?['web_run'=>$c['health_run'],'health_port'=>$c['health_port']]:['web_health'=>fn()=>true];
        $worker=new AsusUpdateWorker($s,$prepare,new AsusUpdateLifecycle($c['service']),array_merge(['owner'=>$c['env']['owner'],'opkg'=>$c['opkg']],$health));
        if($argv[1]==='authorize'){exit((new AsusUpdateGuard($s,$c['env']['owner'],$c['opkg']))->authorize($argv[2])?0:1);}
        if($argv[1]==='client-apply'){require __DIR__.'/app/update-dispatch.php';$j=$s->readOperation($argv[2]);echo json_encode((new AsusUpdateDispatch($s,$prepare,['owner'=>$c['env']['owner'],'opkg'=>$c['opkg'],'busybox'=>'/usr/bin/busybox']))->apply($j['id'],$j['revision'],str_repeat('e',32)));exit;}
        if($argv[1]==='guard-apply'){require __DIR__.'/app/update-watchdog.php';(new AsusUpdateWatchdog($s,$c['env']['owner']))->run($argv[2],[PHP_BINARY,'-n',__FILE__,'apply',$argv[2]],AsusUpdateStore::uptime()+10);exit;}
        if($argv[1]==='setup'){$j=$s->reserve('''+json.dumps(revision)+''',str_repeat('b',32),json_decode(file_get_contents($base.'/state/operations/'''+self.id+'''/candidate.json'),true));
            // reserve generated an id; replace it with this protected native fixture id.
            $db=json_decode($s->readFile('operations.json'),true);$j['id']='''+json.dumps(self.id)+''';$j['state']='applying';$j['runtime_digest']=hash_file('sha256',__DIR__.'/closure.json');$db['operations']=[$j['id']=>$j];$s->writeFile('operations.json',json_encode($db));
            AsusUpdateSnapshot::capture($c['env']['opt'],__DIR__.'/../backup',$c['env']['owner']);exit;}
        if($argv[1]==='preflight'){try{$worker->preflight($argv[2]);exit(0);}catch(Throwable $e){$s->writeFile('operations/'.$argv[2].'/preflight-error.json',json_encode(['code'=>AsusUpdatePrepare::code($e)]));exit(1);}}
        if($s->readFile('operations/'.$argv[2].'/guard.json')===null)$s->writeFile('operations/'.$argv[2].'/guard.json',json_encode(['schema'=>1,'guardian'=>AsusUpdateLifecycle::identity(getmypid()),'child'=>AsusUpdateLifecycle::identity(getmypid()),'deadline'=>AsusUpdateStore::uptime()+10]));
        echo json_encode($worker->apply($argv[2]));''')
        (self.runtime/'check.sh').write_text('#!/bin/sh\nexec '+shlex.quote(str(self.php))+' -n '+shlex.quote(str(self.entry))+' preflight "$1"\n');(self.runtime/'check.sh').chmod(0o700)
        (self.runtime/'run.sh').write_text('#!/bin/sh\nexec '+shlex.quote(str(self.php))+' -n '+shlex.quote(str(self.entry))+' guard-apply "$1"\n');(self.runtime/'run.sh').chmod(0o700)
        (self.base/'check.sh').write_text('#!/bin/sh\nexec '+shlex.quote(str(self.php))+' -n '+shlex.quote(str(self.entry))+' guard-check "$1"\n');(self.base/'check.sh').chmod(0o700)
        files={}
        for p in self.runtime.rglob('*'):
            if p.is_file():
                mode=0o700 if p.stat().st_mode&0o111 else 0o600;p.chmod(mode)
                files[p.relative_to(self.runtime).as_posix()]={'mode':mode,'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
        (self.runtime/'closure.json').write_text(json.dumps({'schema':1,'files':dict(sorted(files.items())),'loader':'ld-fixture.so','bytes':sum(x['size'] for x in files.values())}));(self.runtime/'closure.json').chmod(0o600)
        for p in list(self.state.glob('manifest.*'))+list(self.op.glob('*'))+list(resources.iterdir()):
            if p.is_file():p.chmod(0o600)
        self.execute('setup')
    def execute(self,mode='apply'):
        r=subprocess.run([str(self.php),'-n',str(self.entry),mode,self.id],capture_output=True,text=True,timeout=15)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stderr,'')
        pidfile=self.service.run/'pid'
        if pidfile.is_file() and not pidfile.is_symlink():
            pid=int(pidfile.read_text())
            try:start=Path(f'/proc/{pid}/stat').read_text().rsplit(') ',1)[1].split()[19]
            except FileNotFoundError:pass
            else:self.service.identities.append((pid,start))
        return json.loads(r.stdout) if r.stdout else None
    def commands(self):return self.service.log.read_text().splitlines() if self.service.log.exists() else []
    def test_running_stops_before_install_and_restores_once(self):
        self.service.running();r=self.execute();self.assertEqual(r['state'],'succeeded');self.assertEqual(r['core_state'],'running');self.assertEqual(self.commands(),['stop','start'])
    def test_stopped_service_never_starts_even_temporarily(self):
        r=self.execute();self.assertEqual(r['state'],'succeeded');self.assertEqual(r['core_state'],'stopped');self.assertEqual(self.commands(),[])
    def test_waiting_for_wan_is_preserved_without_claiming_running(self):
        (self.service.run/'enabled').touch(mode=0o600);(self.service.base/'no-wan').touch()
        r=self.execute();self.assertEqual(r['state'],'succeeded');self.assertEqual(r['core_state'],'waiting_for_wan');self.assertEqual(self.commands(),['stop','start'])
    def test_busy_opkg_does_not_stop_service(self):
        self.service.running()
        with self.lock.open('r+') as f:
            fcntl.lockf(f,fcntl.LOCK_EX|fcntl.LOCK_NB);r=self.execute()
        self.assertEqual(r['state'],'failed');self.assertEqual(r['code'],'opkg_busy');self.assertEqual(self.commands(),[]);self.assertFalse((self.base/'installs').exists())
    def test_failed_installer_does_not_restart_or_claim_success(self):
        self.service.running();(self.base/'install-fails').touch();r=self.execute()
        self.assertEqual(r['state'],'failed');self.assertEqual(r['code'],'install_failed');self.assertEqual(self.commands(),['stop'])
    def test_changed_snapshot_refuses_before_stop(self):
        self.service.running();(self.opt/'etc/nfqws2/nfqws2.conf').write_text('changed');r=self.execute()
        self.assertEqual(r['state'],'failed');self.assertEqual(r['code'],'settings_changed');self.assertEqual(self.commands(),[]);self.assertFalse((self.base/'installs').exists())
    def test_failed_stop_never_reaches_installer(self):
        self.service.running();(self.service.base/'stop-fails').touch();r=self.execute()
        self.assertEqual(r['state'],'failed');self.assertEqual(r['code'],'core_stop_failed');self.assertEqual(self.commands(),['stop']);self.assertFalse((self.base/'installs').exists())
    def test_own_web_health_uses_its_actual_bind_address(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):self.send_response(200);self.end_headers()
            def log_message(self,*args):pass
        server=http.server.HTTPServer(('127.0.0.2',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(lambda:(server.shutdown(),server.server_close(),thread.join()))
        web_run=self.base/'web-run';web_run.mkdir(mode=0o700)
        (web_run/'lighttpd.conf').write_text('server.bind = "127.0.0.2"\n');(web_run/'lighttpd.conf').chmod(0o600)
        config=json.loads((self.base/'config.json').read_text());config.update(health_run=str(web_run),health_port=server.server_port)
        (self.base/'config.json').write_text(json.dumps(config))
        result=self.execute();self.assertEqual(result['state'],'succeeded',result)
    def install_hooks(self):
        helper=self.opt/'lib/nfqws2-asus/update/lifecycle.sh';helper.parent.mkdir(parents=True)
        helper.write_text('asus_update_transaction() { '+shlex.quote(str(self.php))+' -n '+shlex.quote(str(self.entry))+' authorize "$1"; }\n')
        for name in ['prerm','postinst']:
            text=(ROOT/('asus/ipk/unified-'+name)).read_text()
            text=text.replace('/opt/etc/init.d/S51nfqws2',str(self.service.core)).replace('/opt/etc/init.d/S81nfqws-asus-web',str(self.service.web)).replace('/opt/',str(self.opt)+'/')
            text='asus_migration_restore(){ :; }; asus_install_defaults(){ :; }; asus_migration_complete(){ :; };\n'+text
            (self.base/name).write_text(text)
        original=self.body.read_text();original=original.replace('printf opkg','sh '+shlex.quote(str(self.base/'prerm'))+' || exit $?\nprintf opkg')
        original+='\nsh '+shlex.quote(str(self.base/'postinst'))+'\n'
        self.body.write_text(original)
    def test_verified_hooks_never_duplicate_stop_or_start(self):
        self.install_hooks();self.service.running();result=self.execute()
        self.assertEqual(result['state'],'succeeded',result);self.assertEqual(self.commands(),['stop','start'])
    def test_verified_postinst_keeps_initially_stopped_service_stopped(self):
        self.install_hooks();result=self.execute()
        self.assertEqual(result['state'],'succeeded',result);self.assertEqual(self.commands(),[])
    def test_pending_package_race_is_rechecked_under_native_opkg_mutex(self):
        self.service.running();(self.base/'inject-pending').touch();result=self.execute()
        self.assertEqual(result['state'],'failed',result);self.assertEqual(result['code'],'pending_packages');self.assertEqual(self.commands(),[]);self.assertFalse((self.base/'installs').exists())
    def test_installer_success_without_exact_version_is_failure(self):
        self.body.write_text(self.body.read_text().replace('sed "s/+b10/+b11/"','cat'))
        result=self.execute();self.assertEqual(result['state'],'failed');self.assertEqual(result['code'],'version_mismatch')
    def test_postinst_failure_never_restores_core_or_claims_success(self):
        self.install_hooks();self.service.web.write_text('#!/bin/sh\nexit 9\n');self.service.running()
        result=self.execute();self.assertEqual(result['state'],'failed');self.assertEqual(result['code'],'install_failed');self.assertEqual(self.commands(),['stop'])
    def test_worker_death_keeps_live_installer_protected_then_reports_interrupted(self):
        self.service.running();(self.base/'pending-check').touch()
        p=subprocess.Popen([str(self.php),'-n',str(self.entry),'apply',self.id],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        try:
            end=time.monotonic()+3
            while not (self.base/'installs').exists() and time.monotonic()<end:time.sleep(.005)
            self.assertTrue((self.base/'installs').exists());p.kill();p.wait(timeout=2)
            code='require $argv[1]."/update-guard.php";try{$s=new AsusUpdateStore($argv[2],(int)$argv[3]);$f=(new AsusUpdateGuard($s,(int)$argv[3],$argv[4]))->mutationLease();fclose($f);echo "allowed";}catch(Throwable $e){echo $e->getMessage();}'
            def ordinary():return subprocess.check_output([str(NATIVE),'-n','-r',code,str(PUBLIC),str(self.state),str(os.getuid()),str(self.opkg)],timeout=2).decode()
            self.assertEqual(ordinary(),'busy')
            end=time.monotonic()+3
            while time.monotonic()<end:
                if ordinary()=='allowed':break
                time.sleep(.02)
            else:self.fail('dead worker/installer transaction remained locked')
            job=json.loads((self.state/'operations.json').read_text())['operations'][self.id]
            self.assertEqual(job['state'],'interrupted');self.assertEqual(self.commands(),['stop'])
        finally:
            if p.poll() is None:p.kill();p.wait()
            p.stderr.close()
    def make_ready(self):
        self.assertTrue((PUBLIC/'update-dispatch.php').is_file(),'detached dispatcher missing')
        db=json.loads((self.state/'operations.json').read_text());db['operations'][self.id]['state']='prepared';(self.state/'operations.json').write_text(json.dumps(db))
    def await_finished(self):
        end=time.monotonic()+5
        while time.monotonic()<end:
            job=json.loads((self.state/'operations.json').read_text())['operations'][self.id]
            if job['state'] in ['succeeded','failed','interrupted']:
                pidfile=self.service.run/'pid'
                if pidfile.is_file():
                    pid=int(pidfile.read_text())
                    try:start=Path(f'/proc/{pid}/stat').read_text().rsplit(') ',1)[1].split()[19]
                    except FileNotFoundError:pass
                    else:self.service.identities.append((pid,start))
                return job
            time.sleep(.02)
        self.fail('detached operation did not finish')
    def test_detached_update_finishes_after_the_client_process_exits(self):
        self.make_ready();self.service.running();self.execute('client-apply')
        job=self.await_finished();self.assertEqual(job['state'],'succeeded',job);self.assertEqual(self.commands(),['stop','start'])
    def test_duplicate_apply_does_not_launch_another_installer(self):
        self.make_ready();(self.base/'pending-check').touch();first=self.execute('client-apply');second=self.execute('client-apply')
        self.assertEqual(first['id'],second['id']);self.assertEqual(self.await_finished()['state'],'succeeded');self.assertEqual((self.base/'installs').read_text(),'opkg')
    def await_check(self):
        end=time.monotonic()+5
        while time.monotonic()<end:
            result=self.execute('client-check-status')
            if result.get('error')=='busy':time.sleep(.03);continue
            if result['state']!='checking':return result
            time.sleep(.03)
        self.fail('background metadata check did not finish')
    def test_metadata_check_is_detached_and_cache_reuse_does_not_fetch(self):
        self.assertTrue((PUBLIC/'update-check.php').is_file(),'background metadata checker missing')
        result=self.execute('client-check');self.assertIn(result['state'],['checking','available'])
        self.assertEqual(self.await_check()['state'],'available');self.assertEqual(self.execute('client-check')['state'],'available');self.assertEqual((self.base/'fetches').read_text(),'x')
    def test_missing_private_channel_is_an_explicit_unconfigured_state(self):
        (self.base/'missing-channel').touch();result=self.execute('client-check')
        self.assertEqual(result['state'],'unconfigured');self.assertFalse((self.base/'fetches').exists())

    def test_metadata_guard_registration_survives_short_status_lock_contention(self):
        text=self.entry.read_text();needle="if(in_array($argv[1],['client-check'"
        text=text.replace(needle,"if($argv[1]==='guard-check'){while(!is_file($base.'/release-check-guard'))usleep(10000);}"+needle)
        self.entry.write_text(text);(self.base/'stalled-check').touch();self.execute('client-check')
        with (self.state/'control.lock').open('r+b') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX);(self.base/'release-check-guard').touch();time.sleep(.25)
        result=self.await_check();self.assertEqual(result['state'],'failed');self.assertEqual(result['code'],'timed_out')
    def test_metadata_deadline_is_honest_failure_after_client_exits(self):
        self.assertTrue((PUBLIC/'update-check.php').is_file(),'background metadata checker missing')
        (self.base/'stalled-check').touch();self.execute('client-check');result=self.await_check()
        self.assertEqual(result['state'],'failed');self.assertEqual(result['code'],'timed_out')


if __name__=='__main__':unittest.main()

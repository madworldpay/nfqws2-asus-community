"""Real coordinator -> preparation -> worker -> native mutex -> configure/upgrade.

Only ARM ELF staging is substituted with a sealed host PHP fixture. The same
staged worker, signatures, archives, database, snapshot and launcher run for real.
"""
import base64
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tarfile
import unittest

PROJECT=Path(__file__).resolve().parents[1]/'project'
sys.path.insert(0,str(PROJECT/'tests'))
import test_package_update_apply as executable_fixture


OPKG=PROJECT/'.work/packaging-audit-20261012/opkg-x64'


@unittest.skipUnless(executable_fixture.NATIVE.exists() and OPKG.is_file(),'native PHP and actual Entware opkg fixtures required')
class AsusResumeFlowTests(unittest.TestCase):
    def test_exact_build80_configures_before_latest81_and_preserves_private_settings(self):
        fixture=executable_fixture.PackageUpdateApplyTests('test_resume_stopped_core_never_starts_and_leaves_snapshot_and_log')
        fixture.setUpClass();self.addCleanup(fixture.tearDownClass)
        fixture.setUp();self.addCleanup(fixture.doCleanups)
        base=fixture.base;opt=fixture.opt;owner=os.getuid();php=fixture.php
        feed=base/'feed';feed.mkdir(mode=0o700)
        for build in [80,81]:
            version=f'1.3.1-asus6+b{build}'
            fixture.fixture.package(Version=version)
            if build==80:
                fixture.fixture.add_control_members([('postinst',fixture.fixture.postinst.read_bytes(),tarfile.REGTYPE)])
            fixture.fixture.payload({'opt/lib/nfqws2-asus/helper.sh':(fixture.fixture.immutable.read_bytes(),0o755)})
            package={**fixture.fixture.candidate['package'],'filename':f'nfqws2-asus_{version}_aarch64-3.10.ipk'}
            shutil.copyfile(fixture.fixture.pkg,feed/package['filename'])
            manifest={'schema_version':1,'package_version':version,'core_version':'1.3.1-asus6','web_version':'0.1.4','build':build,'notes':'coordinator fixture','packages':[package]}
            raw=json.dumps(manifest,separators=(',',':')).encode()
            (feed/f'{build}.json').write_bytes(raw)
            (feed/f'{build}.sig').write_bytes(base64.b64encode(subprocess.check_output(['openssl','dgst','-sha256','-sign',str(fixture.key)],input=raw)))
        fixture.status.write_text(fixture.fixture.status().replace('+b10','+b80').replace('Status: install ok installed','Status: install user unpacked',1).replace('Version: 1\nStatus:','Version: 1\nArchitecture: all\nStatus:'))
        # An unpacked real package already has its original control and file
        # inventory. Once configure succeeds, the next update must be able to
        # snapshot that coherent installed baseline without relaxing guards.
        info=opt/'lib/opkg/info';info.mkdir(parents=True,exist_ok=True)
        with tarfile.open(feed/'nfqws2-asus_1.3.1-asus6+b80_aarch64-3.10.ipk') as package:
            with tarfile.open(fileobj=io.BytesIO(package.extractfile('control.tar.gz').read())) as control:
                for member in control:
                    self.assertTrue(member.isfile());name=member.name.removeprefix('./')
                    target=info/('nfqws2-asus.'+name);target.write_bytes(control.extractfile(member).read());target.chmod(member.mode)
            with tarfile.open(fileobj=io.BytesIO(package.extractfile('data.tar.gz').read())) as data:
                installed=['/'+member.name.removeprefix('./') for member in data if member.isfile()]
        (info/'nfqws2-asus.list').write_text('\n'.join(installed)+'\n');(info/'nfqws2-asus.list').chmod(0o644)
        config=base/'actual-opkg.conf';config.write_text('dest root /\narch all 100\narch aarch64-3.10 150\n')
        (opt/'tmp').mkdir(mode=0o755,exist_ok=True)
        actual=shlex.join([str(OPKG),'-f',str(config),'-o',str(base),'--tmp-dir',str(opt/'tmp'),'--force-postinstall'])
        fixture.body.write_text('#!/bin/sh\nprintf "%s|%s\\n" "$*" "$NFQWS_ASUS_NO_START" >> '+shlex.quote(str(base/'arguments'))+'\nexec '+actual+' "$@"\n')
        template=base/'host-template';shutil.copytree(fixture.runtime,template)
        shutil.rmtree(fixture.state);fixture.state.mkdir(mode=0o700);(fixture.state/'operations').mkdir(mode=0o700)
        work=base/'coordinator';work.mkdir(mode=0o700);shutil.copytree(PROJECT/'webui/web/public',work/'app')
        (work/'resources').mkdir(mode=0o700);(work/'resources/update-release-key.pem').write_text(fixture.public)
        shutil.copyfile(PROJECT/'updates/package-manifest.schema.json',work/'resources/package-manifest.schema.json')
        helper=base/'host-boundary.php'
        helper.write_text('''<?php
        final class BootstrapFixtureSource implements AsusUpdateSource {
            public function manifest():array{return $this->read(81,'latest');}
            public function archive(string $v):array{if($v!=='1.3.1-asus6+b80')throw new RuntimeException('recovery_required');return $this->read(80,'archive80');}
            private function read(int $build,string $event):array{file_put_contents('''+json.dumps(str(base/'source-events'))+''',$event."\\n",FILE_APPEND);return ['json'=>file_get_contents('''+json.dumps(str(feed))+'''.'/'.$build.'.json'),'signature'=>file_get_contents('''+json.dumps(str(feed))+'''.'/'.$build.'.sig')];}
            public function download(array $p,string $dest):void{if(!copy('''+json.dumps(str(feed))+'''.'/'.$p['filename'],$dest))throw new RuntimeException('download_failed');chmod($dest,0600);}
        }
        final class BootstrapHostRuntime {
            public static function stage(string $dest,array $config=[]):array{
                $copy=function($from,$to)use(&$copy){if(!mkdir($to,0700))throw new RuntimeException('invalid_state');foreach(scandir($from) as $n){if($n==='.'||$n==='..'||$n==='closure.json')continue;$p=$from.'/'.$n;$q=$to.'/'.$n;if(is_dir($p))$copy($p,$q);else{copy($p,$q);chmod($q,is_executable($p)?0700:0600);}}};
                $copy('''+json.dumps(str(template))+''',$dest);
                foreach(['check.sh'=>'preflight','run.sh'=>'guard-apply'] as $n=>$mode){$command='#!/bin/sh'."\\n".'exec '.escapeshellarg($dest.'/php').' -n '.escapeshellarg($dest.'/worker.php').' '.$mode.' "$1"'.($mode==='preflight'?' "$2"':'')."\\n";file_put_contents($dest.'/'.$n,$command);chmod($dest.'/'.$n,0700);}
                $files=[];$scan=function($p,$prefix='')use(&$scan,&$files){foreach(scandir($p) as $n){if($n==='.'||$n==='..')continue;$q=$p.'/'.$n;$name=$prefix.$n;if(is_dir($q))$scan($q,$name.'/');else $files[$name]=['mode'=>fileperms($q)&0777,'size'=>filesize($q),'sha256'=>hash_file('sha256',$q)];}};$scan($dest);ksort($files);
                file_put_contents($dest.'/closure.json',json_encode(['schema'=>1,'files'=>$files,'loader'=>'ld-fixture.so','bytes'=>array_sum(array_column($files,'size'))]));chmod($dest.'/closure.json',0600);
                return self::load($dest);
            }
            public static function load(string $dest):array{$r=AsusUpdateRuntime::load($dest,'''+str(owner)+''');$r['argv']=[$dest.'/php','-n',$dest.'/worker.php'];return $r;}
        }
        ''')
        entry=(template/'worker.php').read_text()
        a=entry.index('        $source=new class(');b=entry.index('        $prepare=new AsusUpdatePrepare',a)
        entry=entry[:a]+'        require_once '+json.dumps(str(helper))+';\n        if(($argv[1]??null)==="--")array_splice($argv,1,1);\n        $source=new BootstrapFixtureSource();\n        $c["env"]["resources"]=__DIR__."/resources";\n'+entry[b:]
        (template/'worker.php').write_text(entry)
        # Source the exact production coordinator, binding only router locations,
        # ownership and ELF staging to this unprivileged host fixture.
        main=(PROJECT/'asus/install-main.php').read_text()
        main=main.replace("require_once __DIR__.'/app/update-github.php';","require_once __DIR__.'/app/update-github.php';\nrequire_once "+json.dumps(str(helper))+";")
        main=main.replace('new AsusGithubUpdateSource()','new BootstrapFixtureSource()')
        env={**fixture.env,'resources':str(work/'resources')}
        main=main.replace("['resources'=>__DIR__.'/resources']",'json_decode('+json.dumps(json.dumps(env))+',true)')
        main=main.replace('new AsusUpdateStore(__DIR__)','new AsusUpdateStore(__DIR__,'+str(owner)+')')
        main=main.replace('new AsusUpdateStore()','new AsusUpdateStore('+json.dumps(str(fixture.state))+','+str(owner)+')')
        main=main.replace('new AsusUpdateGuard($store)','new AsusUpdateGuard($store,'+str(owner)+','+json.dumps(str(fixture.opkg))+')')
        main=main.replace('AsusUpdateRuntime::','BootstrapHostRuntime::')
        (work/'main.php').write_text(main)
        driver=work/'driver.php';driver.write_text('<?php $nfqwsAsusMode=$argv[1];require __DIR__."/main.php";')
        native=executable_fixture.NATIVE
        def call(mode,success=True):
            result=subprocess.run([str(native),'-n',str(driver),mode],capture_output=True,text=True,timeout=20)
            if success:self.assertEqual(result.returncode,0,result.stdout+result.stderr+'\n'+((work/'coordinator.log').read_text() if (work/'coordinator.log').exists() else ''))
            else:self.assertNotEqual(result.returncode,0);self.assertIn('busy',result.stderr)
        call('prepare')
        call('prepare')  # A disconnected SSH may have left a sealed, unapplied plan.
        staged=json.loads((fixture.state/'operations.json').read_text())['operations']
        self.assertEqual([j['state'] for j in staged.values()],['interrupted','prepared'])
        journal=fixture.state/'operations.json';db=json.loads(journal.read_text());active=list(db['operations'].values())[-1]
        active['state']='preparing';active['prepare_launch_uptime']=float(Path('/proc/uptime').read_text().split()[0]);journal.write_text(json.dumps(db))
        call('prepare',success=False)  # A fresh preparer is never abandoned.
        active['prepare_launch_uptime']-=20;journal.write_text(json.dumps(db))
        with (fixture.state/'operations'/active['id']/'work.lock').open('r+') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            call('prepare',success=False)  # A live worker retains its operation.
        identity=json.loads(subprocess.check_output([str(native),'-n','-r','require $argv[1]."/update-lifecycle.php";echo json_encode(AsusUpdateLifecycle::identity((int)$argv[2]));',str(work/'app'),str(os.getpid())]))
        guard=fixture.state/'operations'/active['id']/'guard.json';guard.write_text(json.dumps({'guardian':identity,'child':None}));guard.chmod(0o600)
        call('prepare',success=False)  # A live guardian also prevents reclamation.
        guard.unlink()
        call('prepare')  # SSH killed the preparer; the old work lease is free.
        self.assertEqual([j['state'] for j in json.loads(journal.read_text())['operations'].values()],['interrupted','interrupted','prepared'])
        self.assertNotIn('latest',(base/'source-events').read_text())
        self.assertFalse((base/'arguments').exists())
        call('run')
        result=json.loads((work/'result.json').read_text())
        self.assertEqual(result['state'],'succeeded');self.assertEqual(result['version'],'1.3.1-asus6+b81')
        arguments=(base/'arguments').read_text().splitlines()
        self.assertEqual(len(arguments),2);self.assertEqual(arguments[0],'configure nfqws2-asus|1')
        self.assertTrue(arguments[1].startswith('--nodeps install '));self.assertTrue(arguments[1].endswith('/package.ipk|1'))
        self.assertEqual((opt/'etc/nfqws2/nfqws2.conf').read_text(),'PRIVATE_CONFIG')
        self.assertEqual((opt/'etc/nfqws-asus-web/auth.json').read_text(),'{"SECRET":"PRIVATE"}')
        jobs=json.loads((fixture.state/'operations.json').read_text())['operations']
        self.assertEqual([j['state'] for j in jobs.values()],['succeeded','succeeded'])
        self.assertEqual([j.get('installed_version') for j in jobs.values()],['1.3.1-asus6+b80','1.3.1-asus6+b81'])
        self.assertIn('Version: 1.3.1-asus6+b81',(info/'nfqws2-asus.control').read_text())
        self.assertEqual((info/'nfqws2-asus.list').read_text().strip(),'/opt/lib/nfqws2-asus/helper.sh')


if __name__=='__main__':unittest.main()

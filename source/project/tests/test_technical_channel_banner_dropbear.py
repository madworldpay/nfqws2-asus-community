"""Real Dropbear/PHP fixture, inside an explicitly supplied disposable network-none container.

The container must be owned by this test run, named nfqws-tech-*, and mount the
checkout at /workspace. Its test-only UID0 account and authorized_keys are replaced.
TECHNICAL_DROPBEAR_CONTAINER=<name> python3 -m unittest discover -s tests -p test_technical_channel_banner_dropbear.py
"""
import importlib.util
import json
import os
from pathlib import Path
import select
import shlex
import subprocess
import tempfile
import time
import unittest
import uuid

CONTAINER = os.environ.get('TECHNICAL_DROPBEAR_CONTAINER')
PROFILE = os.environ.get('TECHNICAL_DROPBEAR_PLATFORM', 'openwrt')
ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(CONTAINER, 'explicit disposable network-none Dropbear container required')
class DropbearMetadataTests(unittest.TestCase):
    @classmethod
    def execute(cls, *args, **kwargs):
        return subprocess.run(['docker', 'exec', '-i', CONTAINER, *args], text=True,
                              capture_output=True, check=True, timeout=10, **kwargs)

    @classmethod
    def setUpClass(cls):
        inspection = json.loads(subprocess.check_output(['docker', 'inspect', CONTAINER], text=True))[0]
        if inspection['HostConfig']['NetworkMode'] != 'none' or not inspection['Name'].startswith('/nfqws-tech-'):
            raise RuntimeError('fixture requires its own nfqws-tech-* container with --network none')
        if PROFILE not in ['openwrt', 'asus-entware']:
            raise RuntimeError('invalid package platform fixture')
        cls.tmp = tempfile.TemporaryDirectory()
        cls.host = Path(cls.tmp.name)
        cls.host.chmod(0o700)
        cls.base = '/tmp/nfqws-banner-test-'+uuid.uuid4().hex
        cls.worker = None
        cls.addClassCleanup(cls.cleanup)
        cls.execute('mkdir', '-m', '700', cls.base)
        cls.execute('php-cli', '-r', '''$app=$argv[1].'/app';mkdir($app,0700);foreach(glob('/workspace/source/project/webui/web/public/*.php') as $file)copy($file,$app.'/'.basename($file));file_put_contents($app.'/platform-profile.json',json_encode(['schema_version'=>1,'platform'=>$argv[2]]));''', cls.base, PROFILE)
        cls.execute('dropbearkey', '-t', 'ed25519', '-f', cls.base+'/hostkey')
        host_public = next(line for line in cls.execute('dropbearkey', '-y', '-f', cls.base+'/hostkey').stdout.splitlines() if line.startswith('ssh-ed25519 '))
        subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(cls.host/'operator')], check=True)
        operator_public = (cls.host/'operator.pub').read_text()
        cls.execute('php-cli', '-r', '''$b=$argv[1];umask(0077);mkdir('/root/.ssh',0700,true);mkdir('/etc/dropbear',0700,true);$key=stream_get_contents(STDIN);file_put_contents('/root/.ssh/authorized_keys',$key);file_put_contents('/etc/dropbear/authorized_keys',$key);file_put_contents('/etc/passwd',preg_replace('/^root:/m','owner_fixture:',file_get_contents('/etc/passwd')));if(is_file('/etc/shadow'))file_put_contents('/etc/shadow',preg_replace('/^root:/m','owner_fixture:',file_get_contents('/etc/shadow')));''', cls.base, input=operator_public)
        # Only fixture paths differ; both banner creation and localServer/guard
        # execution use the actual package's PHP methods.
        php = r'''<?php
require __BASE__.'/app/technical-channel.php';
$b=__BASE__;$cfg=['runtime'=>$b.'/run','journal'=>$b.'/journal.json','owner'=>0,'temporary_parent'=>'/tmp','library'=>$b.'/library','busybox'=>'/bin/busybox'];
$c=new AsusTechnicalChannel($cfg);$id=str_repeat('a',32);
if($argv[1]==='guard')exit($c->command($id));
if($argv[1]==='stop'){$c->stop();exit;}
umask(0077);mkdir($cfg['runtime'],0700);mkdir($cfg['library'],0700);
file_put_contents($cfg['library'].'/guard.sh',"#!/bin/sh\nexec /usr/bin/php-cli ".$b."/driver.php guard\n");chmod($cfg['library'].'/guard.sh',0700);
$bootstrap=proc_open(['/usr/sbin/dropbear','-F','-E','-s','-j','-k','-r',$b.'/hostkey','-P',$b.'/bootstrap.pid','-p','127.0.0.1:45123'],[0=>['file','/dev/null','r'],1=>['file','/dev/null','w'],2=>['file',$b.'/bootstrap.log','a']],$pipes);usleep(150000);
$account=new ReflectionMethod($c,'rootAccount');[$login,$home]=$account->invoke($c);
$s=['state'=>'connecting','stage'=>'local_server','session_id'=>str_repeat('b',32),'activation_id'=>$id,'identity'=>AsusTechnicalProcess::identity(getmypid()),'expires_at'=>time()+180,'uptime_deadline'=>AsusTechnicalProcess::uptime()+180];
$banner=new ReflectionMethod($c,'prepareBanner');$banner->invokeArgs($c,[&$s,$login]);
file_put_contents($cfg['runtime'].'/server.pid','');chmod($cfg['runtime'].'/server.pid',0600);$stamp=lstat($cfg['runtime'].'/server.pid');$s['server_pidfile']=['dev'=>$stamp['dev'],'ino'=>$stamp['ino']];
$server=new ReflectionMethod($c,'localServer');[$p,$port,$args]=$server->invoke($c,$id);usleep(100000);$ps=proc_get_status($p);$s['server_process']=AsusTechnicalProcess::identity($ps['pid']);$s['child_argv']=['server_process'=>$args];
AsusTechnicalFiles::write($cfg['runtime'].'/state.json',json_encode($s),0600);echo json_encode(['port'=>$port,'login'=>$login,'args'=>$args])."\n";flush();
try{while(time()<$s['expires_at']){$now=AsusTechnicalFiles::json($cfg['runtime'].'/state.json');if(!in_array($now['state'],['connecting','connected'],true))break;usleep(100000);}}
finally{$c->stop();proc_close($p);$st=proc_get_status($bootstrap);if($st['running'])proc_terminate($bootstrap,9);proc_close($bootstrap);}
'''.replace('__BASE__', json.dumps(cls.base)).replace('\n', '\n')
        cls.execute('php-cli', '-r', 'file_put_contents($argv[1],stream_get_contents(STDIN));', cls.base+'/driver.php', input=php)
        cls.worker = subprocess.Popen(['docker', 'exec', '-i', CONTAINER, 'php-cli', cls.base+'/driver.php', 'server'],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        ready, _, _ = select.select([cls.worker.stdout], [], [], 5)
        if not ready:
            cls.worker.kill()
            raise RuntimeError('Dropbear PHP fixture did not become ready')
        line = cls.worker.stdout.readline()
        if not line:
            raise RuntimeError(cls.worker.stderr.read())
        cls.record = json.loads(line)
        cls.known = cls.host/'Загрузки known "hosts" \\pin'
        cls.known.write_text('fixture-router '+host_public+'\n')
        cls.session = dict(schema_version=1, purpose='technical_channel', session_id='b'*32,
                           expires_at=int(time.time())+120, remote_port=cls.record['port'])
        (cls.host/'session.json').write_text(json.dumps(cls.session))
        (cls.host/'session.json').chmod(0o600)
        # Bridge stdin/stdout into the isolated namespace; no host TCP listener.
        shim = cls.host/'ssh'
        proxy = shlex.join(['docker', 'exec', '-i', CONTAINER, 'nc', '127.0.0.1', str(cls.record['port'])])
        shim.write_text('#!/bin/sh\nexec /usr/bin/ssh -o '+shlex.quote('ProxyCommand='+proxy)+' "$@"\n')
        shim.chmod(0o700)
        spec = importlib.util.spec_from_file_location('technical_operator_fixture', ROOT/'technical-channel/connect.py')
        cls.operator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.operator)

    @classmethod
    def cleanup(cls):
        try:
            if cls.worker is not None:
                cls.execute('php-cli', cls.base+'/driver.php', 'stop')
                out, err = cls.worker.communicate(timeout=5)
                if cls.worker.returncode:
                    raise RuntimeError(out+err)
                banner = cls.execute('php-cli', '-r', 'echo is_file($argv[1])?"leaked":"removed";', cls.base+'/run/operator-banner.'+'a'*32).stdout
                if banner != 'removed':
                    raise RuntimeError('session banner leaked after stop')
        finally:
            cls.execute('rm', '-rf', cls.base)
            cls.tmp.cleanup()

    def base_argv(self, known=None):
        return self.operator.ssh_base(self.session, known or self.known, 'fixture-router', ssh=str(self.host/'ssh'))

    def test_unknown_account_gets_banner_before_key_authentication(self):
        self.assertEqual(self.record['login'], 'owner_fixture')
        self.assertIn('-b', self.record['args'])
        self.assertEqual(self.operator.discover(self.session, self.base_argv()), 'owner_fixture')

    def test_wrong_host_pin_and_wrong_signed_session_fail_closed(self):
        wrong = self.host/'wrong-known-hosts'
        wrong.write_text('fixture-router '+(self.host/'operator.pub').read_text())
        with self.assertRaises(ValueError):
            self.operator.discover(self.session, self.base_argv(wrong))
        with self.assertRaises(ValueError):
            self.operator.discover(self.session | dict(session_id='c'*32), self.base_argv())

    def test_cli_discovers_custom_uid0_login_and_runs_existing_forced_guard(self):
        env = os.environ | dict(PATH=str(self.host)+os.pathsep+os.environ['PATH'])
        result = subprocess.run(['python3', str(ROOT/'technical-channel/connect.py'), '--session-dir', str(self.host),
                                 '--router-known-hosts', str(self.known), '--router-host-key-alias', 'fixture-router',
                                 '--command', 'printf "uid="; id -u'], text=True, capture_output=True, env=env, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertEqual(result.stdout, 'uid=0\n')


if __name__ == '__main__':
    unittest.main()

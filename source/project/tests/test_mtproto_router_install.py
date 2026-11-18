"""Exercise the router button with the production store and detached worker in a private /opt."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_dpi_normalize import PHP, PUBLIC, ROOT


class RouterInstallTests(unittest.TestCase):
    def test_rejects_untrusted_programs_actions_paths_and_ports(self):
        script = """require $argv[1].'/mtproto-install-api.php';
        $base=['cmd'=>'mtprotoinstall','csrf_token'=>'test','request_id'=>str_repeat('a',32),
               'port'=>'1443','secret'=>'dd'.str_repeat('1',32)];$results=[];
        foreach([[],['port'=>'443'],['port'=>'65536'],['port'=>[]],['secret'=>'bad'],
                 ['request_id'=>'../x'],['program'=>'other'],['method'=>'linux'],['action'=>'remove']] as $change){
          try{AsusMtprotoInstall::validate(array_replace($base,$change));$results[]=true;}
          catch(RuntimeException $e){$results[]=false;}
        }echo json_encode($results);"""
        proc = subprocess.run([PHP, '-n', '-r', script, str(PUBLIC)], check=True, capture_output=True)
        self.assertEqual(json.loads(proc.stdout), [True]+[False]*8)

    @unittest.skipUnless(shutil.which('bwrap') and shutil.which('busybox'), 'requires a private Linux mount and network namespace')
    def test_live_job_reopen_retry_and_telegram_failure_in_isolated_entware(self):
        with tempfile.TemporaryDirectory() as directory:
            opt = Path(directory)
            for rel in ['bin', 'libexec/nfqws2-asus', 'lib/nfqws2-asus/mtproto', 'share', 'etc/init.d']:
                (opt/rel).mkdir(parents=True, exist_ok=True)
            (opt/'bin/php-cgi').symlink_to(Path(PHP).resolve())
            (opt/'bin/opkg').symlink_to('/bin/false')
            (opt/'libexec/nfqws2-asus/busybox').symlink_to(shutil.which('busybox'))
            (opt/'share/nfqws-asus-web').symlink_to(PUBLIC)
            lib = opt/'lib/nfqws2-asus/mtproto'
            shutil.copyfile(ROOT/'asus/mtproto/worker.php', lib/'worker.php')
            # The proxy installer is the only simulated service. Nothing can reach the LAN.
            (lib/'install.sh').write_text('''#!/bin/sh
set -eu
IFS= read -r port
IFS= read -r key
echo invoked >> /opt/invocations
sleep 0.4
if [ "$port" = 1444 ]; then exit 19; fi
umask 077
mkdir /opt/share/nfqws-mtproto
printf '{"port":%s,"secret":"%s"}' "$port" "$key" > /opt/share/nfqws-mtproto/config.json
''')
            (lib/'install.sh').chmod(0o755)
            (opt/'test.php').write_text('''<?php
require '/opt/share/nfqws-asus-web/mtproto-install-api.php';
$api=new AsusMtprotoInstall();$base=['cmd'=>'mtprotoinstall','csrf_token'=>'x',
 'request_id'=>str_repeat('a',32),'secret'=>'dd'.str_repeat('1',32),'port'=>'1444'];
$poll=['cmd'=>'mtprotoinstallstatus','csrf_token'=>'x'];
function finish($api,$poll) {
    for($i=0;$i<100;$i++){usleep(50000);$s=$api->dispatch($poll)['job'];
      if(in_array($s['state'],['completed','failed'],true))return $s;}
    throw new RuntimeException('test timeout');
}
$out=[];$out[]=$api->dispatch($base)['job']['state'];
$out[]=$api->dispatch($base)['job']['id']===$base['request_id'];
try{$api->dispatch(array_replace($base,['request_id'=>str_repeat('c',32)]));$out[]='bad';}
catch(RuntimeException $e){$out[]=$e->getMessage();}
$out[]=finish($api,$poll)['code'];$base['port']='1443';$base['request_id']=str_repeat('b',32);
$api->dispatch($base);$s=finish($api,$poll);$out[]=$s['state'];
$out[]=array_keys($s);$link=['cmd'=>'mtprotoinstalllink','csrf_token'=>'x','request_id'=>$s['id']];
$out[]=$api->dispatch($link)['secret']===$base['secret'];$out[]=$api->dispatch($base)['job']['state'];
$out[]=count(file('/opt/invocations'));echo json_encode($out);
''')
            args = ['bwrap','--unshare-user','--uid','0','--gid','0','--unshare-net','--unshare-pid',
                    '--ro-bind','/','/','--bind',str(opt),'/opt','--proc','/proc','--dev','/dev',
                    '/opt/bin/php-cgi','-n','-f','/opt/test.php']
            run = subprocess.run(args, capture_output=True, text=True, timeout=25)
            if run.returncode and run.stderr.startswith('bwrap:'):
                self.skipTest(run.stderr.strip())
            self.assertEqual(run.returncode, 0, run.stdout+run.stderr)
            self.assertEqual(json.loads(run.stdout), ['queued',True,'busy','telegram_unreachable','completed',
                             ['id','state','code','port'],True,'completed',2])
            self.assertNotIn('"key"',(opt/'var/lib/nfqws2-asus/mtproto-installer/install.json').read_text())

"""Native web stops preserve support only inside a proven package transaction.

Runs inert packages and real /proc ancestry in isolated OpenWrt Docker rootfs;
never opens a router connection or uses host networking.
"""
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
import uuid

from test_openwrt_builder import builder

ROOT = Path(__file__).resolve().parents[1]
CONTAINER = os.environ.get('NFQWS_TEST_DOCKER')
CACHE = os.environ.get('NFQWS_TEST_SMARTDNS_CACHE')


@unittest.skipUnless(CONTAINER and CACHE, 'Requires isolated native PHP CGI and official package tools')
class NativeUpdateChannelContinuity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = json.loads(subprocess.check_output(['docker', 'inspect', CONTAINER]))[0]
        if not CONTAINER.startswith('nfqws-openwrt') or spec['HostConfig']['NetworkMode'] != 'none':
            raise RuntimeError('Refusing a non-isolated test container')
        allowed = {'nfqws-update87-fixture:24', 'nfqws-update87-fixture:25',
                   'nfqws-openwrt88-fixture:24', 'nfqws-openwrt88-fixture:25',
                   'nfqws-openwrt-test:24.10.8', 'nfqws-openwrt-test:25.12.6-php'}
        if spec['Config']['Image'] not in allowed:
            raise RuntimeError('Refusing an unrecognized native test image')

    def sh(self, code, data=None, check=True):
        result = subprocess.run(['docker', 'exec', '-i', CONTAINER, 'sh', '-c', code],
                                input=data, text=True, capture_output=True, timeout=25)
        if check:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def setUp(self):
        self.base = '/tmp/native-channel-' + uuid.uuid4().hex
        self.format = 'apk' if self.sh('test -x /usr/bin/apk; echo $?').strip() == '0' else 'ipk'
        self.sh('test ! -e /tmp/nfqws2-native-package; test ! -e /usr/lib/nfqws2/update/quiesce.php')
        self.sh('umask 077; mkdir -p ' + self.base + '/source/app ' + self.base + '/source/resources')
        self.addCleanup(lambda: self.sh('rm -rf ' + self.base, check=False))
        self.sh('cp ' + shlex.quote(str(ROOT / 'webui/web/public')) + '/*.php ' + self.base + '/source/app/; chmod 644 ' + self.base + '/source/app/*.php')
        self.sh('printf %s ' + shlex.quote('{"schema_version":1,"platform":"openwrt"}') + ' > ' + self.base + '/source/app/platform-profile.json')
        for source, target in [('openwrt-package-manifest.schema.json', 'openwrt-package-manifest.schema.json'), ('trusted-release-key.pem', 'update-release-key.pem')]:
            self.sh('cp ' + shlex.quote(str(ROOT / 'updates' / source)) + ' ' + self.base + '/source/resources/' + target)
        guard = (ROOT / 'openwrt/update/service-guard.php').read_text().replace('/usr/share/nfqws2-web', self.base + '/source/app').replace('new AsusUpdateStore()', 'new AsusUpdateStore(' + json.dumps(self.base + '/store') + ')')
        self.sh('cat > ' + self.base + '/service-guard.php', guard)
        init = (ROOT / 'openwrt/nfqws2-web.init').read_text().replace('/usr/lib/nfqws2/update/service-guard.php', self.base + '/service-guard.php')
        self.sh('cat > ' + self.base + '/web.init', init)
        stop = f'''#!/bin/sh
action=''
. {self.base}/web.init || exit 1
# The real native init callback and guard run unchanged; only the independent
# channel process is an inert fixture. Any recover/start call is also recorded.
nfqws_web_technical_channel() {{
    printf '%s\\n' "$1" >> {self.base}/channel-calls
    [ "$1" != stop ] || kill "$(cat {self.base}/channel.pid)"
}}
action=${{1:-stop}}
case "$action" in stop|restart|shutdown) stop_service;; *) exit 2;; esac
'''
        self.sh('cat > ' + self.base + '/stop.sh', stop)
        self.sh('chmod 700 ' + self.base + '/stop.sh; sleep 120 >/dev/null 2>&1 & echo $! > ' + self.base + '/channel.pid')
        self.addCleanup(lambda: self.sh('kill "$(cat ' + self.base + '/channel.pid)" 2>/dev/null || :', check=False))
        self.receipt = '{"id":"existing-session","expires_at":123456789,"reconnects":0}\n'
        self.sh('cat > ' + self.base + '/session.json', self.receipt)

    def alive(self):
        # BusyBox kill -0 also recognizes zombies; /proc state is authoritative.
        return self.sh('state=$(awk \'{print $3}\' /proc/$(cat ' + self.base + '/channel.pid)/stat 2>/dev/null); case "$state" in \'\'|Z|X) echo no;; *) echo yes;; esac').strip() == 'yes'

    def package(self, hook):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); stage = root / 'payload'; out = root / 'out'; out.mkdir()
            builder.write_files(stage, {'usr/share/nfqws2/channel-fixture': (b'inert\n', 0o644)})
            if self.format == 'ipk':
                metadata = b'Package: nfqws2-native\nVersion: 1.3.2-87\nArchitecture: x86_64\nDescription: Inert channel continuity fixture\n'
                builder.write_files(stage, {'CONTROL/control': (metadata, 0o644), 'CONTROL/preinst': (hook.encode(), 0o755)})
                tool = builder.pinned_asset(builder.ASSETS['ipkg_build'], CACHE, True)
                subprocess.run(['fakeroot', 'sh', str(tool), str(stage), str(out)], check=True, capture_output=True)
                package = next(out.glob('*.ipk'))
            else:
                key = root / 'key.pem'; public = root / 'public.pem'
                subprocess.run(['openssl', 'genpkey', '-algorithm', 'RSA', '-pkeyopt', 'rsa_keygen_bits:3072', '-out', str(key)], check=True, capture_output=True); key.chmod(0o600)
                subprocess.run(['openssl', 'pkey', '-in', str(key), '-pubout', '-out', str(public)], check=True, capture_output=True)
                target = builder.native_metadata('25.12', 'x86_64', 87); target['dependencies'] = []
                hooks = {name: b'#!/bin/sh\nexit 0\n' for name in ['preinst', 'postinst', 'prerm', 'postrm']}; hooks['preinst'] = hook.encode()
                package = builder.build_apk(target, stage, hooks, CACHE, out, True, key)
                self.sh('mkdir -m 700 ' + self.base + '/keys; cat > ' + self.base + '/keys/fixture.pem', public.read_text())
            subprocess.run(['docker', 'cp', str(package), CONTAINER + ':' + self.base + '/package.' + self.format], check=True, capture_output=True)
        self.addCleanup(lambda: self.sh(('opkg remove' if self.format == 'ipk' else 'apk del --network=no') + ' nfqws2-native >/dev/null 2>&1 || :', check=False))

    def manager_args(self):
        return ['/bin/opkg', '--nodeps', 'install', self.base + '/package.ipk'] if self.format == 'ipk' else ['/usr/bin/apk', 'add', '--network=no', '--cache=no', '--repositories-file', '/dev/null', '--keys-dir', self.base + '/keys', self.base + '/package.apk']

    def staged_manager(self, case):
        self.package('#!/bin/sh\nwhile [ ! -f ' + self.base + '/go ]; do sleep 0.05; done\n' + self.base + '/stop.sh\n')
        worker = r'''<?php
require __DIR__.'/app/openwrt-update-guard.php';
$s=new AsusUpdateStore(dirname(__DIR__,3));$id=basename(dirname(__DIR__));$base=dirname(__DIR__,4);$format=trim(file_get_contents($base.'/format'));
$worker=AsusUpdateLifecycle::identity(getmypid());$lease=$s->lease('apply.lock');
$t=['schema'=>1,'id'=>$id,'boot_id'=>AsusUpdateStore::boot(),'worker'=>$worker,'manager'=>null,'phase'=>'installing','format'=>$format,'intent'=>['mode'=>'stopped']];
$s->writeFile('native-transaction.json',json_encode($t));$s->update($id,['identity'=>$worker]);
$args=json_decode(file_get_contents($base.'/manager-args.json'),true);$p=proc_open($args,[0=>['file','/dev/null','r'],1=>['file',$base.'/manager.log','a'],2=>['file',$base.'/manager.log','a']],$pipes,'/',['PATH'=>'/usr/sbin:/usr/bin:/sbin:/bin','NFQWS_UPDATE_PRESERVE_CHANNEL'=>'1']);
$status=proc_get_status($p);$end=microtime(true)+2;
do{$manager=AsusUpdateLifecycle::identity($status['pid']);if(($manager['exe']??null)===realpath($format==='ipk'?'/bin/opkg':'/usr/bin/apk'))break;usleep(1000);}while(microtime(true)<$end);
if(($manager['exe']??null)!==realpath($format==='ipk'?'/bin/opkg':'/usr/bin/apk'))throw new RuntimeException('manager proof missing');
$t['manager']=$manager;if(trim(file_get_contents($base.'/case'))==='stale')$t['manager']['start_ticks']='1';
$s->writeFile('native-transaction.json',json_encode($t));
if(trim(file_get_contents($base.'/case'))==='tampered')file_put_contents(__DIR__.'/app/platform.php',"\n// changed",FILE_APPEND);
file_put_contents($base.'/go','go');$exit=proc_close($p);if($exit!==0)throw new RuntimeException(file_get_contents($base.'/manager.log'));
'''
        self.sh('cat > ' + self.base + '/source/worker.php', worker)
        for filename, value in [('case', case), ('format', self.format), ('manager-args.json', json.dumps(self.manager_args()))]:
            self.sh('cat > ' + self.base + '/' + filename, value)
        setup = '''require $argv[1]."/openwrt-update-guard.php";$s=new AsusUpdateStore($argv[2]."/store");$revision=str_repeat("a",64);$j=$s->reserve($revision,str_repeat("b",32),["revision"=>$revision,"package_version"=>"1.3.2-87"]);$r=NfqwsOpenWrtUpdateRuntime::stage($s->path("operations/".$j["id"]."/runtime"),["application"=>$argv[1],"resources"=>$argv[2]."/source/resources","entry"=>$argv[2]."/source/worker.php"]);$s->update($j["id"],["state"=>"prepared","runtime_digest"=>$r["digest"]]);$s->claimApply($j["id"],$revision,str_repeat("c",32));echo $j["id"];'''
        operation = self.sh('php-cli -r ' + shlex.quote(setup) + ' ' + self.base + '/source/app ' + self.base)
        self.sh(self.base + '/store/operations/' + operation + '/runtime/run.sh apply ' + operation)

    def test_sealed_native_manager_keeps_existing_channel_without_renewing_session(self):
        self.staged_manager('genuine')
        self.assertTrue(self.alive(), 'genuine native updater revoked the independent channel')
        self.sh('test ! -e ' + self.base + '/channel-calls')
        self.assertEqual(self.sh('cat ' + self.base + '/session.json'), self.receipt)
        # Once the manager/worker leave, the old ticket must not preserve it.
        self.sh(self.base + '/stop.sh')
        self.assertFalse(self.alive())
        self.assertEqual(self.sh('cat ' + self.base + '/channel-calls'), 'stop\n')

    def test_modified_runtime_cannot_preserve_channel(self):
        self.staged_manager('tampered')
        self.assertFalse(self.alive(), 'an unsealed worker must not preserve support')
        self.assertEqual(self.sh('cat ' + self.base + '/channel-calls'), 'stop\n')

    def test_stale_manager_identity_cannot_preserve_channel(self):
        self.staged_manager('stale')
        self.assertFalse(self.alive(), 'a stale PID/start tuple must not preserve support')
        self.assertEqual(self.sh('cat ' + self.base + '/channel-calls'), 'stop\n')

    def test_ordinary_stop_restart_and_shutdown_revoke_despite_env_and_inherited_fds(self):
        for action in ['stop', 'restart', 'shutdown']:
            with self.subTest(action=action):
                if not self.alive():
                    self.sh('sleep 120 >/dev/null 2>&1 & echo $! > ' + self.base + '/channel.pid')
                self.sh('NFQWS_UPDATE_PRESERVE_CHANNEL=1; export NFQWS_UPDATE_PRESERVE_CHANNEL; exec 8>/dev/null; exec 9>/dev/null; ' + self.base + '/stop.sh ' + action)
                self.assertFalse(self.alive(), action + ' did not revoke the channel')
        self.assertEqual(self.sh('cat ' + self.base + '/channel-calls'), 'stop\nstop\nstop\n')

    def test_verified_manual_manager_controller_preserves_but_manager_alone_revokes(self):
        controller = '/usr/lib/nfqws2/update/quiesce.php'
        self.sh('mkdir -p /usr/lib/nfqws2/update; chmod 755 /usr/lib/nfqws2/update')
        self.addCleanup(lambda: self.sh('rm -f ' + controller + '; rm -rf /tmp/nfqws2-native-package', check=False))
        code = '<?php require ' + json.dumps(self.base + '/source/app/openwrt-update-guard.php') + ';$s=new AsusUpdateStore(' + json.dumps(self.base + '/store') + ');$lease=$s->lease("apply.lock");$p=proc_open([' + json.dumps(self.base + '/stop.sh') + '],[0=>["file","/dev/null","r"],1=>["file","/dev/null","w"],2=>["file","/dev/null","w"]],$pipes);exit(proc_close($p));'
        self.sh('cat > ' + controller, code); self.sh('chmod 644 ' + controller)
        library = (ROOT / 'openwrt/package-lifecycle.sh').read_text().split('case "$NFQWS_PKG_ACTION" in')[0]
        hook = '#!/bin/sh\numask 077\n' + library + '\nNFQWS_PKG_FORMAT=' + self.format + '\nnfqws_package_snapshot || exit 1\n/usr/bin/php8-cgi -d register_argc_argv=1 -q -f ' + controller + ' -- upgrade || exit 1\n'
        hook += 'state=$(awk \'{print $3}\' /proc/$(cat ' + self.base + '/channel.pid)/stat 2>/dev/null); case "$state" in \'\'|Z|X) echo revoked > ' + self.base + '/inside;; *) echo preserved > ' + self.base + '/inside;; esac\n'
        hook += self.base + '/stop.sh\n'
        self.package(hook)
        self.sh(shlex.join(self.manager_args()))
        self.assertEqual(self.sh('cat ' + self.base + '/inside'), 'preserved\n', 'verified native manual context revoked support')
        self.assertFalse(self.alive(), 'manager ancestry alone cannot preserve support')
        self.assertEqual(self.sh('cat ' + self.base + '/channel-calls'), 'stop\n')
        self.assertEqual(self.sh('cat ' + self.base + '/session.json'), self.receipt)


if __name__ == '__main__':
    unittest.main()

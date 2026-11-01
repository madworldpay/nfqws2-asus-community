"""Native sidecar ownership/scoping at shell and nft boundaries; no router access."""
import importlib.util
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/'openwrt/ip-health-runtime.sh'
spec=importlib.util.spec_from_file_location('ip_health_native_builder',ROOT/'openwrt/build.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)


class IpHealthNativeTests(unittest.TestCase):
    def shell(self,body,**env):
        self.assertTrue(RUNTIME.exists(),'native IP Health runtime missing')
        return subprocess.run(shlex.split(os.environ.get('TEST_SHELL','sh'))+['-c','set -f\n. '+shlex.quote(str(ROOT/'openwrt/firewall.sh'))+'\n. '+shlex.quote(str(RUNTIME))+'\n'+body],env={**os.environ,**env},capture_output=True,text=True,timeout=5)

    def config(self,extra=''):
        return '''NFQUEUE_NUM=300; TCP_PORTS=80,443; UDP_PORTS=443; IPV6_ENABLED=1
ASUS_CLIENT_MODE=all; ASUS_CLIENTS4=''; ASUS_CLIENTS6=''; NFQWS_WAN=eth0; NFQWS_HEALTH_QUEUE=301
'''+extra+'\n'

    def test_native_payload_has_portable_worker_and_no_entware_or_boot_intent(self):
        method=getattr(builder,'ip_health_payload',None);self.assertTrue(callable(method),'native payload missing')
        files=method()
        for name in ['runtime.sh','service.sh','worker.php','dns.lua','monitor.lua']:
            self.assertIn('usr/lib/nfqws2/ip-health/'+name,files)
        worker=files['usr/lib/nfqws2/ip-health/worker.php'][0].decode()
        self.assertNotIn('/opt/',worker);self.assertNotIn('nfqws2-asus',worker)
        self.assertIn('/usr/share/nfqws2-web/ip-health-runtime.php',worker)
        self.assertIn("'/usr/bin/nfqws2'",worker)
        self.assertIn("realpath('/var/run/nfqws2-native')",worker)
        self.assertIn('new NfqwsIpHealthStore(null,$public)',worker)
        self.assertFalse(any(name.startswith('etc/')or name.endswith('bans.json')for name in files))
        for name,(data,mode)in files.items():self.assertEqual(mode,0o755 if name.endswith('/service.sh')else 0o644)

    def test_rules_are_separate_bypass_marked_scoped_and_ipv6_disabled(self):
        p=self.shell(self.config("ASUS_CLIENT_MODE=include; ASUS_CLIENTS4='192.168.1.3'; IPV6_ENABLED=0")+'nfqws_health_rules')
        self.assertEqual(p.returncode,0,p.stderr)
        for text in ['create table inet nfqws2_health','NFQWS2 IP Health v1','priority mangle + 1','queue num 301 bypass','0x40000000','ct original ip saddr != @clients4 return','ip daddr != @clients4 return','meta nfproto ipv6 return','udp sport 53']:
            self.assertIn(text,p.stdout)
        self.assertNotIn('queue num 300',p.stdout);self.assertNotIn('fw4',p.stdout);self.assertNotIn('flush ruleset',p.stdout)
        p=self.shell(self.config("ASUS_CLIENT_MODE=exclude; ASUS_CLIENTS4='192.168.1.3'")+'nfqws_health_rules')
        self.assertIn('ct original ip saddr @clients4 return',p.stdout);self.assertIn('ip daddr @clients4 return',p.stdout)

    def test_dns_is_queued_in_forward_output_never_router_prerouting_reply(self):
        p=self.shell(self.config()+'nfqws_health_rules');self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn('chain forward {',p.stdout)
        forward=p.stdout.split(' chain forward {',1)[1].split(' }',1)[0]
        self.assertIn('iifname != \"eth0\" return',forward)
        self.assertIn('ct direction != reply return',forward)
        reply=p.stdout.split(' chain reply {',1)[1].split(' }',1)[0]
        self.assertNotIn('udp sport 53',reply)
        self.assertEqual(p.stdout.count('udp sport 53 counter queue'),2)

    def test_invalid_rules_emit_nothing(self):
        for extra in ["NFQWS_WAN='eth0 eth1'","NFQWS_WAN='wan;reboot'",'NFQUEUE_NUM=65535','NFQWS_HEALTH_QUEUE=300',"ASUS_CLIENT_MODE=exclude; ASUS_CLIENTS4='1.2.3.4;reboot'"]:
            with self.subTest(extra=extra):
                p=self.shell(self.config(extra)+'nfqws_health_rules');self.assertNotEqual(p.returncode,0);self.assertEqual(p.stdout,'')

    def test_foreign_table_never_deleted_and_failed_check_never_applied(self):
        for foreign in [True,False]:
            with self.subTest(foreign=foreign),tempfile.TemporaryDirectory()as folder:
                body=self.config()+'''NFQWS_HEALTH_PRIVATE="$TEST_ROOT"
nft() { printf '%s\n' "$*" >> "$TEST_ROOT/calls"; case "$*" in
'list table inet nfqws2_health') '''+('echo foreign; return 0'if foreign else'return 1')+''';;
'-c -f '*) return 1;; esac; }
nfqws_health_firewall_apply
'''
                p=self.shell(body,TEST_ROOT=folder);self.assertNotEqual(p.returncode,0)
                calls=(Path(folder)/'calls').read_text();self.assertNotIn('delete table',calls)
                self.assertFalse(any(line.startswith('-f ')for line in calls.splitlines()))

    def test_missing_capability_does_not_launch_or_touch_main_service(self):
        with tempfile.TemporaryDirectory()as folder:
            body=self.config()+'''NFQWS_HEALTH_PRIVATE="$TEST_ROOT/private"; NFQWS_HEALTH_PUBLIC="$TEST_ROOT/public"
NFQWS_RUN="$TEST_ROOT"; NFQWS_BIN=/usr/bin/nfqws2; USER=nobody
nfqws_health_directory() { mkdir -p "$1"; }
nfqws_process_pid() { echo 41; }
nfqws_uplinks() { echo eth0; }
nfqws_health_php() { printf '%s\n' "$*" >> "$TEST_ROOT/calls"; case "$1" in available) return 1;; esac; }
nfqws_health_stop() { echo optional-stop >> "$TEST_ROOT/calls"; }
nfqws_queue_facts() { echo 'unbound null null'; }
ip() { echo 'eth0 inet 93.184.216.34'; }
nfqws_health_start
'''
            p=self.shell(body,TEST_ROOT=folder);self.assertEqual(p.returncode,0,p.stderr)
            calls=(Path(folder)/'calls').read_text();self.assertIn('available eth0',calls)
            self.assertNotIn('prepare ',calls);self.assertNotIn('loop',calls);self.assertFalse((Path(folder)/'bans.json').exists())

    def test_stopped_core_foreign_queue_and_multiwan_are_inert(self):
        for case,reason in [('stopped',None),('foreign','queue_in_use'),('multiwan','multiwan_unsupported')]:
            with self.subTest(case=case),tempfile.TemporaryDirectory()as folder:
                body=self.config()+'''NFQWS_HEALTH_PRIVATE="$TEST_ROOT/private"; NFQWS_HEALTH_PUBLIC="$TEST_ROOT/public"
ISP_INTERFACE=eth0
nfqws_health_directory() { mkdir -p "$1"; }
nfqws_process_pid() { [ "$CASE" != stopped ] || return 1; echo 41; }
nfqws_uplinks() { if [ "$CASE" = multiwan ] && [ -z "$ISP_INTERFACE" ]; then echo 'eth0 eth1'; else echo eth0; fi; }
nfqws_health_stop() { :; }
nfqws_health_php() { printf '%s\n' "$*" >> "$TEST_ROOT/calls"; }
nfqws_queue_facts() { echo 'bound 123 999'; }
nfqws_health_start
'''
                p=self.shell(body,TEST_ROOT=folder,CASE=case);self.assertEqual(p.returncode,0,p.stderr)
                calls=(Path(folder)/'calls').read_text()if(Path(folder)/'calls').exists()else''
                if reason:self.assertIn('inactive '+reason,calls)
                else:self.assertFalse((Path(folder)/'private').exists())
                self.assertNotIn('available',calls);self.assertNotIn('prepare ',calls);self.assertNotIn('loop',calls)

    def test_foreground_supervisor_releases_startup_lease_before_worker_loop(self):
        with tempfile.TemporaryDirectory()as folder:
            root=Path(folder);engine=root/'engine'
            engine.write_text('#!/bin/sh\nfor arg in "$@"; do case "$arg" in --pidfile=*) printf "42\\n" > "${arg#--pidfile=}";; esac; done\n');engine.chmod(0o755)
            (root/'config.env').write_text('NFQUEUE_NUM=300\n')
            body=self.config()+'''NFQWS_HEALTH_PRIVATE="$TEST_ROOT/private"; NFQWS_HEALTH_PUBLIC="$TEST_ROOT/public"
NFQWS_RUN="$TEST_ROOT"; NFQWS_BIN="$TEST_ROOT/engine"; USER=$(id -un)
nfqws_health_directory() { mkdir -p "$1"; }
nfqws_process_pid() { echo 41; }
nfqws_uplinks() { echo eth0; }
nfqws_health_stop() { echo stop >> "$TEST_ROOT/stops"; }
nfqws_health_firewall_apply() { :; }
nfqws_queue_facts() { echo 'unbound null null'; }
ip() { echo 'eth0 inet 93.184.216.34'; }
nfqws_health_php() {
 case "$1" in loop) touch "$TEST_ROOT/loop-entered"; flock -x -n "$TEST_ROOT/apply.lock" true;; *) return 0;; esac
}
exec 8>"$TEST_ROOT/apply.lock"; flock -s 8
nfqws_health_start
'''
            p=self.shell(body,TEST_ROOT=folder);self.assertTrue((root/'loop-entered').exists())
            self.assertEqual(p.returncode,0,'foreground procd shell must not retain its startup shared update lease')
            self.assertEqual((root/'stops').read_text().splitlines(),['stop','stop'],'worker exit must detach the observer and table even without a main-service stop')

    def test_procd_optional_instance_has_no_independent_respawn_or_start_intent(self):
        with tempfile.TemporaryDirectory()as folder:
            root=Path(folder);control=root/'control';control.write_text('#!/bin/sh\nexit 0\n');control.chmod(0o755)
            (root/'launch.env').write_text("NFQWS_LAUNCH_ARGS='--user=nobody --qnum=300'\n")
            source=(ROOT/'openwrt/nfqws2.init').read_text().replace('[ -x /usr/lib/nfqws2/ip-health/service.sh ]','true')
            init=root/'init';init.write_text(source)
            p=subprocess.run(['sh','-c','''action=''; NFQWS_CONTROL="$CONTROL"; NFQWS_RUN="$RUN"; . "$INIT"
procd_open_instance() { printf 'instance %s\n' "$*"; }
procd_set_param() { printf '%s\n' "$*"; }
procd_close_instance() { :; }
start_service
'''],env={**os.environ,'CONTROL':str(control),'RUN':folder,'INIT':str(init)},capture_output=True,text=True,timeout=3)
            self.assertEqual(p.returncode,0,p.stderr);self.assertIn('instance iphealth',p.stdout)
            self.assertIn('command /usr/lib/nfqws2/ip-health/service.sh',p.stdout)
            self.assertNotIn('respawn',p.stdout)


@unittest.skipUnless(os.environ.get('NFQWS_TEST_DOCKER'),'isolated native nft test container not selected')
class IpHealthNativeNftTests(unittest.TestCase):
    def test_real_nft_owned_transaction_and_foreign_collision_preserve_fw4(self):
        import json
        container=os.environ['NFQWS_TEST_DOCKER'];meta=json.loads(subprocess.check_output(['docker','inspect',container]))[0]
        self.assertTrue(container.startswith('nfqws-openwrt')and meta['HostConfig']['NetworkMode']!='host')
        source=(ROOT/'openwrt/firewall.sh').read_text()+'\n'+RUNTIME.read_text()+'''
set -e
if nft list table inet nfqws2_health >/dev/null 2>&1; then echo table_in_use >&2; exit 99; fi
NFQUEUE_NUM=300; TCP_PORTS=80,443; UDP_PORTS=443; IPV6_ENABLED=0
ASUS_CLIENT_MODE=include; ASUS_CLIENTS4='192.168.1.3'; ASUS_CLIENTS6=''; NFQWS_WAN=eth0; NFQWS_HEALTH_QUEUE=301
NFQWS_HEALTH_PRIVATE=$(mktemp -d /tmp/ip-health-nft.XXXXXX)
trap 'nft delete table inet nfqws2_health 2>/dev/null || :; rm -rf "$NFQWS_HEALTH_PRIVATE"' EXIT
nft -j list table inet fw4 > "$NFQWS_HEALTH_PRIVATE/fw4-before"
nfqws_health_firewall_apply
nft -j list table inet nfqws2_health > "$NFQWS_HEALTH_PRIVATE/health"
nfqws_health_firewall_stop
! nft list table inet nfqws2_health >/dev/null 2>&1
nft 'create table inet nfqws2_health { comment "operator-owned fixture"; }'
! nfqws_health_firewall_apply
! nfqws_health_firewall_stop
nft list table inet nfqws2_health | grep -F 'operator-owned fixture' >/dev/null
nft -j list table inet fw4 > "$NFQWS_HEALTH_PRIVATE/fw4-after"
cmp "$NFQWS_HEALTH_PRIVATE/fw4-before" "$NFQWS_HEALTH_PRIVATE/fw4-after"
cat "$NFQWS_HEALTH_PRIVATE/health"
'''
        p=subprocess.run(['docker','exec','-i',container,'sh'],input=source,text=True,capture_output=True,timeout=10)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        rules=json.loads(p.stdout)['nftables'];chains=[r['chain']for r in rules if'chain'in r]
        self.assertEqual({r['prio']for r in chains if'hook'in r},{-149})
        queue=[]
        for item in rules:
            for expr in item.get('rule',{}).get('expr',[]):
                if'queue'in expr:queue.append(expr['queue'])
        self.assertTrue(queue);self.assertTrue(all(q['num']==301 and 'bypass'in q['flags']for q in queue))

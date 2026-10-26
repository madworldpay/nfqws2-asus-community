"""Package hooks share state only within one live manager transaction."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

LIB=Path(__file__).resolve().parents[1]/'openwrt/package-lifecycle.sh'


class NativePackageLifecycleTests(unittest.TestCase):
    def postinstall_calls(self,mode):
        with tempfile.TemporaryDirectory()as td:
            root=Path(td);init=root/'init';init.mkdir();state=root/'state';state.mkdir()
            (state/'state').write_text('manager=boot:123:456\nenabled=1\nrunning=1\nweb_present=1\nweb_enabled=1\nweb_running=1\n')
            for name in ['nfqws2-native','nfqws2-native-web','nfqws2-native-dns','nfqws2-native-dns-resume']:
                path=init/name;path.write_text('#!/bin/sh\nprintf "%s:%s\\n" '+name+' "$1"\n');path.chmod(0o755)
            source=LIB.read_text().split('case "$NFQWS_PKG_ACTION" in')[0].replace('/etc/init.d/',str(init)+'/')
            body=source+"""
nfqws_package_state_dir="$TEST_STATE"
nfqws_package_defaults() { return 0; }
nfqws_package_guard() { return 0; }
nfqws_package_manager() { echo boot:123:456; }
nfqws_package_native_update() { [ "$1" = postinstall ] || return 0; return "$TEST_MODE"; }
nfqws_package_service() { printf '%s:%s\n' "$1" "$2"; }
uci() { case "$*" in '-q get firewall.nfqws2_native.path') echo /usr/lib/nfqws2/firewall-hook.sh;; '-q get firewall.nfqws2_native') echo include;; *) return 1;; esac; }
nfqws_package_postinstall
rc=$?
[ ! -f "$TEST_STATE/state" ] || echo journal-retained
exit "$rc"
"""
            return subprocess.run(['sh','-c',body],env={**os.environ,'TEST_STATE':str(state),'TEST_MODE':str(mode)},capture_output=True,text=True)

    def test_controlled_postinstall_defers_all_starts_and_keeps_original_intent(self):
        r=self.postinstall_calls(0);self.assertEqual(r.returncode,0,r.stderr)
        self.assertFalse(any(line.endswith(':start')for line in r.stdout.splitlines()),r.stdout)
        self.assertIn('nfqws2-native:enable',r.stdout);self.assertIn('journal-retained',r.stdout)

    def test_manual_postinstall_restores_services_and_cleans_transaction_journal(self):
        r=self.postinstall_calls(10);self.assertEqual(r.returncode,0,r.stderr)
        for name in ['nfqws2-native','nfqws2-native-web','nfqws2-native-dns-resume']:self.assertIn(name+':start',r.stdout)
        self.assertNotIn('journal-retained',r.stdout)

    def test_failed_controlled_postinstall_proof_cannot_start_any_service(self):
        r=self.postinstall_calls(1);self.assertNotEqual(r.returncode,0)
        self.assertFalse(any(line.endswith(':start')for line in r.stdout.splitlines()),r.stdout)
        self.assertIn('journal-retained',r.stdout)

    def test_foreign_service_is_rejected_before_any_dns_or_service_change(self):
        source=LIB.read_text().split('case "$NFQWS_PKG_ACTION" in')[0]
        r=subprocess.run(['sh','-c',source+'''
nfqws_package_service_owner() { [ "$1" != nfqws2-native-web ]; }
nfqws_package_dns_control() { echo unexpected-dns-change; }
nfqws_package_service() { echo unexpected-service-change; }
nfqws_package_stop_services upgrade
'''],capture_output=True,text=True)
        self.assertNotEqual(r.returncode,0)
        self.assertEqual(r.stdout,'')

    def test_dns_is_restored_before_core_or_web_can_stop(self):
        source=LIB.read_text().split('case "$NFQWS_PKG_ACTION" in')[0]
        r=subprocess.run(['sh','-c',source+'''
nfqws_package_dns_control() { printf 'dns-control-%s\\n' "$1"; }
nfqws_package_service() { printf '%s-%s\\n' "$1" "$2"; }
nfqws_package_stop_services upgrade
'''],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(r.stdout.splitlines(),['dns-control-upgrade','nfqws2-native-dns-stop','nfqws2-native-dns-resume-stop','nfqws2-native-stop','nfqws2-native-web-stop'])

    def test_failed_dns_restoration_cannot_replace_live_component_files(self):
        source=LIB.read_text().split('case "$NFQWS_PKG_ACTION" in')[0]
        r=subprocess.run(['sh','-c',source+'''
nfqws_package_dns_control() { echo dns-restore-failed; return 1; }
nfqws_package_service() { echo unexpected-service-change; }
nfqws_package_stop_services upgrade
'''],capture_output=True,text=True)
        self.assertNotEqual(r.returncode,0)
        self.assertEqual(r.stdout.splitlines(),['dns-restore-failed'])

    def test_remove_clears_dns_consent_before_stopping_owned_services(self):
        source=LIB.read_text().split('case "$NFQWS_PKG_ACTION" in')[0]
        r=subprocess.run(['sh','-c',source+'''
nfqws_package_dns_control() { printf 'dns-control-%s\\n' "$1"; }
nfqws_package_service() { printf '%s-%s\\n' "$1" "$2"; }
nfqws_package_stop_services remove
'''],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(r.stdout.splitlines()[0],'dns-control-remove')

    def test_native_update_checks_precede_dns_and_snapshot_follows_service_stop(self):
        source=LIB.read_text().split('case "$NFQWS_PKG_ACTION" in')[0]
        r=subprocess.run(['sh','-c',source+'''
nfqws_package_native_update() { printf 'update-%s\\n' "$1"; }
nfqws_package_service_owner() { return 0; }
nfqws_package_dns_control() { echo dns; }
nfqws_package_service() { printf '%s-%s\\n' "$1" "$2"; }
nfqws_package_stop_services upgrade
'''],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(r.stdout.splitlines(),['update-verify','dns','nfqws2-native-dns-stop','nfqws2-native-dns-resume-stop','nfqws2-native-stop','nfqws2-native-web-stop','update-capture'])

    def test_failed_native_manager_proof_cannot_change_dns_or_services(self):
        source=LIB.read_text().split('case "$NFQWS_PKG_ACTION" in')[0]
        r=subprocess.run(['sh','-c',source+'''
nfqws_package_native_update() { return 1; }
nfqws_package_service_owner() { return 0; }
nfqws_package_dns_control() { echo unexpected; }
nfqws_package_service() { echo unexpected; }
nfqws_package_stop_services upgrade
'''],capture_output=True,text=True)
        self.assertNotEqual(r.returncode,0);self.assertEqual(r.stdout,'')

    def test_apk_upgrade_stops_old_process_before_replacing_its_executable(self):
        source=LIB.read_text().split('case "$NFQWS_PKG_ACTION" in')[0]
        r=subprocess.run(['sh','-c',source+'''
nfqws_package_preremove() { printf 'stop-for-%s\n' "$1"; }
NFQWS_PKG_FORMAT=apk; PKG_UPGRADE=1; nfqws_package_prepare_upgrade
NFQWS_PKG_FORMAT=ipk; PKG_UPGRADE=1; nfqws_package_prepare_upgrade
NFQWS_PKG_FORMAT=apk; PKG_UPGRADE=0; nfqws_package_prepare_upgrade
'''],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(r.stdout.splitlines(),['stop-for-upgrade'])

    def test_prerm_before_preinst_keeps_running_intent_only_for_same_transaction(self):
        source=LIB.read_text().split('case "$NFQWS_PKG_ACTION" in')[0]
        with tempfile.TemporaryDirectory()as td:
            body=source+'''
nfqws_package_state_dir="$TEST_STATE"
nfqws_package_manager() { printf '%s\n' "$TEST_MANAGER"; }
nfqws_package_guard() { mkdir -p "$1"; }
nfqws_package_service_state() { printf 'enabled=1\nrunning=%s\n' "$TEST_RUNNING"; }
TEST_MANAGER=boot:123:456; TEST_RUNNING=1
nfqws_package_snapshot
TEST_RUNNING=0
nfqws_package_snapshot
grep '^running=1$' "$TEST_STATE/state" || exit 1
TEST_MANAGER=boot:999:1000
nfqws_package_snapshot
grep '^running=0$' "$TEST_STATE/state" || exit 1
'''
            r=subprocess.run(['sh','-c',body],env={**os.environ,'TEST_STATE':td},capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr+r.stdout)
            self.assertEqual(r.stdout.splitlines(),['running=1','running=0'])


if __name__=='__main__':unittest.main()

"""Package hooks share state only within one live manager transaction."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

LIB=Path(__file__).resolve().parents[1]/'openwrt/package-lifecycle.sh'


class NativePackageLifecycleTests(unittest.TestCase):
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

import os
from pathlib import Path
import subprocess
import shlex
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / 'asus/lifecycle.sh'


class ServiceTests(unittest.TestCase):
    def test_imported_strategy_uses_runtime_defaults_and_keeps_explicit_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lib = root / 'opt/lib/nfqws2-asus'
            lib.mkdir(parents=True)
            (lib / 'platform.sh').write_bytes((ROOT / 'asus/platform.sh').read_bytes())
            (lib / 'lifecycle.sh').write_text('''asus_lock() { :; }
asus_check() { asus_validate && printf '%s|%s|%s\\n' "$NFQUEUE_NUM" "$USER" "$LOG_LEVEL"; }
''')
            for name in ['diagnostics.sh', 'legacy.sh', 'args.sh']:
                (lib / name).write_text('')
            (lib / 'compatibility.sh').write_text('asus_read_compatibility() { :; }\n')
            conf = root / 'opt/etc/nfqws2/nfqws2.conf'
            conf.parent.mkdir(parents=True)
            script = root / 'service'
            script.write_text((ROOT / 'asus/S51nfqws2').read_text().replace('/opt/', str(root) + '/opt/'))
            base = 'TCP_PORTS=80,443\nUDP_PORTS=443\nNFQWS_ARGS="--filter-tcp=443"\n'
            for extra, expected, rc in [('', '300|nobody|0', 0),
                    ('NFQUEUE_NUM=321\nUSER=routeruser\nLOG_LEVEL=1\n', '321|routeruser|1', 0),
                    ('NFQUEUE_NUM=65536\n', '', 1), ('NFQUEUE_NUM=""\n', '', 1)]:
                with self.subTest(extra=extra):
                    conf.write_text(base + extra)
                    result = subprocess.run(shlex.split(os.environ.get('TEST_SHELL', 'sh')) + [str(script), 'check'],
                                            capture_output=True, text=True, env={**os.environ, 'USER': 'inherited-user'})
                    self.assertEqual(result.returncode, rc, result.stderr)
                    self.assertEqual(result.stdout.strip(), expected)

    def run_sh(self, body, owner=0):
        with tempfile.TemporaryDirectory() as tmp:
            prelude = f'. "{LIB}"\n' if LIB.exists() else ''
            # The router's runtime directory belongs to root. Keep the real
            # filesystem and flock, but model ownership for unprivileged CI.
            prelude += '''
            stat() {
                if [ "$#" = 2 ] && [ "$1" = -t ] && [ "$2" = "$WORK" ]; then
                    printf '%s 4096 8 41c0 %s 0 00 123 2 0 0 1 1 1 4096\\n' "$WORK" "$FIXTURE_OWNER"
                else
                    command stat "$@"
                fi
            }
            '''
            return subprocess.run(shlex.split(os.environ.get('TEST_SHELL', 'sh')) + ['-c', prelude + body], text=True,
                                  capture_output=True, env={**os.environ, 'WORK': tmp, 'FIXTURE_OWNER': str(owner)})

    def test_stale_pid_for_other_process_not_treated_as_daemon(self):
        r = self.run_sh('PIDFILE="$WORK/pid"; NFQWS_BIN=/opt/usr/bin/nfqws2; echo $$ > "$PIDFILE"; asus_running')
        self.assertEqual(r.returncode, 1, r.stderr)

    def test_daemon_recognized_through_symlinked_install_path(self):
        r = self.run_sh('''
        mkdir "$WORK/usb"; ln -s "$WORK/usb" "$WORK/opt"
        ln -s "$(readlink /proc/$$/exe)" "$WORK/usb/daemon"
        PIDFILE=$WORK/pid; echo $$ > "$PIDFILE"
        NFQWS_BIN=$WORK/opt/daemon; asus_running
        ''')
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_firewall_failure_removes_partial_rules(self):
        r = self.run_sh('''
        RUN_DIR=$WORK; IPV6_ENABLED=0
        asus_rules() { echo rules; }
        printf '#!/bin/sh\nexit 1\n' > "$WORK/iptables-restore"
        chmod +x "$WORK/iptables-restore"; PATH="$WORK:$PATH"
        asus_firewall_stop() { echo CLEANED; }
        asus_firewall_apply; echo RESULT=$?
        ''')
        self.assertIn('CLEANED', r.stdout)
        self.assertIn('RESULT=1', r.stdout)

    def test_enabled_ipv6_is_applied_and_removed_on_stop(self):
        r = self.run_sh('''
        RUN_DIR=$WORK; ASUS_WAN=eth0; IPV6_ENABLED=1
        iptables() { case "$*" in *' -S '*) echo ipv4-rules;; esac; }
        printf '#!/bin/sh\ncat >/dev/null\necho IPV4_RESTORE\n' > "$WORK/iptables-restore"
        printf '#!/bin/sh\ncat >/dev/null\necho IPV6_RESTORE\n' > "$WORK/ip6tables-restore"
        chmod +x "$WORK/iptables-restore" "$WORK/ip6tables-restore"; PATH="$WORK:$PATH"
        ip6tables() { case "$*" in *' -S '*) echo ipv6-rules;; esac; }
        asus_rules() { echo rules; }
        asus_detach_family() { echo "DETACH $1"; }
        asus_firewall_apply || exit 1
        asus_firewall_stop
        ''')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.splitlines(), ['IPV4_RESTORE', 'IPV4_RESTORE', 'IPV6_RESTORE', 'DETACH iptables', 'DETACH ip6tables'])

    def test_snapshot_detects_missing_ipv6_hook(self):
        r = self.run_sh('''
        IPV6_ENABLED=1
        iptables() { return 0; }
        ip6tables() { case "$*" in *' -C '*) return 1;; esac; }
        asus_snapshot
        ''')
        self.assertEqual(r.returncode, 1, r.stderr)

    def test_stopped_service_is_not_revived_by_reconcile(self):
        r = self.run_sh('''
        RUN_DIR=$WORK
        asus_start() { echo UNEXPECTED_START; }
        asus_reconcile
        ''')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn('UNEXPECTED', r.stdout)

    def test_reconcile_starts_waiting_service_when_enabled(self):
        r = self.run_sh('''
        RUN_DIR=$WORK; touch "$RUN_DIR/enabled"
        asus_running() { return 1; }
        asus_start() { echo STARTED; }
        asus_reconcile
        ''')
        self.assertEqual(r.stdout.strip(), 'STARTED')

    def test_sysctl_restore_respects_changes_by_other_service(self):
        r = self.run_sh('''
        RUN_DIR=$WORK
        printf 'net.netfilter.nf_conntrack_acct 0 1\n' > "$RUN_DIR/sysctls"
        sysctl() { case "$1" in -n) echo 2;; -w) echo UNEXPECTED_WRITE;; esac; }
        asus_restore_sysctls
        ''')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn('UNEXPECTED_WRITE', r.stdout)

    def test_lock_prevents_second_controller(self):
        r = self.run_sh('''
        RUN_DIR=$WORK
        asus_error() { return 1; }
        asus_lock || exit 9
        asus_lock; echo RESULT=$?
        ''')
        self.assertIn('RESULT=75', r.stdout)

    def test_restore_supports_entware_iptables_1_4_21(self):
        r = self.run_sh('''
        RUN_DIR=$WORK
        printf '#!/bin/sh\n[ "$*" = "--noflush" ] || exit 2\ncat >/dev/null\n' > "$WORK/iptables-restore"
        chmod +x "$WORK/iptables-restore"; PATH="$WORK:$PATH"
        asus_rules() { echo rules; }; asus_attach() { return 0; }
        asus_firewall_family 4
        ''')
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_runtime_directory_symlink_rejected(self):
        r = self.run_sh('''
        mkdir "$WORK/elsewhere"; ln -s "$WORK/elsewhere" "$WORK/runtime"
        RUN_DIR=$WORK/runtime; asus_lock
        ''')
        self.assertNotEqual(r.returncode, 0)

    def test_runtime_directory_owned_by_nonroot_rejected(self):
        r = self.run_sh('RUN_DIR=$WORK; asus_lock', owner=1000)
        self.assertNotEqual(r.returncode, 0)

    def test_lock_with_busybox_stat_without_format_option(self):
        r = self.run_sh('''
        RUN_DIR=$WORK
        stat() {
            [ "$#" = 2 ] && [ "$1" = -t ] || return 1
            printf '%s 4096 8 41c0 0 0 00 123 2 0 0 1 1 1 4096\\n' "$2"
        }
        asus_lock
        ''')
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_abandoned_empty_lock_does_not_disable_management(self):
        r = self.run_sh('''
        RUN_DIR=$WORK
        mkdir "$WORK/lock"
        asus_lock
        ''')
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_wan_change_restarts_daemon_with_runtime_config(self):
        r = self.run_sh('''
        RUN_DIR=$WORK; touch "$WORK/enabled"; echo eth0 > "$WORK/wan"
        asus_running() { return 0; }; asus_interfaces() { echo ppp0; }
        asus_firewall_stop() { echo DETACH; }; asus_kill() { echo STOP; }
        asus_start() { echo "START $ASUS_RECONCILING"; }
        asus_firewall_apply() { echo STALE_DAEMON; }
        asus_reconcile
        ''')
        self.assertEqual(r.stdout.splitlines(), ['DETACH', 'STOP', 'START 1'])

    def test_failed_recovery_retries_after_transient_error(self):
        r = self.run_sh('''
        RUN_DIR=$WORK; asus_lock || exit 9
        CONFFILE=$WORK/config; echo '# cfg' > "$CONFFILE"
        touch "$WORK/enabled"; cp "$CONFFILE" "$WORK/runtime.conf"
        asus_running() { test -f "$WORK/running"; }
        asus_check() { return 0; }; asus_interfaces() { echo eth0; }
        cru() { [ "$1" != d ] || echo DELETED_CRON; }
        asus_sysctls() { test -f "$WORK/fixed"; }
        asus_firewall_stop() { return 0; }; asus_restore_sysctls() { return 0; }
        asus_kill() { rm -f "$WORK/running"; }
        _startup_args() { :; }
        NFQWS_BIN=$WORK/daemon
        printf '#!/bin/sh\n[ ! -e /proc/$$/fd/9 ] || exit 9\ntouch "$WORK/running"\n' > "$NFQWS_BIN"; chmod +x "$NFQWS_BIN"
        asus_firewall_apply() { echo READY; }
        asus_reconcile; echo FIRST=$?
        touch "$WORK/fixed"
        asus_reconcile; echo SECOND=$?
        ''')
        self.assertIn('FIRST=1', r.stdout)
        self.assertIn('READY', r.stdout)
        self.assertIn('SECOND=0', r.stdout)
        self.assertNotIn('DELETED_CRON', r.stdout)


if __name__ == '__main__': unittest.main()

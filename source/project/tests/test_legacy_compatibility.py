"""Exercise selection/dispatch without changing the host's netfilter."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CompatibilityTests(unittest.TestCase):
    def run_shell(self, body):
        with tempfile.TemporaryDirectory() as td:
            return subprocess.run(shlex.split(os.environ.get('TEST_SHELL', 'sh')) + ['-c',
                f'. "{ROOT}/asus/compatibility.sh"\nRUN_DIR="$WORK"\n' + body],
                env={**os.environ, 'WORK': td}, text=True, capture_output=True)

    def test_fallback_keeps_native_pair_and_roundtrips_observed_direction(self):
        r = self.run_shell('''
        asus_probe_family() { [ "$ASUS_XTABLES4" = native-no-w ]; }
        asus_probe_direction() { echo reverse; }
        IPV6_ENABLED=0; asus_choose_tools || exit 1
        asus_save_compatibility || exit 3
        ASUS_XTABLES4=wrong; ASUS_CT4=wrong
        asus_read_compatibility || exit 2
        printf '%s %s\n' "$ASUS_XTABLES4" "$ASUS_CT4"
        ''')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), 'native-no-w reverse')

    def test_check_does_not_replace_active_ipv6_tool_selection(self):
        r = self.run_shell('''
        printf 'native-no-w reverse native-no-w reverse\n' > "$RUN_DIR/compatibility"
        cp "$RUN_DIR/compatibility" "$WORK/before"
        asus_probe_family() { return 0; }
        asus_probe_direction() { echo normal; }
        IPV6_ENABLED=0; asus_choose_tools || exit 1
        cmp "$WORK/before" "$RUN_DIR/compatibility"
        ''')
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_native_dispatch_strips_only_wait_and_preserves_restore_stdin(self):
        r = self.run_shell('''
        asus_native_xtables_path() { printf '%s/tool\n' "$WORK"; }
        printf '#!/bin/sh\nprintf "arg:<%%s>\\n" "$@"\ncat\n' > "$WORK/tool"
        chmod +x "$WORK/tool"
        ASUS_XTABLES4=native-no-w
        printf 'rules\n' | asus_xtables iptables-restore --noflush
        asus_xtables iptables -w -t mangle -L </dev/null
        ''')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, 'arg:<--noflush>\nrules\narg:<-t>\narg:<mangle>\narg:<-L>\n')

    def test_invalid_cache_cannot_select_commands_or_reverse_rules(self):
        r = self.run_shell('''
        echo 'native-no-w reverse native malicious' > "$RUN_DIR/compatibility"
        asus_read_compatibility
        ''')
        self.assertNotEqual(r.returncode, 0)


if __name__ == '__main__': unittest.main()

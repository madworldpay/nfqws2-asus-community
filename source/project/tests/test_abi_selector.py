"""Entware primary-ABI selection without opkg or a recursive private awk."""
import io
import os
from pathlib import Path
import shlex
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
OPKG = Path(os.environ.get('OPKG_TEST_BINARY', ROOT / '.work/packaging-audit-20261012/opkg-x64'))


class AbiSelectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.root = self.work / 'root'
        self.cfg = self.root / 'opt/etc/opkg.conf'
        self.cfg.parent.mkdir(parents=True)
        self.dropins = self.root / 'opt/etc/opkg'
        self.dropins.mkdir()
        self.helper = (ROOT / 'asus/abi.sh').read_text().replace('/opt/', str(self.root) + '/opt/')
        self.shell_command = ['/bin/sh']
        if busybox := os.environ.get('MIGRATION_BUSYBOX_TEST_BINARY'):
            # Put the actual BusyBox awk at the fixed system-awk boundary;
            # a shell function cannot replace the absolute bootstrap lookup.
            system_awk = self.work / 'system-awk'
            system_awk.write_text('#!/bin/sh\nexec ' + shlex.quote(busybox) + ' awk "$@"\n')
            system_awk.chmod(0o755)
            self.helper = self.helper.replace('/usr/bin/awk', str(system_awk)).replace('/bin/awk', str(system_awk))
            self.shell_command = [busybox, 'sh']

    def configure(self, main, dropins=None):
        self.cfg.write_text('dest root /\n' + main)
        for name, body in (dropins or {}).items():
            (self.dropins / name).write_text(body)

    def shell(self, command, prefix='', env=None):
        return subprocess.run(
            self.shell_command + ['-c', prefix + self.helper + '\n' + command],
            text=True, capture_output=True, timeout=5,
            env={**os.environ, **(env or {})},
        )

    def assert_abi(self, expected, family='armv7'):
        for command in ['asus_entware_primary_abi', 'asus_resolve_package_abi ' + shlex.quote(family)]:
            with self.subTest(command=command):
                result = self.shell(command)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, expected + '\n')
                self.assertEqual(result.stderr, '')

    def assert_refused(self, command):
        result = self.shell(command)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotEqual(result.returncode, 127, result.stderr)
        self.assertEqual(result.stdout, '')
        self.assertTrue(result.stderr.strip(), 'failure should explain the unavailable ABI')
        self.assertLess(len(result.stderr), 300)

    def test_primary_priority_beats_compatibility_architecture(self):
        self.configure('arch all 999\narch armv7-2.6 100\narch armv7-3.2 160\n')
        self.assert_abi('armv7-3.2')

    def test_armv7_family_selects_legacy_runtime(self):
        self.configure('arch all 100\narch armv7-3.2 100\narch armv7-2.6 160\n')
        self.assert_abi('armv7-2.6')

    def test_aarch64_family_selects_only_its_primary_abi(self):
        self.configure('arch all 100\narch aarch64-3.10 160\narch armv7-3.2 100\n')
        self.assert_abi('aarch64-3.10', 'aarch64-3.10')
        self.assert_refused('asus_resolve_package_abi armv7')

    def test_secondary_aarch64_cannot_override_armv7_primary(self):
        self.configure('arch armv7-3.2 160\narch aarch64-3.10 100\n')
        self.assert_refused('asus_resolve_package_abi aarch64-3.10')

    def test_unknown_higher_priority_is_not_ignored(self):
        self.configure('arch armv7-3.2 160\narch future-arm-abi 200\n')
        result = self.shell('asus_entware_primary_abi')
        self.assertEqual((result.returncode, result.stdout), (0, 'future-arm-abi\n'), result.stderr)
        self.assert_refused('asus_resolve_package_abi armv7')

    def test_different_highest_abis_are_ambiguous(self):
        self.configure('arch armv7-2.6 160\narch armv7-3.2 160\n')
        self.assert_refused('asus_entware_primary_abi')
        self.assert_refused('asus_resolve_package_abi armv7')

    def test_failure_explains_abi_with_caller_errexit_enabled(self):
        self.configure('arch armv7-2.6 160\narch armv7-3.2 160\n')
        for command in ['asus_entware_primary_abi', 'asus_resolve_package_abi armv7']:
            with self.subTest(command=command):
                result = self.shell(command, prefix='set -eu\n')
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, '')
                self.assertTrue(result.stderr.strip(), 'errexit must not discard the diagnostic')

    def test_duplicate_abis_use_first_declared_priority(self):
        for lines, expected in [
            ('arch armv7-2.6 100\narch armv7-2.6 200\narch armv7-3.2 160\n', 'armv7-3.2'),
            ('arch armv7-2.6 200\narch armv7-2.6 100\narch armv7-3.2 160\n', 'armv7-2.6'),
            ('arch armv7-3.2 160\narch armv7-3.2 160\n', 'armv7-3.2'),
        ]:
            with self.subTest(lines=lines):
                self.configure(lines)
                self.assert_abi(expected)

    def test_fixed_dropins_participate_in_priority_and_duplicates(self):
        self.configure('arch armv7-3.2 160\n', {
            '10-compat.conf': 'arch armv7-3.2 500\narch armv7-2.6 100\n',
            '20-primary.conf': 'arch armv7-2.6 500\narch aarch64-3.10 80',
            'ignored.txt': 'arch aarch64-3.10 900\n',
        })
        self.assert_abi('armv7-3.2')

    def test_quoted_priority_and_atoi_prefix_ordering(self):
        for priority in ['"160"', '"  +160 spaces"', '+160suffix', '000160']:
            with self.subTest(priority=priority):
                self.configure('arch armv7-2.6 100\n"arch" "armv7-3.2" ' + priority)
                self.assert_abi('armv7-3.2')

    def test_empty_missing_and_non_numeric_priority_have_effective_zero(self):
        for priority in ['', '""', 'garbage', '0x160']:
            with self.subTest(priority=priority):
                self.configure('arch armv7-2.6 ' + priority + '\narch armv7-3.2 1\n')
                self.assert_abi('armv7-3.2')

    def test_suffix_after_quoted_priority_is_unquoted_literal(self):
        for suffix in ['junk', 'junk more']:
            with self.subTest(suffix=suffix):
                self.configure('arch armv7-2.6 "160"' + suffix + '\narch armv7-3.2 1\n')
                self.assert_abi('armv7-3.2')

    def test_overflowing_priority_fails_closed(self):
        for priority in ['2147483648', '-2147483649', '9999999999999999999999']:
            with self.subTest(priority=priority):
                self.configure('arch armv7-3.2 160\narch armv7-2.6 ' + priority + '\n')
                self.assert_refused('asus_entware_primary_abi')

    def test_config_read_error_is_not_misreported_as_bad_priority(self):
        self.configure('arch armv7-3.2 160\n')
        (self.dropins / 'directory.conf').mkdir()
        result = self.shell('asus_entware_primary_abi')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')
        self.assertTrue(result.stderr.strip())
        self.assertNotIn('priority', result.stderr)

    def test_missing_primary_and_unsupported_family_fail_closed(self):
        for main in ['', 'arch all 100\n', '# arch armv7-3.2 160\n',
                     'arch armv7-3.2\n', 'arch armv7-2.6 -20\n', 'arch armv7-3.2 0\n']:
            with self.subTest(main=main):
                self.configure(main)
                self.assert_refused('asus_entware_primary_abi')
        self.configure('arch armv7-3.2 160\n')
        self.assert_refused('asus_resolve_package_abi mips')
        self.assert_refused('asus_resolve_package_abi')

    def test_configuration_tokens_are_data_and_never_shell_code(self):
        marker = self.work / 'unexpected'
        injected = '$(touch ' + str(marker) + ')'
        self.configure('arch armv7-3.2 160\n' + injected + '\narch "' + injected + '" 100\n')
        self.assert_abi('armv7-3.2')
        result = self.shell('asus_entware_abi_matches ' + shlex.quote(injected))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(marker.exists())
        self.assertNotEqual(self.shell('asus_entware_abi_matches "armv7-*"').returncode, 0)

    def test_all_interfaces_avoid_private_awk_and_opkg_recursion(self):
        self.configure('arch armv7-3.2 160\n')
        wrappers = self.work / 'private-bin'
        wrappers.mkdir()
        for name in ['awk', 'opkg']:
            wrapper = wrappers / name
            wrapper.write_text('#!/bin/sh\necho recursive-' + name + ' >&2\nexit 97\n')
            wrapper.chmod(0o755)
        prefix = 'awk() { echo recursive-function >&2; return 98; }\n'
        for command, expected in [
            ('asus_entware_abi_matches armv7-3.2', ''),
            ('asus_entware_primary_abi', 'armv7-3.2\n'),
            ('asus_resolve_package_abi armv7', 'armv7-3.2\n'),
        ]:
            with self.subTest(command=command):
                result = self.shell(command, prefix=prefix, env={'PATH': str(wrappers)})
                self.assertEqual((result.returncode, result.stdout, result.stderr), (0, expected, ''))

    def test_noglob_flag_is_preserved_after_success_and_failure(self):
        self.configure('arch all 100\n', {'abi.conf': 'arch armv7-2.6 160'})
        for command in [
            'asus_entware_abi_matches armv7-2.6',
            'asus_entware_abi_matches aarch64-3.10',
            'asus_entware_primary_abi',
            'asus_resolve_package_abi armv7',
            'asus_resolve_package_abi aarch64-3.10',
        ]:
            with self.subTest(command=command):
                result = self.shell(command + '\ncase "$-" in *f*) exit 0;; *) exit 9;; esac', prefix='set -f\n')
                self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(OPKG.exists(), 'matching test opkg not supplied')
    def test_lexical_acceptance_matches_real_opkg(self):
        (self.root / 'opt/tmp').mkdir()
        (self.work / 'tmp').mkdir()
        lines = [
            'arch "armv7-3.2" "160"\n', '"arch""armv7-3.2""160"\n',
            'arch armv7-3.2 160', 'arch armv7-3.2\n',
            'arch armv7-3.2 "160 spaces"\n', 'arch armv7-3.2 160 extra\n',
            'arch armv7-3.2 160 # comment\n', 'arch armv7-3.2 160 "one word"\n',
            '# arch armv7-3.2 160\n', 'arch armv7-3.2 "160\n',
            'arch armv7-3.2 "160"junk\n', 'arch armv7-3.2 "160"junk more\n',
        ]
        for line in lines:
            with self.subTest(line=line):
                self.configure(line)
                actual = subprocess.run([
                    str(OPKG), '-f', str(self.cfg), '-o', str(self.root),
                    '--tmp-dir', str(self.work / 'tmp'), 'print-architecture',
                ], text=True, capture_output=True, check=True, timeout=5)
                result = self.shell('asus_entware_abi_matches armv7-3.2')
                self.assertEqual(result.returncode == 0, 'arch armv7-3.2 ' in actual.stdout, actual.stderr + result.stderr)

    @unittest.skipUnless(OPKG.exists(), 'matching test opkg not supplied')
    def test_effective_priority_and_duplicate_order_match_real_opkg(self):
        def archive(files):
            output = io.BytesIO()
            with tarfile.open(fileobj=output, mode='w:gz') as tar:
                for name, body in files.items():
                    member = tarfile.TarInfo(name)
                    member.size = len(body)
                    tar.addfile(member, io.BytesIO(body))
            return output.getvalue()

        (self.root / 'opt/tmp').mkdir()
        (self.work / 'tmp').mkdir()
        package = self.work / 'priority-probe.ipk'
        package.write_bytes(archive({
            'debian-binary': b'2.0\n',
            'control.tar.gz': archive({'control': b'Package: abi-priority-probe\nVersion: 1\nArchitecture: armv7-2.6\nDescription: ABI priority probe\n'}),
            'data.tar.gz': archive({}),
        }))
        cases = [
            ('arch armv7-2.6\n', False), ('arch armv7-2.6 ""\n', False),
            ('arch armv7-2.6 rubbish\n', False), ('arch armv7-2.6 -20\n', False),
            ('arch armv7-2.6 "160 spaces"\n', True),
            ('arch armv7-2.6 "160"junk\n', False),
            ('arch armv7-2.6 0\narch armv7-2.6 160\n', False),
            ('arch armv7-2.6 160\narch armv7-2.6 0\n', True),
        ]
        for declarations, accepted in cases:
            with self.subTest(declarations=declarations):
                self.configure(declarations + 'arch armv7-3.2 1\n')
                actual = subprocess.run([
                    str(OPKG), '-f', str(self.cfg), '-o', str(self.root),
                    '--tmp-dir', str(self.work / 'tmp'), '--noaction', 'install', str(package),
                ], text=True, capture_output=True, timeout=5)
                self.assertEqual(actual.returncode == 0, accepted, actual.stdout + actual.stderr)
                self.assert_abi('armv7-2.6' if accepted else 'armv7-3.2')


if __name__ == '__main__':
    unittest.main()

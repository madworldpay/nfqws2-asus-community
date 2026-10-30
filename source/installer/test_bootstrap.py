"""Exercise the documented bootstrap in a stock shell with no mktemp."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class BootstrapTests(unittest.TestCase):
    def run_command(self, command, *, curl_ok=True, wget_ok=True, collision=False):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            tools = work/'bin'; tools.mkdir()
            for name in ('mkdir', 'rm', 'rmdir'):
                (tools/name).symlink_to(shutil.which(name))
            for name, ok, flag in [('curl', curl_ok, '-o'), ('wget', wget_ok, '-O'), ('uclient-fetch', wget_ok, '-O')]:
                script = tools/name
                script.write_text('#!/bin/sh\n' + ('exit 22\n' if not ok else
                    f'while [ "$#" -gt 0 ]; do if [ "$1" = {flag} ]; then shift; out=$1; fi; shift; done\n'
                    'printf \'printf "bootstrap-ran\\\\n"\\n\' > "$out"\n'))
                script.chmod(0o755)
            (tools/'sh').symlink_to('/bin/sh')
            command = command.replace('/tmp/nfqws2-install.', str(work/'nfqws2-install.'))
            existing = work/'nfqws2-install.collision'
            if collision:
                command = command.replace('$$', 'collision')
                existing.mkdir(); (existing/'owner-data').write_text('keep')
            result = subprocess.run(['/bin/sh', '-c', command], env={**os.environ, 'PATH': str(tools)},
                                    capture_output=True, text=True, timeout=10)
            if collision:
                self.assertEqual((existing/'owner-data').read_text(), 'keep')
            else:
                self.assertEqual(list(work.glob('nfqws2-install.*')), [])
            return result

    def commands(self):
        return re.findall(r'```sh\n(.*?)\n```', (ROOT/'README.md').read_text(), re.S)[:2]

    def test_stock_shell_downloads_and_runs_without_mktemp(self):
        for command in self.commands():
            with self.subTest(command=command):
                r = self.run_command(command)
                self.assertEqual(r.returncode, 0, r.stdout+r.stderr)
                self.assertIn('bootstrap-ran', r.stdout)

    def test_fallback_download_and_failure_do_not_run_partial_script(self):
        for command in self.commands():
            r = self.run_command(command, curl_ok=False)
            self.assertEqual(r.returncode, 0, r.stdout+r.stderr)
            self.assertIn('bootstrap-ran', r.stdout)
            r = self.run_command(command, curl_ok=False, wget_ok=False)
            self.assertNotEqual(r.returncode, 0)
            self.assertNotIn('bootstrap-ran', r.stdout)

    def test_existing_directory_is_preserved(self):
        for command in self.commands():
            r = self.run_command(command, collision=True)
            self.assertNotEqual(r.returncode, 0)
            self.assertNotIn('bootstrap-ran', r.stdout)


if __name__ == '__main__':
    unittest.main()

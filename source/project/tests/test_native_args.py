"""Use the matching native upstream binary to check real argument/Lua parsing.

Set NFQWS_TEST_BINARY to the x86_64 binary from the pinned multiarch release.
This checks profiles, not the ARM64 ABI, kernel NFQUEUE or real traffic.
"""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from test_packages import ROOT, read_ipk


class NativeArgumentTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('NFQWS_TEST_BINARY'), 'optional matching native binary not supplied')
    def test_default_profiles_and_lua_load_in_real_daemon(self):
        package = read_ipk(next(Path(os.environ.get('PACKAGES_DIR', ROOT/'dist')).glob('nfqws2-asus_*.ipk')))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, (_, content) in package['data'].items():
                dest = root/name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(content)
            (root/'opt/var/log').mkdir(parents=True)
            conf = root/'opt/etc/nfqws2/nfqws2.conf'
            template = conf.with_name(conf.name+'.notactive')
            if template.exists(): conf.write_bytes(template.read_bytes())
            for sample in (root/'opt/etc/nfqws2/lists').glob('*.notactive'):
                sample.with_name(sample.name.removesuffix('.notactive')).write_bytes(sample.read_bytes())
            conf.write_text(conf.read_text().replace('/opt/',tmp+'/opt/'))
            script = f'''set -f
. {shlex.quote(str(conf))}
. {shlex.quote(str(root/'opt/lib/nfqws2-asus/args.sh'))}
# This container cannot change supplementary groups. Omit only privilege drop.
args=$(_startup_args | sed 's/--user=[^ ]* //')
{shlex.quote(os.environ['NFQWS_TEST_BINARY'])} --dry-run $args
'''
            r = subprocess.run(shlex.split(os.environ.get('TEST_SHELL', 'sh'))+['-c', script],
                               text=True, capture_output=True, timeout=15)
            self.assertEqual(r.returncode, 0, r.stdout+r.stderr)
            self.assertIn('5 user defined desync profile(s)', r.stdout+r.stderr)


if __name__ == '__main__': unittest.main()

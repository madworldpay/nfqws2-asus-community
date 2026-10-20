import os
from pathlib import Path
import shlex
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class LegacyModuleTests(unittest.TestCase):
    def probe(self, model='RT-AC87U', extend='10', valid_hash=True):
        body = '''
        nvram() { case "$2" in productid) echo "$MODEL";; firmver) echo 3.0.0.4;; buildno) echo 384.13;; extendno) echo "$EXTEND";; esac; }
        uname() { echo '2.6.36.4brcmarm armv7l'; }
        asus_legacy_fingerprints() { test "$HASH_OK" = 1; }
        insmod() { printf 'loaded:%s\n' "$1"; }
        asus_load_legacy_module
        '''
        return subprocess.run(shlex.split(os.environ.get('TEST_SHELL', 'sh')) + ['-c',
            f'. "{ROOT}/asus/legacy.sh"\n' + body], env={**os.environ, 'MODEL':model,
            'EXTEND':extend, 'HASH_OK':'1' if valid_hash else '0'}, text=True, capture_output=True)

    def test_exact_profile_loads_without_force_but_mismatch_never_loads(self):
        r=self.probe()
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('nfnetlink_queue.ko',r.stdout)
        self.assertNotIn('-f ',r.stdout)
        for kw in [{'model':'RT-AC68U'}, {'extend':'11'}, {'valid_hash':False}]:
            r=self.probe(**kw)
            self.assertNotEqual(r.returncode,0)
            self.assertNotIn('loaded:',r.stdout)


if __name__ == '__main__': unittest.main()

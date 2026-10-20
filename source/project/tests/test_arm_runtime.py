"""Run the packaged ARMv7 selectors and applet wrappers with real QEMU ELFs.

Only the final foreign-ELF exec is adapted for the host without binfmt ARM.
The canonical shell shim, ABI parser, private PATH and nested scripts are real.
This checks userspace bootstrap, not a legacy router's kernel/NFQUEUE.
"""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from test_packages import read_ipk, ROOT

AUDIT = ROOT/'.work/packaging-audit-20261012'


@unittest.skipUnless((AUDIT/'qemu-arm').exists(), 'QEMU ARM runtime not supplied')
class ArmRuntimeTests(unittest.TestCase):
    def test_private_shell_and_awk_bootstrap_for_both_arm_abis(self):
        packages = Path(os.environ.get('PACKAGES_DIR', ROOT/'dist'))
        candidates = list(packages.glob('nfqws2-asus_*_armv7.ipk'))
        self.assertEqual(len(candidates),1,'Build the unified ARMv7 IPK first')
        data = read_ipk(candidates[0])['data']
        for abi, version, sysroot in [('armv7-2.6','1.36.1','armv7-legacy-sysroot'),
                                      ('armv7-3.2','1.37.0','armv7-sysroot')]:
            with self.subTest(abi=abi), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                names = ['opt/lib/nfqws2-asus/abi.sh','opt/libexec/nfqws2-asus/busybox']
                names += [name for name in data if name.startswith('opt/lib/nfqws2-asus/bin/')]
                for name in names:
                    info, content = data[name]
                    p=root/name; p.parent.mkdir(parents=True,exist_ok=True)
                    p.write_bytes(content.replace(b'/opt/',str(root).encode()+b'/opt/'));p.chmod(info.mode)
                cfg=root/'opt/etc/opkg.conf'; cfg.parent.mkdir(parents=True)
                cfg.write_text(f'arch all 100\narch {abi} 160\n')
                variant=root/f'opt/libexec/nfqws2-asus/{abi}'
                native=variant/'native/busybox'; native.parent.mkdir(parents=True)
                native.write_bytes(data[f'opt/libexec/nfqws2-asus/{abi}/busybox'][1]);native.chmod(0o755)
                wrapper=variant/'busybox'
                wrapper.write_text('#!/bin/sh\nexec '+shlex.join([str(AUDIT/'qemu-arm'),'-L',str(AUDIT/sysroot),str(native)])+' "$@"\n');wrapper.chmod(0o755)
                canonical=root/'opt/libexec/nfqws2-asus/busybox'
                env={**os.environ,'PATH':str(root/'opt/lib/nfqws2-asus/bin')+':'+os.environ['PATH']}
                result=subprocess.run([str(canonical),'sh','-c',"awk 'BEGIN {print 2+3}'; sh -c 'printf bootstrapped'"],env=env,capture_output=True,text=True,timeout=10)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(result.stdout,'5\nbootstrapped')
                result=subprocess.run([str(canonical)],env=env,capture_output=True,text=True,timeout=10)
                self.assertIn('BusyBox v'+version,result.stdout+result.stderr)


if __name__ == '__main__': unittest.main()

import os
import shutil
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InstallTests(unittest.TestCase):
    def check(self, model, arch='aarch64', uid=0, with_id=True, package_arch='aarch64-3.10', entware_arch='aarch64-3.10'):
        with tempfile.TemporaryDirectory() as tmp:
            commands = {
                'nvram': f'[ "$2" = productid ] && echo {model}',
                'uname': f'echo {arch}',
                'opkg': 'echo "opkg cannot re-enter its install lock" >&2; exit 255',
                'cru': 'exit 0',
            }
            if with_id:
                commands['id'] = 'echo 0'
            (Path(tmp) / 'awk').symlink_to(shutil.which('awk'))
            for name, body in commands.items():
                p = Path(tmp) / name
                p.write_text('#!/bin/sh\n'+body+'\n');p.chmod(0o755)
            script = ROOT / 'asus/ipk/preinst'
            if not script.exists():
                return subprocess.CompletedProcess([], 127, '', 'preinst missing')
            # Model the router's procfs identity without requiring root on the PC.
            status = Path(tmp) / 'status'
            status.write_text(f'Name:\tsh\nUid:\t0\t{uid}\t0\t0\nGid:\t0\t0\t0\t0\n')
            fixture = Path(tmp) / 'preinst'
            config = Path(tmp) / 'opkg.conf'
            config.write_text(f'arch all 100\narch {entware_arch} 160\n')
            fixture.write_text(script.read_text().replace('. /opt/lib/nfqws2-asus/abi.sh', (ROOT/'asus/abi.sh').read_text()).replace('/proc/self/status', str(status)).replace('/opt/etc/opkg.conf', str(config)).replace('/opt/etc/opkg/*.conf', tmp+'/*.extra.conf').replace("ASUS_PACKAGE_ARCH='aarch64-3.10'", f"ASUS_PACKAGE_ARCH='{package_arch}'"))
            return subprocess.run(['/bin/sh', str(fixture), 'install'], text=True, capture_output=True,
                                  env={**os.environ, 'PATH': tmp})

    def test_both_exact_models_accepted(self):
        for model in ['GT-BE19000', 'GT-BE19000AI']:
            r = self.check(model)
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_other_model_is_allowed_with_risk_warning(self):
        r = self.check('GT-AX6000')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('own risk', r.stderr)

    def test_wrong_architecture_rejected(self):
        r = self.check('GT-BE19000', 'armv7l')
        self.assertEqual(r.returncode, 1, r.stderr)

    def test_armv7_target_installs_without_model_gate(self):
        for abi in ['armv7-2.6', 'armv7-3.2']:
            r=self.check('RT-AC87U', 'armv7l', package_arch='armv7', entware_arch=abi)
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_armv7_all_metadata_still_rejects_other_cpus_and_abis(self):
        for cpu, abi in [('mips','armv7-2.6'),('armv7l','aarch64-3.10'),('aarch64','aarch64-3.10')]:
            r=self.check('RT-AC87U',cpu,package_arch='armv7',entware_arch=abi)
            self.assertEqual(r.returncode,1,r.stderr)

    def test_wrong_entware_abi_is_rejected_even_with_matching_cpu(self):
        r=self.check('GT-BE19000AI', entware_arch='armv7-3.2')
        self.assertEqual(r.returncode, 1, r.stderr)

    def test_router_without_id_can_install_as_root(self):
        r = self.check('GT-BE19000AI', with_id=False)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_nonroot_effective_uid_rejected_without_id(self):
        r = self.check('GT-BE19000AI', uid=1000, with_id=False)
        self.assertEqual(r.returncode, 1, r.stderr)

    def test_invalid_effective_uid_rejected(self):
        r = self.check('GT-BE19000AI', uid='invalid', with_id=False)
        self.assertEqual(r.returncode, 1, r.stderr)


if __name__ == '__main__': unittest.main()

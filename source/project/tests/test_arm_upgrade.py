"""Upgrade actual ARMv7 IPKs with opkg, foreign BusyBox and a service boundary.

Offline paths, procfs UID, filesystem owner and service commands are adapted.
Dependencies are preinstalled fixtures: ELF/runtime coverage is separate.
No force-architecture/force-depends/downgrade flags are used; force-postinstall
only enables maintainer scripts inside opkg's test offline root.
"""
import os, io, tarfile, tempfile, subprocess, shlex, importlib.util, unittest
from pathlib import Path
r = Path(__file__).resolve().parents[1]
audit = r / '.work/packaging-audit-20261012'
work = r / '.work/legacy-arm-20261012'
packages = Path(os.environ.get('PACKAGES_DIR', r / 'dist'))
spec = importlib.util.spec_from_file_location('b', r / 'asus/build.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)

def read(p):
    out = {}
    with tarfile.open(p) as t:
        for section in ['control', 'data']:
            with tarfile.open(fileobj=io.BytesIO(t.extractfile(section + '.tar.gz').read())) as s:
                out[section] = {m.name.removeprefix('./'): (s.extractfile(m).read(), m.mode) for m in s if m.isfile()}
    return out

def write(p, c, d):
    p.write_bytes(b.compressed_tar({'debian-binary': (b'2.0\n', 420), 'control.tar.gz': (b.compressed_tar(c), 420), 'data.tar.gz': (b.compressed_tar(d), 420)}))
    return p

@unittest.skipUnless((audit / 'opkg-x64').exists() and (audit / 'qemu-arm').exists() and (work / 'old-armv7-asus5.ipk').exists(), 'previous ARM IPK and QEMU sysroots not supplied')
class ArmUpgradeTests(unittest.TestCase):

    def exercise(self, abi):
        candidates = list(packages.glob('nfqws2-asus_*_armv7.ipk'))
        self.assertEqual(len(candidates), 1, 'Build current ARMv7 package first')
        new_package = candidates[0]
        source_control = read(new_package)['control']['control'][0].decode()
        new_version = next((x.removeprefix('Version: ') for x in source_control.splitlines() if x.startswith('Version: ')))
        next_version = new_version.rsplit('+b', 1)[0] + '+b' + str(int(new_version.rsplit('+b', 1)[1]) + 1)
        with tempfile.TemporaryDirectory() as td:
            t = Path(td)
            root = t / 'root'
            (root / 'opt/tmp').mkdir(parents=True)
            (root / 'opt/etc').mkdir()
            (t / 'tmp').mkdir()
            (t / 'bin').mkdir()
            cfg = root / 'opt/etc/opkg.conf'
            cfg.write_text('dest root /\narch all 100\narch ' + abi + ' 160\n')
            status = t / 'proc-status'
            status.write_text('Uid:\t0\t0\t0\t0\n')
            for name, body in {'nvram': 'case "$2" in sw_mode) echo 1;; *) echo RT-AC68U;; esac', 'uname': 'echo armv7l', 'cru': 'exit 0', 'opkg': 'echo Nested-opkg-prohibited >&2; exit 255'}.items():
                p = t / 'bin' / name
                p.write_text('#!/bin/sh\n' + body + '\n')
                p.chmod(493)
            sysroot = audit / ('armv7-legacy-sysroot' if abi.endswith('2.6') else 'armv7-sysroot')
            bb = ('#!/bin/sh\nexec ' + shlex.join([str(audit / 'qemu-arm'), '-L', str(sysroot), str(sysroot / 'opt/bin/busybox')]) + ' "$@"\n').encode()
            source = read(new_package)
            depends = next((x for x in source['control']['control'][0].decode().splitlines() if x.startswith('Depends: '))).removeprefix('Depends: ').split(', ')
            pkgs = []
            for dep in depends:
                c = {'control': (f'Package: {dep}\nVersion: 99\nArchitecture: {abi}\nDescription: preinstalled dependency boundary\n'.encode(), 420)}
                pkgs.append(write(t / (dep + '.ipk'), c, {}))
            base = [str(audit / 'opkg-x64'), '-f', str(cfg), '-o', str(root), '--force-postinstall', '--tmp-dir', str(t / 'tmp')]
            env = {**os.environ, 'PATH': str(t / 'bin') + ':' + os.environ['PATH']}

            def run(paths):
                res = subprocess.run(base + ['install'] + list(map(str, paths)), env=env, capture_output=True, text=True, timeout=90)
                assert res.returncode == 0, res.stdout + res.stderr
                assert 'Nested-opkg-prohibited' not in res.stdout + res.stderr
                return res.stdout
            run(pkgs)

            def candidate(path, version=None):
                p = read(path)
                if version:
                    p['control']['control'] = (p['control']['control'][0].replace(('Version: ' + new_version).encode(), ('Version: ' + version).encode()), 420)
                for key in ['preinst', 'postinst', 'prerm', 'postrm']:
                    content, mode = p['control'][key]
                    text = content.decode().replace('ASUS_MIGRATION_OWNER=0', 'ASUS_MIGRATION_OWNER=' + str(os.getuid())).replace('if [ -n "$IPKG_INSTROOT" ]; then', 'if false; then').replace('/proc/self/status', str(status)).replace('/opt/', str(root) + '/opt/')
                    p['control'][key] = (text.encode(), mode)
                p['data']['opt/libexec/nfqws2-asus/busybox'] = (bb, 493)
                # Like S51/S81 below, the DNS root controller is a service
                # boundary here. Its real restore/abort behavior is exercised
                # by lifecycle/native tests, not an offline opkg root lacking PHP.
                if 'opt/lib/nfqws2-asus/smartdns/control.sh' in p['data']:
                    p['data']['opt/lib/nfqws2-asus/smartdns/control.sh'] = ((
                        '#!/bin/sh\nprintf "%s\\n" "smartdns $1" >> '+shlex.quote(str(t/'calls'))+'\n'
                    ).encode(),493)

                for s in ['S51nfqws2', 'S81nfqws-asus-web']:
                    p['data']['opt/etc/init.d/' + s] = (('#!/bin/sh\nprintf "%s\\n" "' + s + ' $1" >> ' + shlex.quote(str(t / 'calls')) + '\n').encode(), 493)
                dest = t / ('candidate' + str(len(list(t.glob('candidate*.ipk')))) + '.ipk')
                return write(dest, p['control'], p['data'])
            if abi.endswith('3.2'):
                old = r / '.work/legacy-arm-20261012/old-armv7-asus5.ipk'
                run([candidate(old)])
            else:
                run([candidate(new_package)])
            active = {'opt/etc/nfqws2/nfqws2.conf': b'# custom\nASUS_CLIENT_MODE="include"\nASUS_CLIENTS4="192.0.2.7"\n', 'opt/etc/nfqws2/lists/user.list': b'example.invalid\n', 'opt/etc/nfqws2/lists/custom.list': b'another.invalid\n', 'opt/etc/nfqws-asus-web/auth.json': b'{"mode":"disabled","username":"sample"}\n', 'opt/etc/nfqws-asus-web/ark-backup.json': b'{"sample":true}\n'}
            for name, data in active.items():
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
            if abi.endswith('3.2'):
                run([candidate(new_package)])
            out = run([candidate(new_package, next_version)])
            assert 'Upgrading nfqws2-asus' in out, out
            calls=(t/'calls').read_text().splitlines()
            last_dns=max(i for i,v in enumerate(calls) if v=='smartdns upgrade')
            assert calls.index('S51nfqws2 stop',last_dns)>last_dns,calls
            assert calls.index('S81nfqws-asus-web stop',last_dns)>last_dns,calls

            for name, data in active.items():
                assert (root / name).read_bytes() == data, name
            statusfiles = list(root.rglob('status'))
            assert any(('Version: ' + next_version in p.read_text() for p in statusfiles)), statusfiles

    def test_fresh_legacy_install_then_build_upgrade_preserves_settings(self):
        self.exercise('armv7-2.6')

    def test_modern_architecture_to_all_upgrade_preserves_settings(self):
        self.exercise('armv7-3.2')
if __name__ == '__main__':
    unittest.main()

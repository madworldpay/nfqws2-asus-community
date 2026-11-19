"""Run the actual previous release's staged PHP postflight on candidate settings."""
import hashlib
import io
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

from test_dpi_normalize import PHP


PUBLISHED = {
    99: {'aarch64-3.10': '9279ad5bfd73882e77fe36432431f1cf1989aec11adf805e23d404422b294fac',
         'armv7': 'b188a8e39163fde9b5a1c0650a00b523964e66829cea198f1fc194a86049cd3e'},
    100: {'aarch64-3.10': '5004031746e232e49e96991b8391b91cde5cd6fed2bf60d10612f6bbf23588cf',
          'armv7': '9eadc6d33601930f926286a11d43d1da02cf3b114ee6116c8aa0ba76da653545'},
}
WEB = 'opt/share/nfqws-asus-web/'


def read_payload(path, expected=None):
    raw = path.read_bytes()
    if expected and hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('Published package digest mismatch: ' + path.name)
    with tarfile.open(fileobj=io.BytesIO(raw)) as ipk:
        data = next(m for m in ipk if m.name.removeprefix('./') == 'data.tar.gz')
        inner = ipk.extractfile(data).read()
    with tarfile.open(fileobj=io.BytesIO(inner)) as members:
        return {m.name.removeprefix('./'): (members.extractfile(m).read(), m.mode)
                for m in members if m.isfile()}


def write(path, member):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw, mode = member
    path.write_bytes(raw)
    path.chmod(mode)


def install_settings(base, payload):
    # Model unpacked/seeded files relevant to the snapshot. Actual removal of
    # obsolete b100 opkg entries is exercised in test_b100_owned_list_upgrade.
    for name, member in payload.items():
        if name.startswith('opt/etc/nfqws2/') or name == 'opt/share/nfqws2-asus/report-baseline.json':
            write(base / name, member)
        if name.startswith('opt/share/nfqws2-asus/defaults/blobs/'):
            path = base / 'opt/etc/nfqws2/blobs' / Path(name).name
            if not path.exists():
                write(path, member)


class PublishedAsusUpdateHostlistTests(unittest.TestCase):
    def test_previous_updaters_accept_candidate_and_still_detect_changed_settings(self):
        inputs = ['ASUS_BUILD99_ARTIFACTS', 'ASUS_BUILD100_ARTIFACTS', 'ASUS_CANDIDATE_ARTIFACTS']
        if not all(os.environ.get(name) for name in inputs):
            self.skipTest('point the release check at published b99, b100 and candidate ASUS packages')
        old_dirs = {n: Path(os.environ[f'ASUS_BUILD{n}_ARTIFACTS']) for n in PUBLISHED}
        candidates = Path(os.environ['ASUS_CANDIDATE_ARTIFACTS'])
        script = """require $argv[1].'/update-prepare.php';$uid=(int)$argv[4];
        try {if($argv[5]==='capture')AsusUpdateSnapshot::capture($argv[2],$argv[3],$uid);
        else AsusUpdateSnapshot::verify($argv[2],$argv[3],$uid,true);echo 'ok';}
        catch(Throwable $e){echo $e->getMessage();}"""
        for abi in PUBLISHED[99]:
            candidate, = candidates.glob(f'nfqws2-asus_*_{abi}.ipk')
            incoming = read_payload(candidate)
            for build, digests in PUBLISHED.items():
                old_file = old_dirs[build] / f'nfqws2-asus_1.3.2-asus6+b{build}_{abi}.ipk'
                old = read_payload(old_file, digests[abi])
                with self.subTest(abi=abi, build=build), tempfile.TemporaryDirectory() as tmp:
                    base = Path(tmp)
                    worker = base / 'staged-worker'
                    for name, member in old.items():
                        if name.startswith(WEB) and name.endswith('.php'):
                            write(worker / name[len(WEB):], member)
                    def run(action):
                        result = subprocess.run([PHP, '-n', '-r', script, str(worker), str(base/'opt'),
                                                 str(base/'before'), str(os.getuid()), action],
                                                check=True, capture_output=True, text=True, timeout=20)
                        self.assertEqual(result.stderr, '')
                        return result.stdout
                    install_settings(base, old)
                    user_list = base / 'opt/etc/nfqws2/lists/user.list'
                    write(user_list, (b'owner.example\n', 0o640))
                    if build == 100:
                        saved = sorted(user_list.parent.glob('z2-pack-*.list.gz'))
                        self.assertEqual(len(saved), 5)
                        saved[0].write_bytes(b'owner-customized'); saved[1].unlink()
                    self.assertEqual(run('capture'), 'ok')
                    install_settings(base, incoming)
                    self.assertEqual(run('verify'), 'ok')
                    user_list.write_bytes(b'unexpected change\n')
                    self.assertEqual(run('verify'), 'settings_changed')

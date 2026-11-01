"""Relocated stock Merlin modes; production has no environment path overrides."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_auth_api import PHP

PUBLIC = Path(__file__).resolve().parents[1] / 'webui/web/public'


class RestartScheduleFirmwarePermissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.system_tmp = self.root / 'system-tmp'
        self.opt = self.system_tmp / 'mnt/Flashka/entware'
        self.config = self.opt / 'etc/nfqws2'; self.config.mkdir(parents=True)
        self.alias = self.root / 'opt'; self.alias.symlink_to(self.opt, target_is_directory=True)
        for path in [self.system_tmp, self.system_tmp / 'mnt', self.system_tmp / 'mnt/Flashka']:
            path.chmod(0o777)
        for path in [self.opt, self.opt / 'etc', self.config]: path.chmod(0o755)
        self.run = self.system_tmp / 'nfqws2-asus'; self.run.mkdir(mode=0o700)
        self.app = self.root / 'app'; shutil.copytree(PUBLIC, self.app)
        for name in ['platform.php', 'restart-schedule.php']:
            path = self.app / name; source = path.read_text()
            source = source.replace('/opt', str(self.alias)).replace('/tmp/nfqws2-asus', str(self.run))
            source = source.replace("'/tmp'", repr(str(self.system_tmp)))
            source = source.replace('substr($configured,4)', 'substr($configured,' + str(len(str(self.alias))) + ')')
            source = source.replace("['uid']!==0", "['uid']!==" + str(os.getuid()))
            path.write_text(source)

    def call(self, action='read', directory=None):
        script = '''require $argv[1].'/restart-schedule.php';try{
        $s=new NfqwsRestartSchedule($argv[3]===''?null:$argv[3],(int)$argv[4],fn()=>true);
        $v=$argv[2]==='read'?$s->read():$s->save(true,12,$argv[2]==='watchdog');
        echo json_encode(['value'=>$v]);}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        result = subprocess.run([PHP, '-n', '-r', script, str(self.app), action,
                                 '' if directory is None else str(directory), str(os.getuid())],
                                capture_output=True, text=True, timeout=3)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, '')
        return json.loads(result.stdout)

    def test_stock_777_mount_parents_allow_default_read_and_atomic_save(self):
        path = self.config / 'restart-schedule.conf'
        before = {p: p.stat().st_mode for p in [self.system_tmp, self.system_tmp / 'mnt', self.system_tmp / 'mnt/Flashka']}
        value = self.call(); self.assertIn('value', value, value)
        self.assertFalse(value['value']['enabled']); self.assertFalse(path.exists())
        value = self.call('save'); self.assertIn('value', value, value)
        self.assertTrue(value['value']['enabled']); self.assertEqual(value['value']['interval_hours'], 12)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.call()['value']['interval_hours'], 12)
        self.assertEqual({p: p.stat().st_mode for p in before}, before)

    def test_stock_777_tmp_allows_private_watchdog_status(self):
        value = self.call('watchdog'); self.assertIn('value', value, value)
        config = (self.config / 'restart-schedule.conf').read_text()
        revision = next(line.split('=', 1)[1] for line in config.splitlines() if line.startswith('watchdog_revision='))
        state = self.run / 'watchdog-state'; state.write_text(revision + ' 3 0 locked\n'); state.chmod(0o600)
        self.assertEqual(self.call()['value']['watchdog_state'], 'locked')
        self.assertEqual(self.call()['value']['watchdog_attempts'], 3)

    def test_unsafe_managed_ancestors_and_neighbor_mount_are_rejected(self):
        for path in [self.opt, self.opt / 'etc', self.config]:
            for mode in [0o777, 0o1777]:
                with self.subTest(path=path, mode=oct(mode)):
                    path.chmod(mode); self.assertEqual(self.call('save'), {'error': 'invalid_state'})
                    self.assertFalse((self.config / 'restart-schedule.conf').exists()); path.chmod(0o755)
        neighbor = self.opt.with_name('other-entware') / 'etc/nfqws2'; neighbor.mkdir(parents=True)
        self.assertEqual(self.call('save', neighbor), {'error': 'invalid_state'})
        self.assertEqual(list(neighbor.iterdir()), [])

    def test_runtime_directory_remains_private_even_with_sticky_bit(self):
        self.assertIn('value', self.call('watchdog'))
        for mode in [0o777, 0o1777]:
            with self.subTest(mode=oct(mode)):
                self.run.chmod(mode); self.assertEqual(self.call(), {'error': 'invalid_state'})
        self.run.chmod(0o700)

    def test_setting_links_and_writable_files_are_never_accepted(self):
        self.assertIn('value', self.call('save'))
        path = self.config / 'restart-schedule.conf'; outside = self.root / 'operator-data'
        outside.write_text('OWNER DATA'); outside.chmod(0o600)
        for kind in ['symlink', 'hardlink']:
            with self.subTest(kind=kind):
                path.unlink()
                if kind == 'symlink': path.symlink_to(outside)
                else: os.link(outside, path)
                self.assertEqual(self.call('save'), {'error': 'invalid_state'})
                self.assertEqual(outside.read_text(), 'OWNER DATA')

    def test_managed_directory_symlink_never_redirects_a_timer_write(self):
        outside = self.root / 'operator-directory'; outside.mkdir(mode=0o700)
        self.config.rmdir(); self.config.symlink_to(outside, target_is_directory=True)
        self.assertEqual(self.call('save'), {'error': 'invalid_state'})
        self.assertEqual(list(outside.iterdir()), [])

    def test_timer_and_watchdog_files_keep_private_modes_and_single_links(self):
        self.assertIn('value', self.call('watchdog'))
        config = self.config / 'restart-schedule.conf'
        revision = next(line.split('=', 1)[1] for line in config.read_text().splitlines() if line.startswith('watchdog_revision='))
        state = self.run / 'watchdog-state'; state.write_text(revision + ' 3 0 locked\n'); state.chmod(0o600)
        for path in [config, state]:
            for mode in [0o644, 0o666, 0o4600]:
                with self.subTest(path=path, mode=oct(mode)):
                    path.chmod(mode); self.assertEqual(self.call(), {'error': 'invalid_state'}); path.chmod(0o600)
        outside = self.root / 'operator-state'; outside.write_text('PRESERVE'); outside.chmod(0o600)
        for kind in ['symlink', 'hardlink']:
            with self.subTest(kind=kind):
                state.unlink()
                if kind == 'symlink': state.symlink_to(outside)
                else: os.link(outside, state)
                self.assertEqual(self.call(), {'error': 'invalid_state'})
                self.assertEqual(outside.read_text(), 'PRESERVE')


if __name__ == '__main__': unittest.main()

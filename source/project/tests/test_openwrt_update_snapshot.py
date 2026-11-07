"""Validate native settings identities without a complete backup or a router."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_dpi_normalize import ROOT
from test_package_update_guard import NATIVE


@unittest.skipUnless(NATIVE.is_file(), 'native PHP fixture required')
class NativeUpdateSnapshotTests(unittest.TestCase):
    def test_state_and_backup_verification_share_strict_live_settings_proof(self):
        result = subprocess.run(
            [str(NATIVE), '-n', '-f', str(ROOT / 'tests/test_openwrt_update_snapshot.php')],
            text=True, capture_output=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, '')
        self.assertIn('PASS:', result.stdout)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.base.chmod(0o700)
        self.system = self.base / 'system'
        self.system.mkdir(mode=0o700)

    def put(self, relative, data=b'profile resource'):
        path = self.system / relative
        path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        path.write_bytes(data)
        path.chmod(0o600)
        return path

    def invoke(self, operation, watched='etc/nfqws2/nfqws2.conf', module=None):
        code = '''require $argv[1]; $root=$argv[2];$backup=$argv[3];$owner=(int)$argv[4];$operation=$argv[5];
        try{
          if($operation==='reject'){
            $errors=[];foreach(['state','estimate','capture']as $method){try{
              if($method==='capture')NfqwsOpenWrtUpdateSnapshot::capture($backup,$root,$owner);
              else NfqwsOpenWrtUpdateSnapshot::$method($root,$owner);$errors[$method]='accepted';
            }catch(Throwable $e){$errors[$method]=$e->getMessage();}}
            echo json_encode(['errors'=>$errors,'backup_exists'=>file_exists($backup)]);exit;
          }
          $state=NfqwsOpenWrtUpdateSnapshot::state($root,$owner);
          if($operation==='identity-reject'){
            $template=reset($state['files']);$badFiles=['files'=>[],'bytes'=>0];
            for($i=0;$i<4097;$i++){$r=$template;$r['size']=0;$r['sha256']=hash('sha256','');$badFiles['files']['etc/nfqws2/lists/item-'.$i]=$r;}
            $badBytes=['files'=>[],'bytes'=>67108865];
            for($i=0;$i<5;$i++){$r=$template;$r['size']=$i===4?1:16777216;$badBytes['files']['etc/nfqws2/blobs/item-'.$i]=$r;}
            $errors=[];foreach(['files'=>$badFiles,'bytes'=>$badBytes]as $key=>$bad){try{
              NfqwsOpenWrtUpdateSnapshot::verifyState($bad,$root,$owner);$errors[$key]='accepted';
            }catch(Throwable $e){$errors[$key]=$e->getMessage();}}
            echo json_encode(['errors'=>$errors,'unchanged'=>$state===NfqwsOpenWrtUpdateSnapshot::state($root,$owner)]);exit;
          }
          $estimate=NfqwsOpenWrtUpdateSnapshot::estimate($root,$owner);
          if($operation==='estimate'){echo json_encode(['files'=>count($state['files']),'bytes'=>$estimate]);exit;}
          $before=$state;$original=file_get_contents($root.'/'.$argv[6]);
          $captured=NfqwsOpenWrtUpdateSnapshot::capture($backup,$root,$owner);
          $verified=NfqwsOpenWrtUpdateSnapshot::verify($backup,$root,$owner);
          $same=$before===NfqwsOpenWrtUpdateSnapshot::state($root,$owner)&&$captured===$before;
          $raw=file_get_contents($backup.'/native-snapshot.json');
          $cleanup=json_decode(file_get_contents($backup.'/snapshot.json'),true,32,JSON_THROW_ON_ERROR);
          file_put_contents($backup.'/native-snapshot.json',$raw.str_repeat(' ',2097153-strlen($raw)));
          try{NfqwsOpenWrtUpdateSnapshot::verify($backup,$root,$owner);$oversized='accepted';}catch(Throwable $e){$oversized=$e->getMessage();}
          file_put_contents($backup.'/native-snapshot.json',$raw);
          file_put_contents($backup.'/'.$argv[6],'corrupt copied data');
          try{NfqwsOpenWrtUpdateSnapshot::verify($backup,$root,$owner);$corrupt='accepted';}catch(Throwable $e){$corrupt=$e->getMessage();}
          $liveVerified=NfqwsOpenWrtUpdateSnapshot::verifyState($before,$root,$owner);
          $untouched=file_get_contents($root.'/'.$argv[6])===$original;
          file_put_contents($backup.'/'.$argv[6],$original);
          file_put_contents($root.'/'.$argv[6],'new owner contents');
          try{NfqwsOpenWrtUpdateSnapshot::verify($backup,$root,$owner);$changed='accepted';}catch(Throwable $e){$changed=$e->getMessage();}
          echo json_encode(['files'=>count($state['files']),'bytes'=>$estimate,'manifest_bytes'=>strlen($raw),
             'cleanup_files'=>count($cleanup['files']),'verified'=>$verified,'captured_same'=>$same,
             'corrupt'=>$corrupt,'oversized_manifest'=>$oversized,'live_verified'=>$liveVerified,'live_untouched'=>$untouched,
             'changed'=>$changed,'owner_contents'=>file_get_contents($root.'/'.$argv[6])]);
        }catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        result = subprocess.run(
            [str(NATIVE), '-n', '-r', code,
             str(module or ROOT / 'webui/web/public/openwrt-update-snapshot.php'),
             str(self.system), str(self.base / 'backup'), str(os.getuid()), operation, watched],
            capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, '')
        return json.loads(result.stdout)

    def assert_roundtrip(self, result, files):
        self.assertNotIn('error', result)
        self.assertEqual(result['files'], files)
        self.assertEqual(result['cleanup_files'], files + 1)
        for field in ['verified', 'captured_same', 'live_verified', 'live_untouched']:
            self.assertTrue(result[field], field)
        self.assertEqual(result['corrupt'], 'invalid_state')
        self.assertEqual(result['oversized_manifest'], 'invalid_state')
        self.assertEqual(result['changed'], 'settings_changed')
        self.assertEqual(result['owner_contents'], 'new owner contents')

    def test_four_saved_strategy_resource_sets_survive_native_capture_and_verification(self):
        self.put('etc/nfqws2/nfqws2.conf', b'owner config')
        for strategy in range(4):
            for resource in range(128):
                self.put(f'etc/nfqws2/device-profiles/saved-{strategy:016x}/lists/resource-{resource:03d}.list')
        self.assert_roundtrip(self.invoke('roundtrip'), 513)

    def test_eight_full_saved_strategies_and_stock_exceed_old_2048_limit(self):
        self.put('etc/nfqws2/nfqws2.conf', b'owner config')
        for strategy in range(8):
            for resource in range(256):
                self.put(f'etc/nfqws2/device-profiles/saved-{strategy:016x}/lists/resource-{resource:03d}.list')
        for resource in range(128):
            self.put(f'etc/nfqws2/device-profiles/stock/lists/resource-{resource:03d}.list')
        # Reproduce the rejected beta library with the former limit in an
        # isolated dependency copy; production files stay untouched.
        public = ROOT / 'webui/web/public'
        previous = self.base / 'previous-limit'
        previous.mkdir(mode=0o700)
        for source in public.glob('*.php'):
            shutil.copyfile(source, previous / source.name)
        limits = previous / 'update-snapshot-limits.php'
        limits.write_text(limits.read_text().replace('FILES=4096', 'FILES=2048'))
        self.assertEqual(self.invoke('estimate', module=previous / 'openwrt-update-snapshot.php'),
                         {'error': 'output_limit'})
        self.assert_roundtrip(self.invoke('roundtrip'), 2177)

    def test_long_resource_names_allow_a_manifest_larger_than_150_kilobytes(self):
        self.put('etc/nfqws2/nfqws2.conf', b'owner config')
        for resource in range(483):
            name = f'resource-{resource:03d}-' + 'x' * 100 + '.list'
            self.put('etc/nfqws2/device-profiles/saved-0000000000000001/lists/' + name)
        result = self.invoke('roundtrip')
        self.assert_roundtrip(result, 484)
        self.assertGreater(result['manifest_bytes'], 150000)

    def test_native_file_limit_accepts_4096_and_refuses_the_next_before_backup_creation(self):
        watched = 'etc/nfqws2/lists/resource-0000.list'
        for resource in range(4096):
            self.put(f'etc/nfqws2/lists/resource-{resource:04d}.list', b'')
        result = self.invoke('roundtrip', watched)
        self.assert_roundtrip(result, 4096)
        shutil.rmtree(self.base / 'backup')
        self.put('etc/nfqws2/lists/resource-4096.list', b'')
        self.assertEqual(self.invoke('reject'), {'errors': {'state': 'output_limit', 'estimate': 'output_limit',
                                                          'capture': 'output_limit'}, 'backup_exists': False})

    def test_native_byte_limit_accepts_64_mib_and_refuses_overflow_before_copying(self):
        for resource in range(4):
            path = self.put(f'etc/nfqws2/blobs/resource-{resource}.bin', b'')
            with path.open('r+b') as stream:
                stream.truncate(16777216)
        self.assertEqual(self.invoke('estimate'), {'files': 4, 'bytes': 67108864})
        self.put('etc/nfqws2/lists/overflow.list', b'x')
        self.assertEqual(self.invoke('reject'), {'errors': {'state': 'output_limit', 'estimate': 'output_limit',
                                                          'capture': 'output_limit'}, 'backup_exists': False})

    def test_native_json_limit_refuses_large_link_identity_before_backup_creation(self):
        directory = self.system / 'etc/nfqws2'
        directory.mkdir(parents=True, mode=0o700)
        for resource in range(1024):
            (directory / f'link-{resource:04d}').symlink_to('x' * 2048)
        self.assertEqual(self.invoke('reject'), {'errors': {'state': 'output_limit', 'estimate': 'output_limit',
                                                          'capture': 'output_limit'}, 'backup_exists': False})

    def test_protected_identity_rejects_file_and_byte_overflow_without_changing_settings(self):
        self.put('etc/nfqws2/nfqws2.conf', b'owner config')
        self.assertEqual(self.invoke('identity-reject'), {'errors': {'files': 'invalid_state', 'bytes': 'invalid_state'},
                                                        'unchanged': True})

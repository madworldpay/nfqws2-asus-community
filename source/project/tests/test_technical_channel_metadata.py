"""UID0 metadata is session bound, nonsecret, and removed only by its owner."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import test_technical_channel as technical


@unittest.skipUnless(technical.PHP, 'native PHP fixture required')
class TechnicalMetadataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.root.chmod(0o700)
        self.config = dict(runtime=str(self.root), journal=str(self.root/'journal.json'), owner=os.getuid())
        self.state = dict(state='connecting', session_id='b'*32, activation_id='a'*32, expires_at=2000000000)

    def call(self, code, **values):
        script = "require $argv[1].'/technical-channel.php';$v=json_decode(stream_get_contents(STDIN),true);$s=$v['state'];$c=new AsusTechnicalChannel($v['config']);try{"+code+"}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}"
        result = subprocess.run([technical.PHP, '-n', '-r', script, str(technical.PUBLIC)],
                                input=json.dumps(dict(config=self.config, state=self.state, **values)), text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        return json.loads(result.stdout)

    def prepare(self, login='owner_123'):
        return self.call("$m=new ReflectionMethod($c,'prepareBanner');$m->invokeArgs($c,[&$s,$v['login']]);echo json_encode(['ok'=>$s]);", login=login)

    def test_banner_publishes_only_version_signed_session_and_uid0_login(self):
        result = self.prepare()
        self.assertIn('ok', result, result)
        path = self.root/('operator-banner.'+'a'*32)
        self.assertEqual(path.read_text(), 'NFQWS2-TECH-META/1 '+'b'*32+' owner_123\n')
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads((self.root/'state.json').read_text()), result['ok'])

    def test_metadata_rejects_login_or_session_injection_before_writing(self):
        for login in ['', 'owner\nroot', 'root;id', '-oProxyCommand=id', 'a'*33]:
            with self.subTest(login=login):
                self.assertEqual(self.prepare(login), dict(error='invalid_state'))
                self.assertEqual(list(self.root.iterdir()), [])
        self.state['session_id'] = 'b'*32+'\n'
        self.assertEqual(self.prepare(), dict(error='invalid_state'))
        self.assertEqual(list(self.root.iterdir()), [])

    def test_preexisting_banner_is_preserved(self):
        path = self.root/('operator-banner.'+'a'*32)
        path.write_text('OWNER FILE')
        path.chmod(0o600)
        self.assertIn('error', self.prepare())
        self.assertEqual(path.read_text(), 'OWNER FILE')

    def test_stop_removes_only_owned_metadata(self):
        prepared = self.prepare()
        self.assertIn('ok', prepared, prepared)
        self.state = prepared['ok']
        result = self.call("$m=new ReflectionMethod($c,'clean');$out=$m->invoke($c,$s,'stopped');echo json_encode(['ok'=>$out]);")
        self.assertEqual(result['ok']['state'], 'stopped')
        self.assertFalse((self.root/('operator-banner.'+'a'*32)).exists())

    def test_replaced_banner_is_preserved_during_cleanup(self):
        prepared = self.prepare()
        self.assertIn('ok', prepared, prepared)
        self.state = prepared['ok']
        path = self.root/('operator-banner.'+'a'*32)
        with path.open('rb'):
            path.unlink()
            path.write_text('OWNER REPLACEMENT')
            path.chmod(0o600)
            result = self.call("$m=new ReflectionMethod($c,'clean');$out=$m->invoke($c,$s,'stopped');echo json_encode(['ok'=>$out]);")
        self.assertEqual(result, dict(error='unsafe_key_file'))
        self.assertEqual(path.read_text(), 'OWNER REPLACEMENT')

    def test_symlink_or_inplace_edit_is_preserved_during_cleanup(self):
        prepared = self.prepare()
        self.assertIn('ok', prepared, prepared)
        self.state = prepared['ok']
        path = self.root/('operator-banner.'+'a'*32)
        path.write_text('OWNER INPLACE EDIT')
        result = self.call("$m=new ReflectionMethod($c,'clean');$out=$m->invoke($c,$s,'stopped');echo json_encode(['ok'=>$out]);")
        self.assertEqual(result, dict(error='unsafe_key_file'))
        self.assertEqual(path.read_text(), 'OWNER INPLACE EDIT')
        path.unlink()
        target = self.root/'owner'
        target.write_text('OWNER TARGET')
        path.symlink_to(target)
        result = self.call("$m=new ReflectionMethod($c,'clean');$out=$m->invoke($c,$s,'stopped');echo json_encode(['ok'=>$out]);")
        self.assertEqual(result, dict(error='unsafe_key_file'))
        self.assertTrue(path.is_symlink())
        self.assertEqual(target.read_text(), 'OWNER TARGET')


if __name__ == '__main__':
    unittest.main()

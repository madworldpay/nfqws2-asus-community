"""A DNS update repairs only verified writable data and keeps its exact originals."""
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest

from test_dpi_normalize import PHP, PUBLIC


class SmartDnsPermissionRepairTests(unittest.TestCase):
    policy = 'filter-AAAA\nipset=/video.example/awg_dst\nno-resolv\nserver=1.1.1.1@awg0\n'

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, body, mode):
        path = self.root / name
        path.write_text(body)
        path.chmod(mode)
        return path

    def php(self, body, text):
        script = "require $argv[1].'/smartdns-config.php';$text=$argv[2];$owner=(int)$argv[3];" + body
        result = subprocess.run(
            [PHP, '-n', '-r', script, str(PUBLIC), text, str(os.getuid()), str(self.root)],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, '')
        return json.loads(result.stdout)

    def test_nested_graph_backed_up_in_one_batch_and_repaired_in_place(self):
        first = self.write('awg.conf', self.policy, 0o666)
        second = self.write('split.conf', 'server=1.0.0.1@awg0\n', 0o660)
        private = self.write('private.conf', 'address=/office.example/192.0.2.1\n', 0o600)
        nested = self.write('nested.conf', f'conf-file="{second}" # DNS policy\nconf-file={private}\n', 0o600)
        original = {str(p): (p.read_bytes(), p.stat()) for p in (first, second, private, nested)}
        body = """
        $before=AsusSmartDnsConfig::collect($text,$owner,true);
        $strict=null;
        try{AsusSmartDnsConfig::collect($text,$owner);}catch(Throwable $e){$strict=$e->getMessage();}
        $backups=[];$savedModes=[];
        $backup=function(array $batch)use(&$backups,&$savedModes):void{
            $backups[]=$batch;
            foreach(array_keys($batch)as $path)$savedModes[$path]=fileperms($path)&07777;
        };
        AsusSmartDnsConfig::repair($text,$backup,$owner,$before);
        AsusSmartDnsConfig::repair($text,$backup,$owner);
        $after=AsusSmartDnsConfig::collect($text,$owner,true);
        echo json_encode([$strict,$before,$after,$backups,$savedModes]);
        """
        strict, before, after, batches, modes = self.php(body, f'conf-file={first}\nconf-file={nested}')
        self.assertEqual(strict, 'existing_dns_rules')
        self.assertEqual(before['fingerprints'], after['fingerprints'])
        self.assertEqual(before['text'], after['text'])
        self.assertFalse(after['repairable'])
        self.assertEqual(len(batches), 1)
        self.assertEqual(modes, {str(first): 0o666, str(second): 0o660})
        self.assertEqual(batches[0], before['repairable'])
        self.assertEqual(batches[0][str(first)]['value'], self.policy)
        expected = {first: 0o644, second: 0o640, private: 0o600, nested: 0o600}
        for path, mode in expected.items():
            old_bytes, old = original[str(path)]
            new = path.stat()
            self.assertEqual(path.read_bytes(), old_bytes)
            self.assertEqual((new.st_dev, new.st_ino, new.st_uid, new.st_gid, new.st_mtime_ns),
                             (old.st_dev, old.st_ino, old.st_uid, old.st_gid, old.st_mtime_ns))
            self.assertEqual(stat.S_IMODE(new.st_mode), mode)

    def test_untrusted_includes_links_and_writable_directories_are_refused(self):
        victim = self.write('victim.conf', self.policy, 0o666)
        symlink = self.root / 'symlink.conf'
        symlink.symlink_to(victim)
        hardlink = self.root / 'hardlink.conf'
        os.link(victim, hardlink)
        invalid = [
            self.write('dynamic.conf', f'conf-file={victim}\n', 0o666),
            self.write('script.conf', 'dhcp-script=/bin/sh\n', 0o666),
            self.write('executable.conf', self.policy, 0o777),
            symlink,
            hardlink,
        ]
        parent = self.root / 'unprotected'
        parent.mkdir()
        parent.chmod(0o777)
        redirected = parent / 'data.conf'
        redirected.write_text(self.policy)
        redirected.chmod(0o666)
        invalid.append(redirected)
        body = """
        $backup=static function(){throw new LogicException('unexpected backup');};
        try{AsusSmartDnsConfig::repair($text,$backup,$owner);echo 'null';}
        catch(RuntimeException $e){echo json_encode($e->getMessage());}
        """
        for path in invalid:
            with self.subTest(path=path.name):
                self.assertEqual(self.php(body, f'conf-file={path}\n'), 'existing_dns_rules')
        self.assertEqual(stat.S_IMODE(victim.stat().st_mode), 0o666)
        self.assertEqual(stat.S_IMODE(redirected.stat().st_mode), 0o666)

    def test_replacement_after_backup_refuses_the_entire_batch_before_chmod(self):
        first = self.write('first.conf', self.policy, 0o666)
        second = self.write('second.conf', self.policy, 0o666)
        replacement = self.write('replacement.conf', self.policy, 0o666)
        original_inode = second.stat().st_ino
        body = """
        $backup=function(array $batch)use($argv):void{
            rename($argv[4].'/second.conf',$argv[4].'/original.conf');
            rename($argv[4].'/replacement.conf',$argv[4].'/second.conf');
        };
        try{AsusSmartDnsConfig::repair($text,$backup,$owner);echo 'null';}
        catch(RuntimeException $e){echo json_encode($e->getMessage());}
        """
        self.assertEqual(self.php(body, f'conf-file={first}\nconf-file={second}'), 'stale_baseline')
        original = self.root / 'original.conf'
        self.assertEqual(original.stat().st_ino, original_inode)
        self.assertFalse(replacement.exists())
        for path in (first, second, original):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o666)

    def test_historical_proof_repairs_a_mode_change_and_refuses_replacement(self):
        path = self.write('awg.conf', self.policy, 0o644)
        replacement = self.write('other.conf', self.policy, 0o666)
        body = """
        $proof=AsusSmartDnsConfig::collect($text,$owner)['fingerprints'];
        $path=array_key_first($proof);
        chmod($path,0666);
        $count=0;
        $backup=function(array $batch)use(&$count):void{$count+=count($batch);};
        AsusSmartDnsConfig::repairKnown($proof,$backup,$owner);
        clearstatcache(true,$path);$mode=fileperms($path)&07777;
        rename($path,$argv[4].'/kept.conf');
        rename($argv[4].'/other.conf',$path);
        $failure=null;
        try{AsusSmartDnsConfig::repairKnown($proof,$backup,$owner);}
        catch(RuntimeException $e){$failure=$e->getMessage();}
        echo json_encode([$count,$mode,$failure]);
        """
        self.assertEqual(self.php(body, f'conf-file={path}'), [1, 0o644, 'stale_baseline'])
        self.assertFalse(replacement.exists())
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o666)

    def test_backup_failure_preserves_permissions(self):
        path = self.write('awg.conf', self.policy, 0o666)
        body = """
        $backup=static function(){throw new RuntimeException('storage_unavailable');};
        try{AsusSmartDnsConfig::repair($text,$backup,$owner);echo 'null';}
        catch(RuntimeException $e){echo json_encode($e->getMessage());}
        """
        self.assertEqual(self.php(body, f'conf-file={path}'), 'storage_unavailable')
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o666)


if __name__ == '__main__':
    unittest.main()

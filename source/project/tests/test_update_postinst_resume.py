"""Only the transaction worker may resume SmartDNS after package verification."""
from pathlib import Path
import subprocess
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parents[1]

class PostinstResumeTests(unittest.TestCase):
    def run_hook(self, transaction):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            log = root/'commands'
            for name in ('etc/init.d/S81nfqws-asus-web', 'etc/init.d/S51nfqws2', 'lib/nfqws2-asus/smartdns/control.sh'):
                path = root/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('#!/bin/sh\nprintf "%s %s\\n" "'+path.name+'" "$1" >> "'+str(log)+'"\n')
                path.chmod(0o755)
            lifecycle = root/'lib/nfqws2-asus/update/lifecycle.sh'
            lifecycle.parent.mkdir(parents=True)
            lifecycle.write_text('asus_update_transaction() { return '+('0' if transaction else '1')+'; }\n')
            source = (PROJECT/'asus/ipk/unified-postinst').read_text().replace('/opt/', str(root)+'/')
            wrapper = '\n'.join(name+'() { :; }' for name in ('asus_migration_restore','asus_install_defaults','asus_install_blob_defaults','asus_migration_complete'))+'\n'
            result = subprocess.run(['/bin/sh'], input=wrapper+source, text=True, capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            return log.read_text().splitlines() if log.exists() else []
    def test_transaction_defers_resume_until_worker_verifies_final_package(self):
        commands = self.run_hook(True)
        self.assertFalse(any('queue-resume' in command for command in commands), commands)
        self.assertFalse(any('S51nfqws2 start' in command for command in commands), commands)
        self.assertFalse(any('S81nfqws-asus-web start' in command for command in commands), commands)
    def test_regular_install_keeps_normal_resume(self):
        commands = self.run_hook(False)
        self.assertIn('control.sh queue-resume', commands)
        self.assertIn('S51nfqws2 start', commands)

if __name__ == '__main__': unittest.main()

"""Recovery metadata is data: unknown keys and shell text never become code."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_dpi_normalize import ROOT

SOURCE=ROOT/'asus/smartdns/native-state.sh'


class SmartDnsNativeStateTests(unittest.TestCase):
    def state(self,**patch):
        v=dict(schema='1',request_id='b'*32,boot_id='12345678-1234-1234-1234-123456789abc',
               phase='prepared',deadline='0.000',guard_pid='0',guard_ticks='0',runtime_pid='0',
               runtime_ticks='0',runtime_exe='',hook_created='0',profile_hash='a'*64)
        v.update(patch);return ''.join(k+'\t'+value+'\n' for k,value in v.items()).encode()

    def run_state(self,body,write=False):
        if not SOURCE.is_file():return 2,b'missing_native_state'
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'state').write_bytes(body);(root/'state').chmod(0o600)
            lib=root/'native-state.sh';lib.write_text(SOURCE.read_text().replace('/jffs/nfqws2-asus-smartdns',str(root)))
            command='. "$1"; sd_state_load || exit 2; '
            if write:command+='sd_phase=rolled_back; sd_state_save || exit 3; sd_state_load || exit 4; '
            command+='printf "%s|%s" "$sd_request_id" "$sd_phase"'
            r=subprocess.run(['/bin/sh','-c',command,'fixture',str(lib)],cwd=root,capture_output=True,timeout=4)
            self.assertEqual(r.stderr,b'');self.assertFalse((root/'EXECUTED').exists())
            if write and r.returncode==0:self.assertEqual((root/'state').stat().st_mode&0o777,0o600)
            return r.returncode,r.stdout

    def test_valid_metadata_can_be_loaded_and_atomically_rewritten(self):
        rc,out=self.run_state(self.state(),True);self.assertEqual(rc,0);self.assertEqual(out,('b'*32+'|rolled_back').encode())

    def test_unknown_duplicate_partial_binary_and_oversize_records_are_rejected(self):
        for body in [self.state()+b'PATH\t/tmp\n',self.state()+b'phase\tconfirmed\n',self.state()[:-1],
                     self.state()+b'\0',self.state()+b'x'*16385,self.state(schema='2')]:
            with self.subTest(body=body[:50]):self.assertNotEqual(self.run_state(body)[0],0)

    def test_invalid_id_pid_hash_phase_or_deadline_is_rejected(self):
        for patch in [dict(request_id='../outside'),dict(phase='run_command'),dict(deadline='1e9'),
                      dict(deadline='1.2.3'),dict(guard_pid='-1'),dict(runtime_pid='9999999999'),dict(profile_hash='x'*64),
                      dict(phase='awaiting_confirmation')]:
            with self.subTest(patch=patch):self.assertNotEqual(self.run_state(self.state(**patch))[0],0)

    def test_runtime_executable_is_only_compared_as_literal_metadata(self):
        # A path containing shell metacharacters is never sourced or executed.
        rc,_=self.run_state(self.state(runtime_pid='123',runtime_ticks='456',runtime_exe='/tmp/$(touch EXECUTED)'))
        self.assertEqual(rc,0)


if __name__=='__main__':unittest.main()

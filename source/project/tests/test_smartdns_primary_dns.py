"""Identify the native primary daemon, excluding its TCP child processes."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_dpi_normalize import ROOT

SOURCE=ROOT/'asus/smartdns/primary-dns.sh'


class SmartDnsPrimaryTests(unittest.TestCase):
    def exercise(self,args=None,mode='ready'):
        self.assertTrue(SOURCE.is_file(),'missing_primary_dns_proof')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);binary=root/'dnsmasq';code=root/'dnsmasq.c'
            code.write_text('#include <unistd.h>\n#include <stdlib.h>\nint main(void){if(getenv("FORK_FIXTURE"))fork();for(;;)sleep(1);}\n')
            subprocess.run(['gcc',str(code),'-o',str(binary)],capture_output=True,check=True)
            config=root/'dnsmasq.conf';config.write_text('server=9.9.9.9\n')
            default=root/'default.conf'
            if mode!='wrong_default':default.symlink_to(config)
            script=root/'primary-dns.sh';script.write_text(SOURCE.read_text().replace('/usr/sbin/dnsmasq',str(binary)).replace('/tmp/etc/dnsmasq.conf',str(config)).replace('/etc/dnsmasq.conf',str(default)))
            values=[a.replace('CONFIG',str(config)) for a in (args or ['--log-async'])]
            env=os.environ|({'FORK_FIXTURE':'1'} if mode=='tcp_child' else {})
            p=subprocess.Popen([str(binary),*values],env=env,start_new_session=True)
            other=None
            try:
                if mode=='ambiguous':other=subprocess.Popen([str(binary),*values],start_new_session=True)
                # PID names/argv can briefly still belong to the forking Python.
                import time
                for _ in range(100):
                    if Path(f'/proc/{p.pid}/comm').read_text().strip()=='dnsmasq':break
                    time.sleep(.005)
                if other:
                    for _ in range(100):
                        if Path(f'/proc/{other.pid}/comm').read_text().strip()=='dnsmasq':break
                        time.sleep(.005)
                if mode=='tcp_child':
                    for _ in range(100):
                        if Path(f'/proc/{p.pid}/task/{p.pid}/children').read_text().strip():break
                        time.sleep(.005)
                    self.assertTrue(Path(f'/proc/{p.pid}/task/{p.pid}/children').read_text().strip())
                r=subprocess.run(['/bin/sh',str(script),'identity'],capture_output=True,text=True,timeout=3)
                self.assertEqual(r.stderr,'')
                if mode in ['ready','tcp_child']:
                    ticks=Path(f'/proc/{p.pid}/stat').read_text().rsplit(') ',1)[1].split()[19]
                    self.assertEqual(r.returncode,0);self.assertEqual(r.stdout,f'{p.pid} {ticks}\n')
                else:self.assertNotEqual(r.returncode,0)
            finally:
                for process in [p,other]:
                    if process:
                        os.killpg(process.pid,15);process.wait()

    def test_native_default_and_explicit_primary_config_are_identified(self):
        self.exercise();self.exercise(['-C','CONFIG']);self.exercise(['--conf-file=CONFIG'])

    def test_other_config_cli_dns_override_or_missing_default_is_unverified(self):
        self.exercise(['-C','/unknown'],mode='unknown')
        self.exercise(['--server=9.9.9.9'],mode='unknown')
        self.exercise(mode='wrong_default')

    def test_tcp_child_is_not_another_primary_but_two_roots_are_ambiguous(self):
        self.exercise(mode='tcp_child');self.exercise(mode='ambiguous')


if __name__=='__main__':unittest.main()

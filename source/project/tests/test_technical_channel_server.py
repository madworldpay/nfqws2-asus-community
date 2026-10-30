"""Exercise temporary-account policy through OpenSSH's real effective config."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('technical_server',ROOT/'technical-channel/server.py')
server=importlib.util.module_from_spec(spec);spec.loader.exec_module(server)

@unittest.skipUnless(shutil.which('sshd') and shutil.which('ssh-keygen'),'OpenSSH tools required')
class TechnicalServerTests(unittest.TestCase):
    def provision(self, missing=None):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);hostkey=root/'hostkey'
            subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(hostkey)],check=True)
            conf=root/'sshd_config';written=[];effective=[]
            original_write=server.write
            def write(path,raw,mode=0o600):
                if str(path).startswith('/etc/systemd/'):
                    path=root/path.name
                written.append(path)
                original_write(path,raw,mode)
            def run(*args):
                if args[0]=='ss':return ''
                if args[0]=='/usr/sbin/sshd':
                    command=['/usr/sbin/sshd',args[1],'-f',str(conf),'-h',str(hostkey),*args[2:]]
                    output=subprocess.run(command,check=True,text=True,capture_output=True).stdout
                    if args[1]=='-T':
                        effective.extend(output.splitlines())
                        if missing:output='\n'.join(line for line in output.splitlines() if line!=missing)
                    return output
                return ''
            user='nfqs-aaaaaaaaaaaa';sid='a'*32
            with patch.object(server,'BASE',root/'records'),patch.object(server,'KEYS',root/'keys'),patch.object(server,'paths',return_value=(user,'test-channel',conf)),patch.object(server,'write',side_effect=write),patch.object(server,'run',side_effect=run),patch.object(server.pwd,'getpwnam',side_effect=[KeyError(),SimpleNamespace(pw_uid=os.getuid())]),patch.object(server,'revoke') as revoke:
                try:result=server.provision(dict(session_id=sid,remote_port=44900,expires_at=int(time.time())+300,client_key='ssh-ed25519 '+'A'*68))
                except ValueError:
                    if missing:
                        self.assertTrue(revoke.called);return
                    raise
            self.assertIsNone(missing,'provision accepted incomplete effective policy')
            self.assertTrue(result['policy_verified'])
            for line in ['clientaliveinterval 15','clientalivecountmax 2','maxsessions 0','allowtcpforwarding remote','permitlisten 127.0.0.1:44900','permitopen none','gatewayports no','passwordauthentication no','permittty no']:
                self.assertIn(line,effective)
            # Match all must end the per-account restrictions.
            ordinary=subprocess.run(['/usr/sbin/sshd','-T','-f',str(conf),'-h',str(hostkey),'-C','user=ordinary,host=localhost,addr=127.0.0.1'],check=True,text=True,capture_output=True).stdout.splitlines()
            self.assertIn('clientaliveinterval 0',ordinary)
    def test_effective_keepalives_and_restrictions_are_scoped_to_account(self):self.provision()
    def test_provision_rejects_missing_effective_keepalive(self):self.provision('clientalivecountmax 2')

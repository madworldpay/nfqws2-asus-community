import configparser
import json
import os
from unittest.mock import patch
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / 'support-relay/deploy'
sys.path.insert(0, str(ROOT / 'support-relay/src'))
from nfqws_support.config import load_credentials


class DeploymentTests(unittest.TestCase):
    def test_only_fixed_regular_private_credential_is_loaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'relay-config'
            value = {'username':'sender@example.invalid','sender':'sender@example.invalid',
                     'recipient':'support@example.invalid','password':'a'*16,'hmac_key':'1'*64}
            path.write_text(json.dumps(value)); path.chmod(0o600)
            self.assertEqual(load_credentials(tmp).port, 465)
            path.chmod(0o644)
            with self.assertRaisesRegex(ValueError,'^invalid_config$'): load_credentials(tmp)
            path.chmod(0o600); path.rename(Path(tmp)/'other'); path.symlink_to('other')
            with self.assertRaisesRegex(ValueError,'^invalid_config$'): load_credentials(tmp)

    def test_systemd_acl_credential_is_accepted_only_for_root_or_service_gid(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'relay-config'
            value={'username':'sender@example.invalid','sender':'sender@example.invalid',
                   'recipient':'support@example.invalid','password':'a'*16,'hmac_key':'1'*64}
            path.write_text(json.dumps(value));path.chmod(0o440)
            actual=os.stat(path)
            def metadata(uid,gid,mode=0o440):
                fields=list(actual);fields[0]=(actual.st_mode & ~0o777)|mode;fields[4]=uid;fields[5]=gid
                return os.stat_result(fields)
            for gid in (0,987):
                with self.subTest(gid=gid),patch('os.getegid',return_value=987),patch('os.fstat',return_value=metadata(0,gid)):
                    self.assertEqual(load_credentials(tmp).port,465)
            for meta in (metadata(0,988),metadata(1000,987),metadata(0,987,0o444),metadata(0,987,0o460)):
                with self.subTest(meta=meta),patch('os.getegid',return_value=987),patch('os.fstat',return_value=meta):
                    with self.assertRaisesRegex(ValueError,'^invalid_config$'):load_credentials(tmp)

    def test_header_injection_unknown_field_and_bad_port_are_safe_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'relay-config'
            base = {'username':'sender@example.invalid','sender':'sender@example.invalid',
                    'recipient':'support@example.invalid','password':'a'*16,'hmac_key':'1'*64}
            for key, value in [('recipient','PRIVATE_CANARY\r\nBcc: x@example.invalid'),
                               ('url','PRIVATE_CANARY'), ('port',25), ('source_limit',True)]:
                path.write_text(json.dumps(base|{key:value})); path.chmod(0o600)
                with self.assertRaisesRegex(ValueError,'^invalid_config$'): load_credentials(tmp)

    def test_units_validate_and_constrain_write_paths_and_network_listener(self):
        source = DEPLOY/'nfqws-support.service'
        unit = configparser.ConfigParser(interpolation=None,strict=False)
        unit.optionxform = str
        unit.read_string(source.read_text())
        cfg = unit['Service']
        # These operator-facing settings determine the sandbox and listener.
        for key,want in [('User','nfqws-support'),('PrivateTmp','yes'),('ProtectSystem','strict'),
                         ('ProtectHome','yes'),('NoNewPrivileges','yes'),('MemoryMax','128M'),
                         ('UMask','0077'),('ReadWritePaths','/var/lib/nfqws-support')]:
            self.assertEqual(cfg[key],want)
        self.assertTrue(cfg['LoadCredentialEncrypted'].startswith('relay-config:'))
        command = cfg['ExecStart'].split()
        self.assertEqual(command[command.index('--bind')+1],'127.0.0.1:8875')
        self.assertEqual(command[command.index('--workers')+1],'2')
        self.assertEqual(command[command.index('--worker-class')+1],'sync')
        self.assertEqual(command[command.index('--timeout')+1],'25')
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/source.name
            target.write_text(source.read_text().replace(cfg['ExecStart'],'/bin/true').replace('WorkingDirectory=/usr/local/lib/nfqws-support','WorkingDirectory=/tmp'))
            result=subprocess.run(['systemd-analyze','verify',str(target)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
        cleanup = DEPLOY/'nfqws-support-cleanup.service'
        timer = DEPLOY/'nfqws-support-cleanup.timer'
        self.assertTrue(cleanup.is_file())
        self.assertTrue(timer.is_file())

    def test_renewal_hook_validates_before_reloading_only_nginx(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name in ['nginx','systemctl']:
                p=root/name
                p.write_text('#!/bin/sh\necho "'+name+' $*" >> "$TEST_CALLS"\n'+('exit "${NGINX_STATUS:-0}"\n' if name=='nginx' else ''))
                p.chmod(0o700)
            calls=root/'calls'
            env=os.environ|{'PATH':tmp+':'+os.environ['PATH'],'TEST_CALLS':str(calls)}
            subprocess.run(['sh',str(DEPLOY/'renew-nginx.sh')],env=env,check=True)
            self.assertEqual(calls.read_text().splitlines(),['nginx -t','systemctl reload nginx'])
            calls.unlink()
            result=subprocess.run(['sh',str(DEPLOY/'renew-nginx.sh')],env=env|{'NGINX_STATUS':'1'})
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(calls.read_text().splitlines(),['nginx -t'])

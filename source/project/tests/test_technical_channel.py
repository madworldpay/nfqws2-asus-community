"""Signed temporary support links and exact, crash-safe public-key rollback."""
import base64
import json
import os
import shutil
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding, ed25519

ROOT = Path(__file__).resolve().parents[1]
PHP = os.environ.get('PHP_NATIVE_TEST_BINARY') or shutil.which('php')
PUBLIC = ROOT / 'webui/web/public'


def b64(v):
    return base64.urlsafe_b64encode(v).decode().rstrip('=')


@unittest.skipUnless(PHP, 'native PHP interpreter required')
class TechnicalChannelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.pem = cls.key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        cls.pub = ed25519.Ed25519PrivateKey.generate().public_key().public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH).decode()

    def php(self, script, data):
        call = "$v=json_decode(stream_get_contents(STDIN),true); require $argv[1].'/technical-channel.php'; try { $r=(function($v){" + script + "})($v); echo json_encode(['ok'=>$r]); } catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}"
        r = subprocess.run([PHP, '-n', '-r', call, str(PUBLIC)], input=json.dumps(data), text=True, capture_output=True, timeout=10)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr, '')
        return json.loads(r.stdout)

    def payload(self):
        now = int(time.time())
        # Actual Dropbear Ed25519 secret-key wire format, only a tunnel credential.
        priv = ed25519.Ed25519PrivateKey.generate()
        seed = priv.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
        pub = priv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        dbkey = b'\0\0\0\x0bssh-ed25519\0\0\0\x40' + seed + pub
        return dict(schema_version=1, purpose='technical_channel', session_id='a'*32,
                    issued_at=now-1, expires_at=now+600, server='94.103.80.201', server_port=22,
                    server_user='nfqs-'+('a'*12), remote_port=44900,
                    host_key=self.pub, operator_key=self.pub, tunnel_key=base64.b64encode(dbkey).decode())

    def link(self, data=None, raw=None):
        raw = raw if raw is not None else json.dumps(data or self.payload(), separators=(',', ':')).encode()
        sig = self.key.sign(raw, padding.PKCS1v15(), hashes.SHA256())
        return 'https://github.com/madworldpay/nfqws2-asus-community#technical-channel=v1.'+b64(raw)+'.'+b64(sig)

    def verify(self, link):
        return self.php("return AsusTechnicalInvite::verify($v['link'],$v['pem'],time());",dict(link=link,pem=self.pem))

    def test_valid_offline_link_and_migration(self):
        data=self.payload()
        self.assertEqual(self.verify(self.link(data))['ok'],data)
        data['server']='1.1.1.1'; data['server_port']=2200; data['host_key']=self.pub
        self.assertEqual(self.verify(self.link(data))['ok'],data)

    def test_reject_forged_expired_future_private_hosts_and_extra_fields(self):
        self.assertEqual(self.verify(self.link()[:-1]+'x').get('error'),'invalid_invitation')
        for patch in [dict(expires_at=int(time.time())-1),dict(issued_at=int(time.time())+600),
                      dict(expires_at=int(time.time())+90000),dict(server='127.0.0.1'),dict(server='192.168.1.1'),
                      dict(server='169.254.169.254'),dict(server='100.64.0.1'),dict(server='192.0.2.1'),dict(server='203.0.113.1'),dict(server='224.0.0.1'),dict(server='01.2.3.4'),dict(server='vps.example'),dict(server_user='root'),
                      dict(server_user='x;id'),dict(remote_port=22),dict(purpose='shell'),dict(command='id'),
                      dict(server_port=True),dict(tunnel_key='a'*100)]:
            data=self.payload(); data.update(patch)
            with self.subTest(patch=patch):
                self.assertIn('error',self.verify(self.link(data)))
        raw=json.dumps(self.payload()).encode().replace(b'"schema_version": 1',b'"schema_version": 1, "schema_version": 1')
        self.assertIn('error',self.verify(self.link(raw=raw)))
        self.assertIn('error',self.verify('x'*18000))
        self.assertIn('error',self.verify(self.link().replace('https://github.com/','https://evil.test/')))

    def journal(self, script, root, **data):
        return self.php("$j=new AsusTechnicalJournal($v['root'].'/journal.json', $v['owner']);"+script,
                        dict(root=str(root),owner=os.getuid(),**data))

    def test_restore_exact_original_missing_files_modes_and_final_newline(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); (root/'keys').write_bytes(b'existing-without-lf');(root/'keys').chmod(0o640)
            changes=[dict(path=str(root/'keys'),line='owned-key'),dict(path=str(root/'missing'),line='owned-host')]
            self.assertEqual(self.journal("$j->apply($v['changes']); return true;",root,changes=changes),{'ok':True})
            self.assertTrue((root/'journal.json').is_file())
            self.assertEqual(self.journal("$j->restore(); return true;",root),{'ok':True})
            self.assertEqual((root/'keys').read_bytes(),b'existing-without-lf')
            self.assertEqual((root/'keys').stat().st_mode&0o777,0o640)
            self.assertFalse((root/'missing').exists())
            self.assertFalse((root/'journal.json').exists())

    def test_rollback_preserves_unrelated_concurrent_key_and_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); f=root/'keys'; f.write_bytes(b'old-without-lf'); f.chmod(0o600)
            self.assertEqual(self.journal("$j->apply($v['changes']); return true;",root,changes=[dict(path=str(f),line='owned-key')]), {'ok':True})
            with f.open('ab') as o:o.write(b'unrelated-key\n')
            self.assertEqual(self.journal("$j->restore(); return true;",root),{'ok':True})
            self.assertEqual(f.read_bytes(),b'old-without-lf\nunrelated-key\n')
            (root/'link').symlink_to(f)
            r=self.journal("$j->apply($v['changes']); return true;",root,changes=[dict(path=str(root/'link'),line='bad')])
            self.assertEqual(r.get('error'),'unsafe_key_file')
            self.assertNotIn(b'bad',f.read_bytes())

    def test_runtime_status_exposes_no_invitation_and_unknown_stop_is_idempotent(self):
        # A private, trusted fixture directory avoids touching host router state.
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self.php("$c=new AsusTechnicalChannel(['runtime'=>$v['root'].'/run','journal'=>$v['root'].'/journal.json','owner'=>$v['owner']]);return [$c->status(),$c->stop()];",dict(root=d,owner=os.getuid())),
                             {'ok':[{'state':'idle','session_id':None,'expires_at':None,'code':None}, {'state':'idle','session_id':None,'expires_at':None,'code':None}]})

    def test_oversized_key_files_refused_before_any_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); f=root/'keys'; f.write_bytes(b'x'*65536); f.chmod(0o600)
            r=self.journal("$j->apply($v['changes']); return true;",root,changes=[dict(path=str(f),line='owned')])
            self.assertEqual(r.get('error'),'unsafe_key_file')
            self.assertEqual(f.read_bytes(),b'x'*65536)
            self.assertFalse((root/'journal.json').exists())

    def test_guard_requires_live_matching_worker_tunnel_source_and_both_deadlines(self):
        data=self.php("return AsusTechnicalProcess::identity(getmypid());",{})['ok']
        # Previous PHP has exited, so a stale but correctly formatted identity fails closed.
        self.assertEqual(self.php("return AsusTechnicalProcess::active($v['state'],time(),AsusTechnicalProcess::uptime());",
          dict(state=dict(identity=data,expires_at=int(time.time())+100,uptime_deadline=1e12))),{'ok':False})
        script="""$s=['identity'=>AsusTechnicalProcess::identity(getmypid()),'expires_at'=>time()+10,'uptime_deadline'=>AsusTechnicalProcess::uptime()+10,'state'=>'connected'];
        $a=AsusTechnicalProcess::active($s,time(),AsusTechnicalProcess::uptime());
        $s['uptime_deadline']=0; $b=AsusTechnicalProcess::active($s,time()-1000,AsusTechnicalProcess::uptime());
        return [$a,$b];"""
        self.assertEqual(self.php(script,{}),{'ok':[True,False]})

if __name__=='__main__':unittest.main()

# Run against the real index.php admission code. Only router paths/service leases
# are substituted by the existing fixture; authentication is not mocked.
from test_auth_api import PasswordApiTests

@unittest.skipUnless(PHP, 'native PHP required')
class TechnicalChannelApiTests(PasswordApiTests):
    __unittest_skip__ = not bool(PHP)
    def setUp(self):
        import test_auth_api
        test_auth_api.PHP=PHP
        super().setUp()
        import shutil
        for name in [p.name for p in PUBLIC.glob('*.php') if not (self.base/p.name).exists()]:
            shutil.copyfile(PUBLIC/name,self.base/name)

    def test_channel_requires_password_csrf_and_same_origin(self):
        self.assertEqual(self.request({'cmd':'technicalstart','invitation':'bad','csrf_token':'x'},'visitor')[0],401)
        token=self.login()
        self.assertEqual(self.request({'cmd':'technicalstart','invitation':'bad','consent':'temporary_root_access','csrf_token':'0'*64})[0],403)
        self.assertEqual(self.request({'cmd':'technicalstart','invitation':'bad','consent':'temporary_root_access','csrf_token':token})[0],403)
        self.assertEqual(self.change('',token)[0],200)
        token=self.request({'cmd':'login'},'anonymous')[1]['csrf_token']
        for cmd in ['technicalstart','technicalstatus','technicalstop']:
            code,data=self.request({'cmd':cmd,'invitation':'bad','consent':'temporary_root_access','csrf_token':token},'anonymous')
            self.assertEqual((code,data),(403,{'error':'auth_required'}))

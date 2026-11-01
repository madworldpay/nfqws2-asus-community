"""Run as root in an isolated temporary tree; never reads operator credentials."""
import json,os,re,stat,sys,tempfile,types,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DEPLOY=ROOT/'support-relay/deploy/entware'
DATA={'source':(DEPLOY/'source-control.py').read_text(),'config':(DEPLOY/'lighttpd.conf.example').read_text()}

@unittest.skipUnless(os.geteuid()==0,'root required to test the actual frontend UID')
class UploadRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='nfqws-upload-test-')
        self.root=Path(self.temp.name)
        self.root.chmod(0o755)
        self.config=DATA['config']
        for key,value in {'CATALOG_ROOT':str(self.root/'public'),'TLS_CERTIFICATE':str(self.root/'cert.pem'),
                          'TLS_PRIVATE_KEY':str(self.root/'key.pem'),'SUPPORT_HOST_REGEX':r'example\.invalid'}.items():
            self.config=self.config.replace(key,value)
        self.mod=types.ModuleType('candidate_source_control')
        exec(compile(DATA['source'],'source-control.py','exec'),self.mod.__dict__)
        self.mod.FRONT=self.root/'nfqws-source-frontend'
        self.mod.RELAY=self.root/'nfqws-source-relay'
        if hasattr(self.mod,'UPLOAD'):self.mod.UPLOAD=self.root/'nfqws-source-body'
        upload=re.search(r'server\.upload-dirs\s*=\s*\(\s*"([^"]+)"',self.config).group(1)
        self.upload=self.root/Path(upload).relative_to('/opt/var/run')
        self.mod.FRONT.mkdir()
        self.upload.mkdir(parents=True,exist_ok=True)
        self.upload.chmod(0o755)
        self.cert=self.root/'cert.pem';self.cert.write_bytes(b'public certificate fixture\n')
        self.vendor=self.root/'vendor-init';self.vendor.write_bytes(b'fixture\n')
        self.vendor.chmod(0o755)
        mapping={'/opt/var/lib/nfqws-support':self.root/'metadata',
                 '/opt/etc/init.d/S80lighttpd':self.vendor,'/etc/cert.pem':self.cert}
        self.mod.Path=lambda p:mapping[p]

    def tearDown(self):self.temp.cleanup()

    def nobody_can_upload(self):
        child=os.fork()
        if child==0:
            try:
                os.setgroups([]);os.setgid(65534);os.setuid(65534)
                fd,path=tempfile.mkstemp(prefix='lighttpd-upload-',dir=self.upload)
                os.write(fd,b'x'*65537);os.close(fd);os.unlink(path)
                os._exit(0)
            except PermissionError:os._exit(13)
            except BaseException:os._exit(99)
        _,status=os.waitpid(child,0)
        return os.waitstatus_to_exitcode(status)

    def test_prepare_makes_large_upload_spool_writable_without_opening_control_dir(self):
        self.mod.prepare()
        self.assertEqual(self.nobody_can_upload(),0,'unprivileged frontend cannot create its large-request spool')
        self.assertEqual(stat.S_IMODE(self.mod.FRONT.stat().st_mode),0o700)
        self.assertEqual(self.mod.FRONT.stat().st_uid,0)
        self.assertEqual(stat.S_IMODE(self.upload.stat().st_mode),0o700)
        self.assertEqual(self.upload.stat().st_uid,65534)
        self.assertEqual(self.upload.stat().st_gid,65534)
        self.assertEqual(self.cert.read_bytes(),b'public certificate fixture\n')
        self.mod.prepare()
        self.assertEqual(self.nobody_can_upload(),0,'watchdog preparation must preserve working upload ownership')

    def test_prepare_refuses_redirected_upload_directory(self):
        self.upload.rmdir();outside=self.root/'outside';outside.mkdir();outside.chmod(0o755)
        self.upload.symlink_to(outside,target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError,'symlink'):self.mod.prepare()
        self.assertEqual(stat.S_IMODE(outside.stat().st_mode),0o755)
        self.assertEqual(outside.stat().st_uid,0)

    def test_prepare_refuses_upload_path_occupied_by_a_hardlinked_file(self):
        self.upload.rmdir();outside=self.root/'outside-file';outside.write_bytes(b'unchanged\n');outside.chmod(0o640)
        os.link(outside,self.upload)
        with self.assertRaises(FileExistsError):self.mod.prepare()
        self.assertEqual(stat.S_IMODE(outside.stat().st_mode),0o640)
        self.assertEqual(outside.stat().st_uid,0)
        self.assertEqual(outside.read_bytes(),b'unchanged\n')

    def test_prepare_does_not_broaden_or_take_ownership_of_an_unsafe_parent(self):
        self.root.chmod(0o777)
        with self.assertRaisesRegex(RuntimeError,'upload parent'):self.mod.prepare()
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode),0o777)

if __name__=='__main__':unittest.main(verbosity=2)

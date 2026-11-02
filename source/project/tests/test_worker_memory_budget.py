"""Low configured CGI memory must not break a trusted signed updater entry."""
import base64
import gzip
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_dpi_normalize import ROOT

AUDIT = ROOT / '.work/packaging-audit-20261012'
ABIS = ('armv7-legacy', 'armv7', 'aarch64')
WORK = '''$bytes=str_repeat('m',12*1024*1024);echo json_encode(['bytes'=>strlen($bytes),'memory'=>ini_get('memory_limit'),'peak'=>memory_get_peak_usage(true)]);exit(0);'''

class WorkerMemoryBudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.base.chmod(0o700)
        self.root_status=self.base/'root-status';self.root_status.write_text('Uid:\t0\t0\t0\t0\n')
        app=self.base/'app';app.mkdir();(app/'update-worker.php').write_text('<?php '+WORK)

    def entry(self, source, files=None):
        text=(ROOT/source).read_text().replace('/proc/self/status',str(self.root_status))
        args=('apply','a'*32)
        if source=='asus/install-extract.php':
            text=text.replace("$s['uid']!==0", "$s['uid']!=="+str(os.getuid()))
            payload=files or {'main.php':{'data':base64.b64encode(('<?php '+WORK).encode()).decode(),'mode':0o600}}
            encoded=base64.b64encode(gzip.compress(json.dumps(payload).encode())).decode()
            text=text.replace('<?php','<?php const NFQWS_ASUS_INSTALL_FILES='+json.dumps(encoded)+';',1)
            work=self.base/'work';work.mkdir(mode=0o700,exist_ok=True)
            args=('check',str(work))
        path=self.base/'entry.php';path.write_text(text);return path,args

    def run_cgi(self, abi, entry, args, memory='8M', http=False):
        root=AUDIT/(abi+'-sysroot');runner=AUDIT/('qemu-aarch64' if abi=='aarch64' else 'qemu-arm')
        self.assertTrue((root/'opt/bin/php8-cgi').is_file(),'actual CGI fixture required')
        env=dict(os.environ)
        for key in ('REQUEST_METHOD','QUERY_STRING','CONTENT_TYPE','CONTENT_LENGTH','SCRIPT_FILENAME'):env.pop(key,None)
        if http:env.update(REQUEST_METHOD='GET',REDIRECT_STATUS='200',SCRIPT_FILENAME=str(entry))
        return subprocess.run([str(runner),'-L',str(root),'-E','LD_LIBRARY_PATH='+str(root/'opt/lib'),str(root/'opt/bin/php8-cgi'),'-n','-d','memory_limit='+memory,'-d','register_argc_argv=1','-q','-f',str(entry),'--',*args],env=env,capture_output=True,text=True,timeout=8)

    def test_root_bootstrap_completes_with_eight_megabyte_configuration(self):
        for source in ('asus/install-extract.php',):
            entry,args=self.entry(source)
            for abi in ABIS:
                with self.subTest(source=source,abi=abi):
                    r=self.run_cgi(abi,entry,args)
                    self.assertEqual(r.returncode,0,r.stdout+r.stderr)
                    value=json.loads(r.stdout);self.assertEqual(value['bytes'],12582912)
                    self.assertIn(value['memory'],('32M','64M'),'bootstrap allowance stays bounded')
                    self.assertLess(value['peak'],32*1024*1024)

    def test_extracted_buffers_are_released_before_coordinator_memory_is_used(self):
        code=WORK.replace('12*1024*1024','26*1024*1024')
        files={'main.php':{'data':base64.b64encode(('<?php '+code).encode()).decode(),'mode':0o600},
               'z-buffer.bin':{'data':base64.b64encode(b'x'*(3*1024*1024)).decode(),'mode':0o600}}
        entry,args=self.entry('asus/install-extract.php',files)
        r=self.run_cgi('armv7-legacy',entry,args)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertEqual(json.loads(r.stdout)['bytes'],27262976)
        self.assertEqual((self.base/'work/z-buffer.bin').stat().st_size,3145728)

    def test_larger_and_unlimited_configuration_is_preserved(self):
        for source in ('asus/install-extract.php',):
            entry,args=self.entry(source)
            for memory in ('128M','-1'):
                with self.subTest(source=source,memory=memory):
                    r=self.run_cgi('armv7-legacy',entry,args,memory)
                    self.assertEqual(r.returncode,0,r.stdout+r.stderr)
                    self.assertEqual(json.loads(r.stdout)['memory'],memory)

    def test_http_and_nonroot_cannot_enter_bootstrap_work(self):
        for source in ('asus/install-extract.php',):
            entry,args=self.entry(source)
            r=self.run_cgi('armv7-legacy',entry,args,http=True)
            self.assertNotEqual(r.returncode,0);self.assertNotIn('"bytes"',r.stdout)
            self.root_status.write_text('Uid:\t1000\t1000\t1000\t1000\n')
            r=self.run_cgi('armv7-legacy',entry,args)
            self.assertNotEqual(r.returncode,0);self.assertNotIn('"bytes"',r.stdout)
            self.root_status.write_text('Uid:\t0\t0\t0\t0\n')

    def test_unsafe_extraction_destination_cannot_enter_bootstrap_work(self):
        entry,args=self.entry('asus/install-extract.php');(self.base/'work').chmod(0o755)
        r=self.run_cgi('armv7-legacy',entry,args)
        self.assertNotEqual(r.returncode,0);self.assertNotIn('"bytes"',r.stdout)

if __name__=='__main__':unittest.main()

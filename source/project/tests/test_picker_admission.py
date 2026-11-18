"""Optional root-managed Start admission, without extending the public API."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import uuid
from test_dpi_normalize import PHP, PUBLIC

PROJECT = Path(__file__).resolve().parents[1]
IMAGE = os.environ.get('NFQWS_TEST_GUARD_PHP_IMAGE', 'nfqws-openwrt-test:25.12.6-php')


class PickerAdmissionTests(unittest.TestCase):
    def php(self, body):
        with tempfile.TemporaryDirectory() as folder:
            r = subprocess.run([PHP, '-n', '-r',
                "require $argv[1].'/strategy-picker-runtime.php';" + body,
                str(PUBLIC), folder], capture_output=True, text=True, timeout=10)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stderr, '')
        return json.loads(r.stdout)

    def test_unmanaged_missing_registry_preserves_legacy_start_admission(self):
        out = self.php(r'''
        $a=new NfqwsStrategyPickerAdmission($argv[2].'/not-created');
        echo json_encode(['lease'=>$a->enter(str_repeat('a',32),str_repeat('b',64),null),
          'created'=>file_exists($argv[2].'/not-created')]);
        ''')
        self.assertEqual(out, {'lease': None, 'created': False})

    def test_constructor_refuses_noncanonical_roots_before_access(self):
        out = self.php(r'''
        $out=[];foreach(['','relative','.','/','/tmp/../elsewhere','/tmp/./registry','/tmp//registry','/tmp/registry/',"/tmp/registry\0"]as $root){
          try{new NfqwsStrategyPickerAdmission($root);$out[]='accepted';}
          catch(Throwable $e){$out[]=$e->getMessage();}}
        echo json_encode($out);
        ''')
        self.assertEqual(out, ['invalid_admission'] * 9)

    def test_management_requires_actual_root_uid(self):
        out = self.php(r'''
        $a=new NfqwsStrategyPickerAdmission($argv[2].'/registry');
        try{$a->prepare(str_repeat('a',32),str_repeat('b',32),str_repeat('c',64),str_repeat('d',64));echo json_encode('accepted');}
        catch(Throwable $e){echo json_encode($e->getMessage());}
        ''')
        self.assertEqual(out, 'accepted' if os.getuid() == 0 else 'invalid_admission')

    def test_identity_records_actual_kernel_credentials(self):
        out = self.php(r'''
        $a=NfqwsStrategyPickerAdmission::identity(getmypid());
        preg_match('/^Uid:\s+([0-9]+)\s+([0-9]+)\s+([0-9]+)\s+([0-9]+)/m',file_get_contents('/proc/self/status'),$m);
        echo json_encode(['uid'=>$a['uid'],'kernel'=>(int)$m[2],'PID'=>$a['pid']===getmypid()]);
        ''')
        self.assertEqual(out, {'uid':os.getuid(),'kernel':os.getuid(),'PID':True})

    def test_public_typed_api_has_no_admission_fields_or_issuer(self):
        out = self.php(r'''
        $p=['cmd'=>'pickersynthesize','csrf_token'=>'fixture','request_id'=>str_repeat('a',32),
         'consent'=>'test','goal'=>'all','concurrency'=>'32','plan_sha256'=>str_repeat('b',64),
         'custom_sites'=>"nnmclub.to\nrutracker.org\nwww.youtube.com\n1.1.1.1\n8.8.8.8",'custom_only'=>'1'];
        NfqwsStrategyPickerRuntime::validateRequest($p);$out=['legacy_shape_accepted'];
        foreach(['operator_scope','admission_deadline','controller_hash']as $key){
         try{NfqwsStrategyPickerRuntime::validateRequest($p+[$key=>'x']);$out[]='accepted';}
         catch(Throwable $e){$out[]=$e->getMessage();}}
        try{NfqwsStrategyPickerRuntime::validateRequest(['cmd'=>'pickeradmissionprepare','csrf_token'=>'fixture']);$out[]='accepted';}
        catch(Throwable $e){$out[]=$e->getMessage();}echo json_encode($out);
        ''')
        self.assertEqual(out, ['legacy_shape_accepted'] + ['invalid_request'] * 4)

    def test_admission_errors_are_fixed_codes_and_unknown_details_stay_private(self):
        codes = ['admission_closed','admission_busy','admission_mismatch','invalid_admission']
        out = self.php(r'''
        $out=[];foreach(['admission_closed','admission_busy','admission_mismatch','invalid_admission','/private/operator/unknown']as $s)
         $out[]=NfqwsStrategyPickerRuntime::error(new RuntimeException($s));echo json_encode($out);
        ''')
        self.assertEqual(out, codes + ['failed'])

    def root_policy(self, pid1=False, opt_alias=False, native=False):
        task = 'picker-admission-' + uuid.uuid4().hex
        cid = None
        image_id = subprocess.check_output(['docker','image','inspect','--format','{{.Id}}',IMAGE],text=True,timeout=5).strip()
        self.assertRegex(image_id, r'^sha256:[a-f0-9]{64}$')
        entry = ['/usr/bin/php8-cgi','-n','-d','register_argc_argv=1','-q','-f','/source/tests/fixtures/picker-admission-policy.php','--','pid1'] if pid1 else ['/bin/sh','-c','/usr/bin/php8-cgi -n -d register_argc_argv=1 -q -f /source/tests/fixtures/picker-admission-policy.php; exit $?']
        if opt_alias:
            entry=['/bin/sh','-c',
                'if [ -e /opt ] || [ -L /opt ]; then rmdir /opt || exit 97; fi; '
                'mkdir -p /tmp/mnt/admission-fixture/entware/etc/nfqws-asus-web; '
                'ln -s /tmp/mnt/admission-fixture/entware /opt; '
                '/usr/bin/php8-cgi -n -d register_argc_argv=1 -q -f /source/tests/fixtures/picker-admission-policy.php -- opt-alias; exit $?']
        if native:
            entry=['/bin/sh','-c','/usr/bin/php8-cgi -n -d register_argc_argv=1 -q -f /source/tests/fixtures/picker-admission-policy.php -- native-default; exit $?']
        readonly=[]if opt_alias or native else['--read-only']
        try:
            c = subprocess.run(['docker','create','--pull=never','--name',task,
                '--label','org.nfqws2.task='+task,'--network','none','--cap-drop','ALL',
                '--security-opt','no-new-privileges:true',*readonly,'--pids-limit','16',
                '--memory','64m','--cpus','0.5','--tmpfs','/tmp:rw,nosuid,nodev,mode=1777,size=16m',
                '--mount','type=bind,src='+str(PROJECT)+',dst=/source,readonly',
                '--entrypoint',entry[0],image_id,*entry[1:]],
                capture_output=True,text=True,timeout=10)
            self.assertEqual(c.returncode,0,c.stderr);cid=c.stdout.strip()
            info=json.loads(subprocess.check_output(['docker','inspect',cid],text=True,timeout=5))[0]
            self.assertEqual(info['Image'],image_id)
            r=subprocess.run(['docker','start','-a',cid],capture_output=True,text=True,timeout=15)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            self.assertEqual(r.stderr,'')
            answer=json.loads(r.stdout)
        finally:
            if cid:
                info=json.loads(subprocess.check_output(['docker','inspect',cid],text=True,timeout=5))[0]
                self.assertEqual(info['Name'],'/'+task)
                self.assertEqual(info['Config']['Labels']['org.nfqws2.task'],task)
                self.assertEqual(info['Image'],image_id)
                subprocess.run(['docker','rm','-f',cid],check=True,capture_output=True,timeout=5)
                absent=subprocess.run(['docker','container','inspect',task],capture_output=True,text=True,timeout=5)
                self.assertNotEqual(absent.returncode,0);self.assertIn('no such',absent.stderr.lower())

        return answer

    def test_actual_isolated_root_registry_policy_and_CAS(self):
        self.assertEqual(self.root_policy(), {'passed':True,'assertions':29})

    def test_actual_native_profile_uses_its_default_root_registry(self):
        self.assertEqual(self.root_policy(native=True), {'passed':True,'assertions':3,'profile':'openwrt'})

    def test_only_the_existing_firmware_opt_alias_is_accepted(self):
        self.assertEqual(self.root_policy(opt_alias=True), {'passed':True,'assertions':4,'firmware_alias_verified':True})

    def test_pid1_cannot_publish_an_invalid_handler_record(self):
        self.assertEqual(self.root_policy(pid1=True), {'passed':True,'assertions':2,'PID':1})


if __name__ == '__main__':
    unittest.main()

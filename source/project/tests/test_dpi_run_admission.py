"""Bound native run admission to measured binaries and workloads, not installation."""
import copy
import json
import os
import subprocess
import tempfile
import unittest
from test_dpi_normalize import PHP, PUBLIC


BOUNDED = {
    'tests': [2, 3],
    'options': {
        'config': {'IP_VERSION': 'ipv4', 'TLS_FINGERPRINT': 'rustls',
                   'MAX_CONCURRENT': 4, 'TIMEOUT': 8},
        'targets': {'domains': ['nnmclub.to', 'rutracker.org', 'rutor.info', 'tapochek.net']},
    },
}


class DpiRunAdmissionTests(unittest.TestCase):
    def php(self, body, payload=None):
        with tempfile.TemporaryDirectory() as tmp:
            r = subprocess.run(
                [PHP, '-n', '-r', "require $argv[1].'/dpi-jobs.php';" + body,
                 str(PUBLIC), tmp, str(os.getuid())],
                input=json.dumps(payload), capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertEqual(r.stderr, '')
        return json.loads(r.stdout)

    def admission(self, memory, run, artifact=None):
        if artifact is None:
            artifact = {'name': 'dpi-detector-linux-armv7', 'elf_machine': 40, 'elf_class': 1}
        return self.php("$p=json_decode(stream_get_contents(STDIN),true);"
                        "echo json_encode(AsusDpiInstaller::memoryAvailability($p['memory'],$p['run'],$p['artifact']));",
                        {'memory': memory, 'run': run, 'artifact': artifact})

    def test_reported_memory_is_not_an_installation_or_run_capacity_limit(self):
        self.assertEqual(self.admission(23000,BOUNDED),{'available':True,'code':'ready'})
        self.assertEqual(self.admission(23000,None),{'available':True,'code':'ready'})

    def retained_availability(self, preferred, retained, memory):
        # Substitute host capabilities/RAM only. Exercise the real activation
        # marker, file hash, retained-artifact selection and availability route.
        result = self.php(r'''
$p=json_decode(stream_get_contents(STDIN),true);$GLOBALS['fixture_memory']=$p['memory'];
$shim= <<<'PHP'
namespace AdmissionFixture;
use \Throwable;use \RuntimeException;
\class_alias('AsusDpiStore',__NAMESPACE__.'\\AsusDpiStore');
\class_alias('AsusDpiCatalog',__NAMESPACE__.'\\AsusDpiCatalog');
\class_alias('AsusDpiLoadPolicy',__NAMESPACE__.'\\AsusDpiLoadPolicy');
\class_alias('NfqwsPlatform',__NAMESPACE__.'\\NfqwsPlatform');
function file_get_contents($path,...$args){return $path==='/proc/meminfo'?'MemAvailable: '.$GLOBALS['fixture_memory']." kB\n":\file_get_contents($path,...$args);}
function extension_loaded($name){return $name==='openssl'||\extension_loaded($name);}
function is_readable($path){return str_ends_with($path,'/ca-certificates.crt')||\is_readable($path);}
function disk_free_space($path){return 1073741824;}
class AsusDpiRuntime {function capabilities(){return ['available'=>true,'code'=>'ready'];}}
PHP;
$source=file_get_contents($argv[1].'/dpi-install.php');
$source=str_replace('__DIR__',var_export($argv[1],true),substr($source,5));
file_put_contents($argv[2].'/namespaced.php','<?php '.$shim.$source);require $argv[2].'/namespaced.php';
$root=$argv[2].'/managed';mkdir($root,0711);chmod($root,0711);$bytes=str_repeat('x',64);$hash=hash('sha256',$bytes);
$measured=['name'=>$p['retained'],'elf_machine'=>40,'elf_class'=>1,'size'=>64,'sha256'=>$hash];
$legacy=['name'=>$p['preferred'],'elf_machine'=>40,'elf_class'=>1,'size'=>65,'sha256'=>str_repeat('a',64),'accepted_installed'=>[$measured]];
file_put_contents($root.'/'.$hash,$bytes);chmod($root.'/'.$hash,0755);
file_put_contents($root.'/active.json',json_encode(['version'=>AsusDpiCatalog::load()['version'],'sha256'=>$hash]));chmod($root.'/active.json',0600);
$i=new AdmissionFixture\AsusDpiInstaller($root,(int)$argv[3],$legacy);
$out=['installed'=>$i->installed()['installed'],'run'=>$i->availability($p['run']),'install'=>$i->availability()];
file_put_contents($root.'/'.$hash,str_repeat('y',64));clearstatcache();
$out['tampered_run']=$i->availability($p['run']);$out['tampered_installed']=$i->installed()['installed'];echo json_encode($out);
''', {'memory': memory, 'run': BOUNDED, 'preferred': preferred, 'retained': retained})
        return result

    def test_availability_uses_verified_retained_binary_instead_of_legacy_preference(self):
        result = self.retained_availability('dpi-detector-armv5te', 'dpi-detector-linux-armv7', 64476)
        self.assertEqual(result, {'installed': True,
            'run': {'available': True, 'code': 'ready'},
            'install': {'available': True, 'code': 'ready'},
            'tampered_run': {'available': True, 'code': 'ready'}, 'tampered_installed': False})

    def test_tampered_retained_binary_stays_uninstalled_without_memory_gate(self):
        result = self.retained_availability('dpi-detector-linux-armv7', 'dpi-detector-armv5te', 65360)
        self.assertEqual(result, {'installed': True,
            'run': {'available': True, 'code': 'ready'},
            'install': {'available': True, 'code': 'ready'},
            'tampered_run': {'available': True, 'code': 'ready'}, 'tampered_installed': False})

    def start(self, kind, memory):
        return self.php(r'''
$p=json_decode(stream_get_contents(STDIN),true);$calls=[];
$s=new AsusDpiStore($argv[2].'/state',(int)$argv[3]);
$j=new AsusDpiJobs($s,[
 'terminal_gate'=>new AsusDpiTerminalLifecycle($argv[2].'/terminal',(int)$argv[3]),
 'installed'=>fn()=>true,
 'available'=>function($kind='install',$params=[])use($p){return AsusDpiInstaller::memoryAvailability($p['memory'],$kind==='run'?$params:null,['name'=>'dpi-detector-linux-armv7','elf_machine'=>40,'elf_class'=>1]);},
 'launch'=>function($id,$kind)use(&$calls){$calls[]=$kind;}
]);
try{
 $result=$p['kind']==='install'?$j->startInstall('11111111-1111-4111-8111-111111111111',true):
  $j->startRun('11111111-1111-4111-8111-111111111111',[2,3],[],$p['run']['options']);
 $out=['state'=>$result['state'],'kind'=>$result['kind']];
}catch(Throwable $e){$out=['error'=>$e->getMessage()];}
$out['launches']=$calls;$out['reserved']=$s->status()['active']!==null;
echo json_encode($out);''', {'kind': kind, 'memory': memory, 'run': BOUNDED})

    def test_job_dispatch_uses_run_policy_for_probe_only(self):
        out = self.start('run', 64476)
        self.assertEqual(out, {'state': 'queued', 'kind': 'run', 'launches': ['run'], 'reserved': True})

    def test_low_memory_does_not_prevent_normal_install_or_probe_dispatch(self):
        for kind, memory in [('install', 64476), ('run', 57343)]:
            with self.subTest(kind=kind, memory=memory):
                self.assertEqual(self.start(kind, memory), {
                    'state': 'queued', 'kind': kind, 'launches': [kind], 'reserved': True})


if __name__ == '__main__':
    unittest.main()

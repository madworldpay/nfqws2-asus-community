"""Pinned native upstream with synthetic targets in a network namespace without uplinks."""
import hashlib,json,os,subprocess,tempfile,unittest
from pathlib import Path
from test_dpi_normalize import PHP,PUBLIC,ROOT

class DpiUpstreamContractTests(unittest.TestCase):
    def test_pinned_cli_json_with_only_synthetic_network(self):
        assets=Path(os.environ['DPI_TEST_ASSETS']);abi=Path(PHP).name.removesuffix('-cli-wrapper');arm=abi.startswith('armv7');name='dpi-detector-linux-armv7' if arm else 'dpi-detector-linux-arm64'
        catalog=json.loads((ROOT/'support/dpi-catalog.json').read_text());artifact=catalog['artifacts']['armv7-3.2' if arm else 'aarch64-3.10'];binary=assets/name
        self.assertEqual(hashlib.sha256(binary.read_bytes()).hexdigest(),artifact['sha256'])
        cache=Path(PHP).parent;qemu=cache/('qemu-arm' if arm else 'qemu-aarch64');sysroot=cache/(abi+'-sysroot')
        script='''import os,json,socket,subprocess,threading,sys
subprocess.run(['ip','link','set','lo','up'],check=True)
s=socket.socket();s.bind(('127.0.0.1',0));s.listen();s.settimeout(.1)
stop=False
def serve():
 while not stop:
  try:c,_=s.accept();c.close()
  except socket.timeout:pass
t=threading.Thread(target=serve,daemon=True);t.start()
p=json.load(open('config.yml'));p.update(TIMEOUT=.1,FAT_CONNECT_TIMEOUT=.1,FAT_READ_TIMEOUT=.1,STUB_IPS_TIMEOUT=.1,IP4_LOOKUP_URLS=[],IP6_LOOKUP_URLS=[],CYMRU_DOH_SERVERS=[])
open('config.yml','w').write(json.dumps(p));open('tcp16.json','w').write(json.dumps([{'id':'HE-01','asn':'PRIVATE_CANARY','provider':'PRIVATE_CANARY','ip':'127.0.0.1','port':s.getsockname()[1]}]))
r=subprocess.run(sys.argv[1:]+json.load(open('native-args.json')),env={'PATH':'/usr/bin:/bin','LANG':'C','HOME':os.getcwd(),'XDG_CONFIG_HOME':os.getcwd(),'TMPDIR':os.getcwd(),'TOKIO_WORKER_THREADS':'1'},capture_output=True,timeout=15)
stop=True;s.close();sys.stdout.buffer.write(r.stdout);sys.stderr.buffer.write(r.stderr);sys.exit(r.returncode)
'''
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)
            code="require $argv[1].'/dpi-options.php';echo json_encode(AsusDpiOptions::compile(['config'=>['TIMEOUT'=>0.1,'FAT_CONNECT_TIMEOUT'=>0.1,'FAT_READ_TIMEOUT'=>0.1,'STUB_IPS_TIMEOUT'=>0.1,'IP4_LOOKUP_URLS'=>[],'IP6_LOOKUP_URLS'=>[],'CYMRU_DOH_SERVERS'=>[]],'targets'=>['tcp'=>[['id'=>'HE-01','ip'=>'127.0.0.1','port'=>443]]]],3,'/native'));"
            compiled=subprocess.run([PHP,'-n','-r',code,str(PUBLIC)],capture_output=True,text=True);self.assertEqual(compiled.returncode,0,compiled.stderr)
            compiled=json.loads(compiled.stdout)
            for name,content in compiled['files'].items():(p/name).write_text(content)
            (p/'native-args.json').write_text(json.dumps(compiled['argv'][1:]))
            run=subprocess.run(['unshare','-Urn','python3','-c',script,str(qemu),'-L',str(sysroot),str(binary)],cwd=p,capture_output=True,timeout=20)
            self.assertEqual(run.returncode,0,run.stderr.decode());self.assertEqual(run.stderr,b'', 'compiled settings produced native warnings');raw=p/'raw';raw.write_bytes(run.stdout)
            value=json.loads(run.stdout);self.assertEqual(value['schema_version'],1);self.assertEqual(list(value['results']),['tcp16'])
            code="require $argv[1].'/dpi-normalize.php';echo json_encode(AsusDpiNormalizer::group(file_get_contents($argv[2]),3,AsusDpiCatalog::load()));"
            r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(raw)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertNotIn('PRIVATE_CANARY',r.stdout);self.assertEqual(json.loads(r.stdout)['rows'][0]['target'],'HE-01')

"""The CLI hands its verified archive to the native coordinator without a RAM copy."""
import hashlib,json,os,shlex,subprocess,tempfile,unittest,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
@unittest.skipUnless(os.environ.get('NFQWS_TEST_DOCKER'),'Requires native root PHP')
class NativeLocalArchive(unittest.TestCase):
 def test_verified_archive_is_moved_once_and_substitution_is_rejected(self):
  module=ROOT/'openwrt/install-local-source.php';self.assertTrue(module.is_file(),'CLI coordinator handoff must avoid a second archive in limited router RAM')
  with tempfile.TemporaryDirectory()as td:
   container=os.environ['NFQWS_TEST_DOCKER'];root=Path('/tmp/native-local-'+uuid.uuid4().hex);src=root/'package';dst=root/'operation.package';data=b'verified native package'
   def sh(cmd,stdin=None):return subprocess.run(['docker','exec','-i',container,'sh','-c',cmd],input=stdin,text=True,capture_output=True,timeout=10)
   self.assertEqual(sh('umask 077; mkdir '+str(root)).returncode,0);self.addCleanup(lambda:sh('rm -rf '+str(root)))
   code='interface AsusUpdateSource{function manifest():array;function download(array $p,string $d):void;}require $argv[1];require $argv[2];$v=json_decode($argv[3],true);$s=new NfqwsOpenWrtInstallLocalSource($v);try{$s->download($v["candidate"]["package"],$argv[4]);echo "moved";}catch(RuntimeException $e){echo $e->getMessage();}'
   plan={'archive':str(src),'manifest':'signed','signature':'signed','candidate':{'package':{'size':len(data),'sha256':hashlib.sha256(data).hexdigest()}}}
   call=lambda:subprocess.run(['docker','exec',container,'php-cli','-r',code,str(ROOT/'webui/web/public/update-store.php'),str(module),json.dumps(plan),str(dst)],text=True,capture_output=True,timeout=10)
   sh('umask 077; cat > '+str(src), (data+b'x').decode());self.assertEqual(call().stdout,'download_hash');self.assertEqual(sh('test -f '+str(src)+' && test ! -e '+str(dst)).returncode,0)
   sh('cat > '+str(src),data.decode());r=call();self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stdout,'moved');self.assertEqual(sh('test ! -e '+str(src)).returncode,0);self.assertEqual(sh('cat '+str(dst)).stdout,data.decode());self.assertEqual(sh('ls -l '+str(dst)).stdout.split()[0],'-rw-------')
if __name__=='__main__':unittest.main()

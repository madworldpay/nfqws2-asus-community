import json,os,subprocess,tempfile,unittest
from pathlib import Path
import test_lab as lab
HERE=Path(__file__).resolve().parent
PHP=os.environ.get('PHP_TEST_BINARY','/usr/bin/php')
class Portable(unittest.TestCase):
 def test_pinned_opt_alias_accepts_firmware_mount_but_not_inner_alias(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);mount=root/'mount';mount.mkdir();mount.chmod(0o777);base=mount/'entware';base.mkdir();base.chmod(0o755);alias=root/'opt';alias.symlink_to(base);(base/'private').mkdir(mode=0o700)
   (base/'private/x').write_text('ok');(base/'private/link').symlink_to('/etc/passwd')
   code="require $argv[1].'/platform.php';require $argv[1].'/share-read.php';require $argv[2].'/device-profiles-paths.php';try{$p=new NfqwsDeviceProfilesPaths($argv[3],(int)$argv[4]);$out=$p->file($argv[3].'/private','x');try{$p->file($argv[3].'/private','link');echo 'unsafe';}catch(Throwable $e){echo file_get_contents($out);}}catch(Throwable $e){echo $e->getMessage();}"
   r=subprocess.run([PHP,'-n','-r',code,str(lab.PUBLIC),str(HERE),str(alias),str(os.getuid())],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stdout,'ok')
 def test_cli_entry_follows_only_the_exact_script_through_firmware_alias(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);real=root/'real';real.mkdir();alias=root/'alias';alias.symlink_to(real);file=real/'runtime.php';file.touch()
   code="require $argv[1].'/platform.php';require $argv[2].'/device-profiles-paths.php';echo NfqwsDeviceProfilesPaths::cliEntry($argv[3],[],[$argv[4],'check'])?'yes':'no';echo NfqwsDeviceProfilesPaths::cliEntry($argv[3],['REQUEST_METHOD'=>'POST'],[$argv[4],'check'])?'bad':'safe';"
   r=subprocess.run([PHP,'-n','-r',code,str(lab.PUBLIC),str(HERE),str(file),str(alias/'runtime.php')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stdout,'yessafe')
 def test_uplinks_normalize_real_multiline_shell_output(self):
  code="require $argv[1].'/platform.php';require $argv[1].'/share-resources.php';require $argv[1].'/import-plan.php';require $argv[2].'/../../openwrt/config.php';require $argv[2].'/device-profiles-runtime.php';try{echo json_encode(NfqwsDeviceProfilesRuntime::uplinks(\"wan0\\nwan1\"));}catch(Throwable $e){echo $e->getMessage();}"
  r=subprocess.run([PHP,'-n','-r',code,str(lab.PUBLIC),str(HERE)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stdout,'"wan0 wan1"')
 def test_fixed_cli_entry_accepts_php_cgi_argv_without_script_filename(self):
  code="require $argv[1].'/platform.php';require $argv[2].'/device-profiles-paths.php';echo NfqwsDeviceProfilesPaths::cliEntry('/fixed/runtime.php',[],['/fixed/runtime.php','check'])?'yes':'no';echo NfqwsDeviceProfilesPaths::cliEntry('/fixed/runtime.php',['REQUEST_METHOD'=>'POST'],['/fixed/runtime.php','check'])?'bad':'safe';"
  r=subprocess.run([PHP,'-n','-r',code,str(lab.PUBLIC),str(HERE)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stdout,'yessafe')
if __name__=='__main__':unittest.main()

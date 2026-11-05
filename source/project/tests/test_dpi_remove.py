import os,json,subprocess,tempfile,hashlib,unittest
from pathlib import Path
from test_dpi_normalize import PHP,PUBLIC

class DpiRemovalTests(unittest.TestCase):
 def test_optional_reports_remove_only_detector_materials(self):
  for reports in [False,True]:
   with self.subTest(reports=reports), tempfile.TemporaryDirectory() as directory:
    base=Path(directory);root=base/'managed';root.mkdir(mode=0o711)
    payload=b'owned detector';digest=hashlib.sha256(payload).hexdigest()
    (root/digest).write_bytes(payload);(root/digest).chmod(0o755)
    (root/'active.json').write_text(json.dumps({'version':'v5.0.0-alpha.21','sha256':digest}));(root/'active.json').chmod(0o600)
    original=root/'dpi_detector_results-20261105-130000.txt';original.write_text('native original\n');original.chmod(0o600)
    manual=root/'manual.txt';manual.write_text('manual canary')
    code='''require $argv[1].'/dpi-remove.php';
    $i=new AsusDpiInstaller($argv[2].'/managed',(int)$argv[4],['size'=>14,'sha256'=>$argv[3]]);
    $s=new AsusDpiSavedStore($argv[2].'/saved',$argv[2].'/managed',(int)$argv[4]);$s->refresh();
    $d=new AsusDpiStore($argv[2].'/jobs',(int)$argv[4]);
    $r=(new AsusDpiRemoval($i,$s,$d,new AsusDpiTerminalLifecycle($argv[2].'/terminal',(int)$argv[4])))->remove($argv[5]==='1');echo json_encode([$r,$s->list()]);'''
    result=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(base),digest,str(os.getuid()),'1' if reports else '0'],capture_output=True,text=True)
    self.assertEqual((result.returncode,result.stderr),(0,''),result.stdout)
    out,listing=json.loads(result.stdout);self.assertEqual(out,{'removed':True,'reports_removed':reports})
    self.assertFalse((root/digest).exists());self.assertEqual(original.exists(),not reports);self.assertEqual(len(listing['reports']),0 if reports else 1)
    self.assertEqual(manual.read_text(),'manual canary')

 def test_report_failure_keeps_detector_installed(self):
  with tempfile.TemporaryDirectory() as directory:
   base=Path(directory);root=base/'managed';root.mkdir(mode=0o711)
   payload=b'owned detector';digest=hashlib.sha256(payload).hexdigest()
   (root/digest).write_bytes(payload);(root/digest).chmod(0o755)
   (root/'active.json').write_text(json.dumps({'version':'v5.0.0-alpha.21','sha256':digest}));(root/'active.json').chmod(0o600)
   outside=base/'outside';outside.write_text('never delete')
   (root/'dpi_detector_results-20261105-130000.txt').symlink_to(outside)
   code='''require $argv[1].'/dpi-remove.php';$i=new AsusDpiInstaller($argv[2].'/managed',(int)$argv[4],['size'=>14,'sha256'=>$argv[3]]);
   $s=new AsusDpiSavedStore($argv[2].'/saved',$argv[2].'/managed',(int)$argv[4]);$d=new AsusDpiStore($argv[2].'/jobs',(int)$argv[4]);
   try{(new AsusDpiRemoval($i,$s,$d,new AsusDpiTerminalLifecycle($argv[2].'/terminal',(int)$argv[4])))->remove(true);}catch(Throwable $e){echo json_encode($e->getMessage());}'''
   result=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(base),digest,str(os.getuid())],capture_output=True,text=True)
   self.assertEqual((result.returncode,result.stderr),(0,''));self.assertEqual(json.loads(result.stdout),'reports_not_removed');self.assertTrue((root/digest).is_file());self.assertEqual(outside.read_text(),'never delete')

 def test_install_and_remove_admission_reject_concurrent_mutation(self):
  with tempfile.TemporaryDirectory() as directory:
   base=Path(directory)
   probe=subprocess.run([PHP,'-n','-r',"require $argv[1].'/dpi-store.php';echo method_exists('AsusDpiStore','mutation')?'yes':'no';",str(PUBLIC)],capture_output=True,text=True)
   self.assertEqual(probe.stdout,'yes','DPI install and uninstall must share one exclusive admission lock')
   hold='''require $argv[1].'/dpi-store.php';$s=new AsusDpiStore($argv[2].'/jobs',(int)$argv[3]);$s->mutation(function()use($argv){touch($argv[2].'/held');usleep(1500000);});'''
   owner=subprocess.Popen([PHP,'-n','-r',hold,str(PUBLIC),str(base),str(os.getuid())],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
   try:
    import time
    end=time.monotonic()+2
    while not (base/'held').exists() and time.monotonic()<end:time.sleep(.01)
    self.assertTrue((base/'held').exists())
    install='''require $argv[1].'/dpi-jobs.php';$s=new AsusDpiStore($argv[2].'/jobs',(int)$argv[3]);$j=new AsusDpiJobs($s,['available'=>fn()=>['available'=>true],'launch'=>function(){throw new RuntimeException('LAUNCH_MUST_NOT_HAPPEN');}]);try{$j->startInstall('11111111-1111-4111-8111-111111111111',true);}catch(Throwable $e){echo $e->getMessage();}'''
    remove='''require $argv[1].'/dpi-remove.php';$s=new AsusDpiStore($argv[2].'/jobs',(int)$argv[3]);try{(new AsusDpiRemoval(null,null,$s))->remove(false);}catch(Throwable $e){echo $e->getMessage();}'''
    for code in [install,remove]:
     out=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(base),str(os.getuid())],capture_output=True,text=True,timeout=1)
     self.assertEqual((out.returncode,out.stderr,out.stdout),(0,'','busy'))
   finally:
    owner.communicate(timeout=3)

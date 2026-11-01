"""Actual mode/lstat/open regressions; copied PHP relocates fixed roots and root UID only."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from test_auth_api import PHP
PUBLIC=Path(__file__).resolve().parents[1]/'webui/web/public'

class IpHealthFirmwarePermissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.system_tmp=self.root/'system-tmp'
        self.opt_root=self.system_tmp/'mnt/Flashka/entware';self.opt_root.mkdir(parents=True)
        self.opt_alias=self.root/'opt';self.opt_alias.symlink_to(self.opt_root,target_is_directory=True)
        for p in [self.system_tmp,self.system_tmp/'mnt',self.system_tmp/'mnt/Flashka']:p.chmod(0o777)
        self.opt_root.chmod(0o755);(self.opt_root/'etc/nfqws2').mkdir(parents=True)
        for p in [self.opt_root/'etc',self.opt_root/'etc/nfqws2']:p.chmod(0o755)
        self.state=self.opt_root/'etc/nfqws2/ip-health'
        self.core=self.system_tmp/'nfqws2-asus';self.private=self.core/'private'
        self.private.mkdir(parents=True,mode=0o700);self.core.chmod(0o700)
        self.run=self.system_tmp/'nfqws2-asus-ip-health';self.run.mkdir(mode=0o755)
        self.system_var=self.system_tmp/'var';self.system_var.symlink_to(self.system_tmp,target_is_directory=True)
        self.app=self.root/'app';shutil.copytree(PUBLIC,self.app)
        for name in ['ip-health-store.php','ip-health-runtime.php']:
            path=self.app/name;source=path.read_text()
            # Production has no environment overrides; fixture owns relocated system roots.
            for old,new in [('/var/run',str(self.system_var/'run')),('/var',str(self.system_var)),('/tmp',str(self.system_tmp)),('/opt',str(self.opt_alias)),('/tmp/run',str(self.system_tmp/'run')),('/tmp/nfqws2-asus-ip-health',str(self.run))]:
                source=source.replace("'"+old+"'",repr(new))
            source=source.replace("['uid']===0","['uid']==="+str(os.getuid())).replace("['uid']!==0","['uid']!=="+str(os.getuid()))
            source=source.replace('[0,$this->owner','['+str(os.getuid())+',$this->owner').replace('$this->owner=0;','$this->owner='+str(os.getuid())+';')
            path.write_text(source)
    def php(self,action,state=None):
        code='''require $argv[1].'/ip-health-runtime.php';try{
        $s=new NfqwsIpHealthStore($argv[3]===''?null:$argv[3],$argv[4]);
        if($argv[2]==='view')$v=$s->view();
        elseif($argv[2]==='configure'){$v=$s->configure(true,$s->status()['revision']);$s->runtimeStatus('active',null,time(),'router_udp');$v=$s->status();}
        else{$r=new NfqwsIpHealthRuntime($s,$argv[5],$argv[4],'/proc','/unused',(int)$argv[6]);$r->writePrivate('worker.json',['proof'=>'safe']);$v=['written'=>true];}
        echo json_encode(['ok'=>true,'value'=>$v]);}catch(Throwable $e){echo json_encode(['ok'=>false,'error'=>$e->getMessage()]);}'''
        p=subprocess.run([PHP,'-n','-r',code,str(self.app),action,'' if state is None else str(state),str(self.run),str(self.private),str(os.getuid())],text=True,capture_output=True,timeout=3)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'');return json.loads(p.stdout)
    def test_actual_merlin_modes_allow_default_read_and_explicit_persistence(self):
        v=self.php('view');self.assertTrue(v['ok'],v);self.assertTrue(v['value']['enabled']);self.assertFalse(self.state.exists())
        self.assertTrue(self.php('view',self.state)['ok'], 'capability admission uses the canonical explicit path')
        v=self.php('configure');self.assertTrue(v['ok'],v);self.assertTrue((self.state/'bans.json').is_file())
        self.assertEqual((self.state/'bans.json').stat().st_mode&0o777,0o600);self.assertEqual(v['value']['runtime']['state'],'active')
        for p in [self.system_tmp,self.system_tmp/'mnt',self.system_tmp/'mnt/Flashka']:self.assertEqual(p.stat().st_mode&0o1777,0o777)
    def test_actual_merlin_tmp_allows_private_runtime_write(self):
        v=self.php('runtime');self.assertTrue(v['ok'],v);self.assertEqual(json.loads((self.private/'worker.json').read_text()),{'proof':'safe'})
        self.assertEqual((self.private/'worker.json').stat().st_mode&0o777,0o600)
    def test_unsafe_entware_root_and_managed_ancestors_remain_rejected(self):
        for target,mode in [(self.opt_root,0o777),(self.opt_root/'etc',0o777),(self.opt_root/'etc/nfqws2',0o1777)]:
            with self.subTest(target=target,mode=oct(mode)):
                target.chmod(mode);self.assertEqual(self.php('view'),{'ok':False,'error':'invalid_state'});self.assertFalse(self.state.exists());target.chmod(0o755)
    def test_unsafe_runtime_managed_ancestor_even_sticky_remains_rejected(self):
        for mode in [0o777,0o1777]:
            with self.subTest(mode=oct(mode)):
                self.core.chmod(mode);self.assertEqual(self.php('runtime'),{'ok':False,'error':'invalid_state'});self.assertFalse((self.private/'worker.json').exists())
        self.core.chmod(0o700)
    def test_opt_anchor_does_not_admit_neighbor_under_writable_mount(self):
        neighbor=self.opt_root.with_name('entware-other')/'state';neighbor.mkdir(parents=True,mode=0o700)
        self.assertEqual(self.php('view',neighbor),{'ok':False,'error':'invalid_state'})
    def test_managed_symlink_is_rejected_without_touching_target(self):
        outside=self.root/'outside';outside.mkdir(mode=0o700);self.state.symlink_to(outside,target_is_directory=True)
        self.assertEqual(self.php('configure'),{'ok':False,'error':'invalid_state'});self.assertEqual(list(outside.iterdir()),[])
    def test_trusted_opt_boundary_does_not_relax_journal_link_checks(self):
        self.assertTrue(self.php('configure')['ok'])
        journal=self.state/'bans.json';outside=self.root/'owner-data';outside.write_text('PRESERVE');outside.chmod(0o600)
        for kind in ['symlink','hardlink']:
            with self.subTest(kind=kind):
                journal.unlink()
                if kind=='symlink':journal.symlink_to(outside)
                else:os.link(outside,journal)
                self.assertEqual(self.php('configure'),{'ok':False,'error':'invalid_state'})
                self.assertEqual(outside.read_text(),'PRESERVE')
    def test_native_fixed_var_alias_accepts_tmp_but_rejects_arbitrary_target(self):
        (self.system_tmp/'run').mkdir(mode=0o755);state=self.system_var/'run/state';state.mkdir(mode=0o700)
        v=self.php('view',state);self.assertTrue(v['ok'],v)
        other=self.root/'arbitrary-var';(other/'run/state').mkdir(parents=True,mode=0o700)
        other.chmod(0o755);(other/'run').chmod(0o755)
        self.system_var.unlink();self.system_var.symlink_to(other,target_is_directory=True)
        self.assertEqual(self.php('view',state),{'ok':False,'error':'invalid_state'})
    def test_native_var_run_alias_has_exact_safe_target_for_store_and_runtime(self):
        self.system_var.unlink();self.system_var.mkdir(mode=0o755)
        target=self.system_tmp/'run';target.mkdir(mode=0o755)
        (self.system_var/'run').symlink_to(target,target_is_directory=True)
        state=self.system_var/'run/state';state.mkdir(mode=0o700)
        self.assertTrue(self.php('view',state)['ok'])
        private=self.system_var/'run/private';private.mkdir(mode=0o700);self.private=private
        self.assertTrue(self.php('runtime')['ok'])
        target.chmod(0o777)
        self.assertEqual(self.php('view',state),{'ok':False,'error':'invalid_state'})
        self.assertEqual(self.php('runtime'),{'ok':False,'error':'invalid_state'})

if __name__=='__main__':unittest.main()

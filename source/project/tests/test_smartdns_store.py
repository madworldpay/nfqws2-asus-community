"""Real file store: concurrent editors and failed writes cannot replace active DNS."""
import json
import os
import subprocess
import tempfile
import unittest
import resource
import signal
import fcntl
import time
from pathlib import Path
from test_dpi_normalize import PHP, PUBLIC
from test_smartdns_profile import profile, upstream


class SmartDnsStoreTests(unittest.TestCase):
    def test_persistent_journal_contention_is_bounded_and_preserves_files(self):
        for operation in [['draft'],['saveDraft',profile(upstream(label='must not be written'))]]:
            with self.subTest(operation=operation[0]),tempfile.TemporaryDirectory() as directory:
                root=Path(directory)/'state'
                self.call(root,[['saveDraft',profile()]])
                before={p.name:p.read_bytes() for p in root.iterdir()}
                with (root/'state.lock').open('r+') as lock:
                    fcntl.flock(lock,fcntl.LOCK_EX)
                    started=time.monotonic()
                    result=self.call(root,[operation])
                    elapsed=time.monotonic()-started
                self.assertEqual(result,[{'error':'busy'}])
                self.assertGreaterEqual(elapsed,.9)
                self.assertLess(elapsed,3)
                self.assertEqual({p.name:p.read_bytes() for p in root.iterdir()},before)

    def test_import_draft_compare_and_swap_can_restore_absence(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'state';saved=self.call(root,[['saveDraft',profile()]])[0]['value']
            out=self.call(root,[['replaceDraft',None,'0'*64],['draft'],['replaceDraft',None,saved],['draft'],['replaceDraft',profile(),None]])
            self.assertEqual(out[0],{'error':'stale_draft'});self.assertIsNotNone(out[1]['value']);self.assertIsNone(out[2]['value']);self.assertIsNone(out[3]['value']);self.assertEqual(out[4]['value'],saved)
    def call(self, root, operations, file_limit=None):
        code = '''$file=$argv[1].'/smartdns-store.php';if(!is_file($file)){echo json_encode(['error'=>'missing_store']);exit;}
        require $file;$now=100.0;$p=json_decode(stream_get_contents(STDIN),true);$s=new AsusSmartDnsStore($argv[2],(int)$argv[3],['boot'=>fn()=>'boot-a','uptime'=>function()use(&$now){return $now;}]);$out=[];
        foreach($p as $op){try{
          if($op[0]==='prepare'){$hash=$s->saveDraft($op[1]);$s->savePreview(['id'=>str_repeat('1',32),'profile_hash'=>$hash,'baseline_hash'=>str_repeat('a',64),'config'=>'fixture','groups'=>[],'overlaps'=>[],'checks'=>[],'expires_uptime'=>$now+600]);$v=$hash;}
          elseif($op[0]==='beginCurrent')$v=$s->begin($op[1],AsusSmartDnsProfile::hash($op[2]),str_repeat('a',64));
          elseif($op[0]==='validateCurrent')$v=$s->beginValidation($op[1],AsusSmartDnsProfile::hash($op[2]),str_repeat('a',64));
          elseif($op[0]==='advance'){$now+=$op[1];$v=$now;}
          else $v=$s->{$op[0]}(...array_slice($op,1));
          $out[]=['value'=>$v];
        }catch(Throwable $e){$out[]=['error'=>$e->getMessage()];}}echo json_encode($out);'''
        def limit_file():
            signal.signal(signal.SIGXFSZ,signal.SIG_IGN)
            resource.setrlimit(resource.RLIMIT_FSIZE,(file_limit,file_limit))
        p = subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(root),str(os.getuid())],
                           input=json.dumps(operations),capture_output=True,text=True,timeout=8,
                           preexec_fn=limit_file if file_limit else None)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'')
        return json.loads(p.stdout)

    def test_stale_profile_and_baseline_rejected(self):
        for mode in ['draft','baseline','expired']:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as d:
                ops = [['prepare',profile()]]
                if mode=='draft':ops += [['saveDraft',profile(upstream(label='new'))]]
                if mode=='expired':ops += [['advance',601]]
                if mode=='baseline':ops += [['begin','b'*32,'c'*64,'d'*64]]
                else:ops += [['beginCurrent','b'*32,profile()]]
                out=self.call(Path(d)/'state',ops)
                self.assertIsInstance(out,list)
                self.assertEqual(out[-1],{'error':'stale_preview'})

    def test_replay_after_lost_response_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            ops=[['prepare',profile()],['beginCurrent','b'*32,profile()],['advance',700],
                 ['beginCurrent','b'*32,profile()],['beginCurrent','b'*32,profile(upstream(label='other'))]]
            out=self.call(Path(d)/'state',ops);self.assertIsInstance(out,list)
            self.assertEqual(out[1],out[3]);self.assertEqual(out[4],{'error':'request_conflict'})
            self.assertEqual(out[1]['value']['state'],'applying')

    def test_parallel_tabs_do_not_replace_live_owner(self):
        with tempfile.TemporaryDirectory() as d:
            out=self.call(Path(d)/'state',[['prepare',profile()],['beginCurrent','b'*32,profile()],
                                          ['advance',900],['beginCurrent','c'*32,profile()]])
            self.assertIsInstance(out,list);self.assertEqual(out[-1],{'error':'busy'})

    def test_pending_backup_survives_rotation(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'state'
            out=self.call(root,[['prepare',profile()],['beginCurrent','b'*32,profile()]]+
                          [['backup',{'marker':i}] for i in range(6)])
            self.assertIsInstance(out,list)
            first=out[2]['value'];self.assertTrue((root/f'backup-{first}.json').is_file())
            backups=list(root.glob('backup-*.json'));self.assertEqual(len(backups),4)
            self.assertEqual(sorted(json.loads(f.read_text())['marker'] for f in backups),[0,3,4,5])

    def test_symlink_hardlink_and_wrong_mode_are_denied(self):
        for mode in ['symlink','hardlink','mode']:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as d:
                root=Path(d)/'state';self.call(root,[['saveDraft',profile()]])
                self.assertTrue(root.is_dir())
                file=root/'draft.json'
                if mode=='mode':file.chmod(0o644)
                else:
                    outside=Path(d)/'outside';outside.write_text('PRIVATE');outside.chmod(0o600)
                    file.unlink()
                    if mode=='symlink':file.symlink_to(outside)
                    else:os.link(outside,file)
                result=self.call(root,[['draft']])
                self.assertEqual(result,[{'error':'invalid_state'}])

    def test_transition_compare_and_swap_and_public_status(self):
        with tempfile.TemporaryDirectory() as d:
            out=self.call(Path(d)/'state',[['prepare',profile()],['beginCurrent','b'*32,profile()],
                ['transition','b'*32,['applying'],{'state':'awaiting_confirmation','deadline_uptime':220}],
                ['transition','b'*32,['applying'],{'state':'confirmed'}],['advance',10],['status']])
            self.assertIsInstance(out,list);self.assertEqual(out[3],{'error':'stale_state'})
            status=out[-1]['value'];self.assertEqual(status['deadline_remaining_s'],110)
            self.assertEqual(status['state'],'awaiting_confirmation')
            self.assertNotIn('profile',status)

    def test_private_files_and_empty_draft_do_not_change_active_profile(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'state';out=self.call(root,[['status'],['saveDraft',profile()],['active']])
            self.assertIsInstance(out,list);self.assertEqual(out[0]['value']['state'],'idle')
            self.assertIsNone(out[-1]['value'])
            self.assertEqual(root.stat().st_mode&0o777,0o700)
            for f in root.iterdir():self.assertEqual(f.stat().st_mode&0o777,0o600)

    def test_failed_partial_write_keeps_previous_draft(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'state';self.call(root,[['saveDraft',profile()]])
            before=(root/'draft.json').read_bytes()
            big=profile(*[upstream('server'+str(i)) for i in range(16)])
            result=self.call(root,[['saveDraft',big]],file_limit=1024)
            self.assertEqual(result,[{'error':'insufficient_space'}])
            self.assertEqual((root/'draft.json').read_bytes(),before)
            self.assertEqual(list(root.glob('.write-*')),[])

    def test_corrupt_journal_is_rejected_without_notices(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'state';self.call(root,[['saveDraft',profile()]])
            state=root/'state.json';state.write_text(json.dumps({'schema_version':1,'history':[],'backups':[]}));state.chmod(0o600)
            self.assertEqual(self.call(root,[['status']]),[{'error':'invalid_state'}])

    def test_validation_claim_precedes_preview_and_is_not_replaced_by_another_tab(self):
        with tempfile.TemporaryDirectory() as d:
            out=self.call(Path(d)/'state',[['saveDraft',profile()],['validateCurrent','b'*32,profile()],
                ['advance',700],['validateCurrent','b'*32,profile()],['validateCurrent','c'*32,profile()]])
            self.assertEqual(out[1]['value']['state'],'validating')
            self.assertEqual(out[1],out[3])
            self.assertEqual(out[-1],{'error':'busy'})

    def test_a_new_validation_invalidates_the_old_preview(self):
        with tempfile.TemporaryDirectory() as d:
            out=self.call(Path(d)/'state',[['prepare',profile()],['validateCurrent','b'*32,profile()],
                                          ['preview','1'*32]])
            self.assertEqual(out[-1],{'error':'stale_preview'})

    def test_corrupt_preview_fields_and_infinite_deadline_are_rejected(self):
        for changed in [{'id':[]},{'profile_hash':[]},{'expires_uptime':'1e999'},{'boot':None}]:
            with self.subTest(changed=changed),tempfile.TemporaryDirectory() as d:
                root=Path(d)/'state';self.call(root,[['prepare',profile()]])
                path=root/'preview.json';v=json.loads(path.read_text());v.update(changed)
                path.write_text(json.dumps(v));path.chmod(0o600)
                self.assertEqual(self.call(root,[['preview','1'*32]]),[{'error':'stale_preview'}])


if __name__=='__main__':unittest.main()

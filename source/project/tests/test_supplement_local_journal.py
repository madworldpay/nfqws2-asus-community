"""New saved portable proposal composed with the existing LOCAL import journal.

This low-level fixture supplies explicit receiver selection/trust facts. It is
not the supplement HTTP Apply path or native-comparison permission.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_dpi_normalize import PHP, PUBLIC
from test_strategy_supplement import BASE, RECIPE, STOCK

BLOB = b'\x00\xffsupplement-local-journal\x00'


class SupplementLocalJournalTests(unittest.TestCase):
    def setUp(self):
        engine = os.environ.get('NFQWS_TEST_ENGINE_DIR')
        self.assertTrue(engine, 'Provide the pinned original Lua fixture bytes')
        artifacts = os.environ.get('NFQWS_SUPPLEMENT_ARTIFACT_DIR')
        if artifacts:
            self.temp = Path(tempfile.mkdtemp(prefix=self._testMethodName+'-', dir=artifacts))
        else:
            tmp = tempfile.TemporaryDirectory()
            self.addCleanup(tmp.cleanup)
            self.temp = Path(tmp.name)
        self.source, self.receiver = self.temp/'source', self.temp/'receiver'
        self.baseline = {}
        self.current = BASE.replace(' --lua-init=@/opt/etc/nfqws2/lua/zapret-antidpi.lua"',
            ' --lua-init=@/opt/etc/nfqws2/lua/zapret-antidpi.lua --blob=owned:@/opt/etc/nfqws2/blobs/custom.bin"')
        self.current = self.current.replace('--lua-desync=multidisorder:pos=2', '--lua-desync=fake:blob=owned')
        for root in (self.source, self.receiver):
            root.mkdir(mode=0o755)
            for kind in ('lua', 'blobs', 'lists'):
                (root/kind).mkdir(mode=0o755)
            for path, expected in list(STOCK.items())[:2]:
                raw = (Path(engine)/'lua'/Path(path).name).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), expected)
                (root/'lua'/Path(path).name).write_bytes(raw)
                self.baseline['lua/'+Path(path).name] = {'bytes': len(raw), 'sha256': expected}
            for name, raw in {'lists/user.list': b'source.example\n', 'lists/auto.list': b'learned.example\n',
                              'lists/exclude.list': b'excluded.example\n', 'blobs/custom.bin': BLOB,
                              'lists/unrelated.list': b'UNRELATED_OWNER_DATA\n'}.items():
                (root/name).write_bytes(raw)
            (root/'nfqws2.conf').write_text(self.current)
            (root/'nfqws2.conf').chmod(0o640)
        (self.receiver/'lists/user.list').write_bytes(b'RECEIVER_ORIGINAL_LIST\n')
        (self.receiver/'lists/user.list').chmod(0o640)
        (self.receiver/'blobs/custom.bin').write_bytes(b'RECEIVER_FOREIGN_BLOB')
        self.count = 0

    def call(self, mode):
        code = r'''require $argv[1].'/import-transaction.php';
        $d=json_decode(stream_get_contents(STDIN),true,32,JSON_THROW_ON_ERROR);$r=$argv[2];$uid=(int)$argv[3];
        $source=new AsusImportTransaction(new AsusImportStore($r.'/source-journal',$uid),new AsusSmartDnsStore($r.'/source-dns',$uid),$r.'/source',$r.'/source/nfqws2.conf',$uid);
        $saved=$source->supplementPortablePreview($d['recipe'],$d['domains'],$source->supplementState()['binding']);
        $doc=AsusImportDocument::read([$saved['portable']['raw']]);$blocks=[];$shared=[];$ports=[];
        foreach($doc['values']as $key=>$value){if(in_array($key,AsusImportConfig::BLOCKS,true))$blocks[]=['key'=>$key,'value'=>$value];else $shared[]=['key'=>$key,'value'=>$value];}
        foreach($doc['ports']as $key=>$value)$ports[]=['key'=>$key,'value'=>$value];
        $selection=['blocks'=>$blocks,'shared'=>$shared,'ports'=>$ports,'files'=>array_map(fn($f)=>['id'=>$f['id']],$doc['resources']),
          'dns'=>[],'allow_shared_impact'=>false,'allow_incomplete'=>false,'trusted_lua'=>false];
        $resources=new AsusShareResources($r.'/receiver',$uid,$d['baseline']);
        $before=file_get_contents($r.'/receiver/nfqws2.conf');
        $plan=AsusImportPlan::prepare($doc,$selection,$before,$resources->inventory(),null,'asus-entware');
        $store=new AsusImportStore($r.'/receiver-journal',$uid);$events=[];$fired=false;
        $deps=['checkpoint'=>function($phase)use($r,$d,$store,&$events,&$fired,$before){
          if($phase==='journal'){
            $j=$store->state()['current'];$backups=[];
            $raw=$store->read($j['id'].'.conf');
            if($raw!==$before)throw new RuntimeException('FIXTURE_BAD_CONFIG_BACKUP');
            $backups[]=['name'=>$j['id'].'.conf','sha256'=>hash('sha256',$raw),'data_base64'=>base64_encode($raw)];
            foreach($j['files']as $i=>$file)if(isset($file['before'])){
              $raw=$store->read($j['id'].'.file-'.$i);
              if(!is_string($raw)||hash('sha256',$raw)!==$file['before'])throw new RuntimeException('FIXTURE_BAD_FILE_BACKUP');
              $backups[]=['name'=>$j['id'].'.file-'.$i,'sha256'=>hash('sha256',$raw),'data_base64'=>base64_encode($raw)];}
            $f=fopen($r.'/receiver-journal/writer.lock','rb');$rival=flock($f,LOCK_EX|LOCK_NB);
            if($rival)flock($f,LOCK_UN);fclose($f);
            $events[]=['phase'=>$phase,'journal'=>$j,'backups'=>$backups,'rival_acquired'=>$rival,
              'config_still_original'=>file_get_contents($r.'/receiver/nfqws2.conf')===$before];
          }else $events[]=['phase'=>$phase];
          if(!$fired&&$d['mode']==='file_failure'&&$phase==='file_0'){$fired=true;throw new RuntimeException('fixture_file_failure');}
          if(!$fired&&$d['mode']==='foreign_config'&&$phase==='committing'){$fired=true;file_put_contents($r.'/receiver/nfqws2.conf',"FOREIGN_CONFIG\n");}
        }];
        $tx=new AsusImportTransaction($store,new AsusSmartDnsStore($r.'/receiver-dns',$uid),$r.'/receiver',$r.'/receiver/nfqws2.conf',$uid,$deps);
        $out=['saved'=>$saved,'plan'=>$plan];$id=str_repeat('a',32);
        try{
          if($d['mode']==='stale_config')file_put_contents($r.'/receiver/nfqws2.conf',$before."# OWNER_EDIT\n");
          if($d['mode']==='stale_AUTO')file_put_contents($r.'/receiver/lists/auto.list',"OWNER_AUTO\n");
          if(!$plan['ready'])throw new RuntimeException('FIXTURE_PLAN_NOT_READY');
          $out['applied']=$tx->apply($plan,$id);
          $out['committed_config_base64']=base64_encode(file_get_contents($r.'/receiver/nfqws2.conf'));
          if($d['mode']==='undo_foreign'){
            foreach($plan['files']as $file)if($file['kind']==='blobs'&&!$file['reuse'])
              file_put_contents($r.'/receiver'.substr($file['path'],strlen('/opt/etc/nfqws2')),"FOREIGN_IMPORTED\n");}
          if($d['mode']==='missing_backup')unlink($r.'/receiver-journal/'.$id.'.conf');
          if(in_array($d['mode'],['normal','undo_foreign','missing_backup'],true))$out['undone']=$tx->undo($id);
        }catch(Throwable $e){$out['error']=$e->getMessage();}
        $out['journal']=$store->state();$out['events']=$events;
        echo json_encode($out,JSON_THROW_ON_ERROR);'''
        request = json.dumps({'mode': mode, 'baseline': self.baseline, 'recipe': RECIPE, 'domains': ['target.example']})
        self.count += 1; prefix = self.temp/str(self.count)
        prefix.with_suffix('.php').write_text(code)
        prefix.with_suffix('.request.json').write_text(request)
        run = subprocess.run([PHP, '-n', '-r', code, str(PUBLIC), str(self.temp), str(os.getuid())],
                             input=request, text=True, capture_output=True, timeout=25)
        prefix.with_suffix('.stdout').write_text(run.stdout)
        prefix.with_suffix('.stderr').write_text(run.stderr)
        self.assertEqual((run.returncode, run.stderr), (0, ''), run.stdout+run.stderr)
        return json.loads(run.stdout)

    def unchanged(self):
        paths = ['lua/zapret-lib.lua', 'lua/zapret-antidpi.lua', 'lists/auto.list',
                 'lists/exclude.list', 'lists/unrelated.list', 'blobs/custom.bin']
        return {name: (hashlib.sha256((self.receiver/name).read_bytes()).hexdigest(),
            tuple(getattr((self.receiver/name).stat(), k) for k in (
                'st_dev', 'st_ino', 'st_mode', 'st_nlink', 'st_uid', 'st_gid', 'st_size', 'st_mtime_ns', 'st_ctime_ns')))
            for name in paths}

    def assert_original(self):
        self.assertEqual((self.receiver/'nfqws2.conf').read_text(), self.current)
        self.assertEqual((self.receiver/'nfqws2.conf').stat().st_mode & 0o777, 0o640)
        self.assertEqual((self.receiver/'lists/user.list').read_bytes(), b'RECEIVER_ORIGINAL_LIST\n')
        self.assertEqual((self.receiver/'lists/user.list').stat().st_mode & 0o777, 0o640)
        self.assertFalse((self.receiver/'blobs/imported').exists())
        self.assertFalse(list(self.receiver.rglob('.import-*')))

    def test_saved_portable_commit_undo_backups_and_owned_hash_rebind(self):
        before = self.unchanged(); out = self.call('normal')
        self.assertNotIn('error', out, out.get('error'))
        self.assertEqual(out['applied']['state'], 'committed')
        self.assertEqual(out['undone']['state'], 'undone')
        journal = next(e for e in out['events'] if e['phase'] == 'journal')
        self.assertFalse(journal['rival_acquired']); self.assertTrue(journal['config_still_original'])
        self.assertEqual(len(journal['backups']), 2)
        for backup in journal['backups']:
            raw = base64.b64decode(backup['data_base64'])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), backup['sha256'])
            self.assertEqual((self.temp/'receiver-journal'/backup['name']).read_bytes(), raw)
            self.assertEqual((self.temp/'receiver-journal'/backup['name']).stat().st_mode & 0o777, 0o600)
        committed = base64.b64decode(out['committed_config_base64'])
        self.assertEqual(committed, out['plan']['config'].encode())
        self.assertIn(('/blobs/imported/'+hashlib.sha256(BLOB).hexdigest()+'.bin').encode(), committed)
        # Receiver operand rebinding changes the actual trial input. The source
        # comparison binding must never be carried across this as native proof.
        self.assertNotEqual(hashlib.sha256(committed).hexdigest(), out['saved']['comparison_binding']['combined_config_sha256'])
        self.assertFalse(out['saved']['can_apply']); self.assertFalse(out['saved']['combined_verified'])
        self.assert_original(); self.assertEqual(self.unchanged(), before)
        self.assertFalse((self.temp/'source-dns').exists()); self.assertFalse((self.temp/'receiver-dns').exists())

    def test_failure_after_first_published_resource_rolls_back_new_composition(self):
        before = self.unchanged(); out = self.call('file_failure')
        self.assertEqual(out.get('error'), 'fixture_file_failure', out.get('error'))
        self.assertEqual(out['journal']['current']['state'], 'rolled_back')
        self.assert_original(); self.assertEqual(self.unchanged(), before)

    def test_foreign_config_during_commit_is_preserved_with_attention(self):
        before = self.unchanged(); out = self.call('foreign_config')
        self.assertEqual(out.get('error'), 'restore_required', out.get('error'))
        self.assertEqual(out['journal']['current']['state'], 'restore_required')
        self.assertEqual((self.receiver/'nfqws2.conf').read_bytes(), b'FOREIGN_CONFIG\n')
        self.assertEqual(self.unchanged(), before)
        self.assertTrue((self.temp/'receiver-journal'/('a'*32+'.conf')).exists())

    def test_precommit_config_or_AUTO_CAS_refuses_before_backup_journal(self):
        for mode in ('stale_config', 'stale_AUTO'):
            with self.subTest(mode=mode):
                out = self.call(mode)
                self.assertEqual(out.get('error'), 'source_changed', out.get('error'))
                self.assertIsNone(out['journal']['current'])
                self.assertFalse((self.temp/'receiver-journal'/('a'*32+'.conf')).exists())
                self.assertEqual(out['events'], [])

    def test_undo_preserves_foreign_imported_bytes_and_committed_config(self):
        before = self.unchanged(); out = self.call('undo_foreign')
        self.assertEqual(out.get('error'), 'source_changed', out.get('error'))
        self.assertEqual(out['journal']['current']['state'], 'committed')
        self.assertEqual((self.receiver/'nfqws2.conf').read_bytes(), base64.b64decode(out['committed_config_base64']))
        imported = self.receiver/'blobs/imported'/(hashlib.sha256(BLOB).hexdigest()+'.bin')
        self.assertEqual(imported.read_bytes(), b'FOREIGN_IMPORTED\n')
        self.assertEqual(self.unchanged(), before)

    def test_missing_original_backup_never_reports_successful_undo(self):
        before = self.unchanged(); out = self.call('missing_backup')
        self.assertEqual(out.get('error'), 'invalid_state', out.get('error'))
        self.assertEqual(out['journal']['current']['state'], 'restore_required')
        self.assertNotIn('undone', out)
        self.assertEqual((self.receiver/'nfqws2.conf').read_bytes(), base64.b64decode(out['committed_config_base64']))
        self.assertEqual(self.unchanged(), before)


if __name__ == '__main__':
    unittest.main()

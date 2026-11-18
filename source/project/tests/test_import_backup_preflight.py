"""All original journal backups must pass before publication or restoration.

Actual LOCAL importer/compiler/store/files; faults affect owned fixture backups.
No service, native engine, AUTO mutation, device or public API is invoked.
"""
import base64, hashlib, json, os, subprocess, tempfile, unittest
from pathlib import Path
from test_dpi_normalize import PHP, PUBLIC

CURRENT = '# owner settings\nISP_INTERFACE="eth9"\nNFQWS_BASE_ARGS=""\nNFQWS_ARGS="--filter-tcp=80"\n'


class ImportBackupPreflightTests(unittest.TestCase):
    def call(self, mode):
        root = Path(tempfile.mkdtemp(prefix=self._testMethodName+'-', dir=os.environ['NFQWS_SUPPLEMENT_ARTIFACT_DIR']))
        resources = root/'resources'; resources.mkdir(mode=0o755)
        for kind in ('lists','lua','blobs'): (resources/kind).mkdir(mode=0o755)
        (resources/'nfqws2.conf').write_text(CURRENT); (resources/'nfqws2.conf').chmod(0o640)
        rows=[]
        for i in range(2):
            name=f'original-{i}.list'; raw=f'NEW_{i}\n'.encode()
            (resources/'lists'/name).write_bytes(f'OLD_{i}\n'.encode()); (resources/'lists'/name).chmod(0o640)
            sha=hashlib.sha256(raw).hexdigest()
            rows.append(dict(id=str(i+1)*32,kind='lists',name=name,encoding='utf8',source_sha256=sha,
                sha256=sha,byte_length=len(raw),data_base64=base64.b64encode(raw).decode(),aliases=[]))
        strategy=dict(type='nfqws2_strategy',schema_version=1,versions=dict(core='unverified',web='local'),
            purpose='Backup preflight LOCAL',operator='Fixture',comment='',mode='blocks',
            blocks=[dict(key='NFQWS_ARGS',value='--filter-tcp=443')],dependencies=[])
        resource_doc=dict(type='nfqws2_resources',schema_version=1,context=dict(purpose='Local',operator='Fixture',comment=''),
            files=rows,audit=dict(scope='files_only',references=[],unresolved=[],missing_reason='',complete=True))
        selection=dict(blocks=strategy['blocks'],shared=[],ports=[],files=[dict(id=r['id'])for r in rows],dns=[],
            allow_shared_impact=False,allow_incomplete=False,trusted_lua=False)
        code=r'''require $argv[1].'/import-transaction.php';
        $d=json_decode(stream_get_contents(STDIN),true,32,JSON_THROW_ON_ERROR);$r=$argv[2];$uid=(int)$argv[3];$id=str_repeat('a',32);
        $s=new AsusImportStore($r.'/journal',$uid);$events=[];$fired=false;$out=[];
        $checkpoint=function($phase)use($r,$d,$s,$id,&$events,&$fired){
            if($d['mode']==='buffered_delete'&&$phase==='undo_config')unlink($r.'/journal/'.$id.'.file-1');
            $f=fopen($r.'/journal/writer.lock','rb');$rival=flock($f,LOCK_EX|LOCK_NB);if($rival)flock($f,LOCK_UN);fclose($f);
            $events[]=['phase'=>$phase,'rival_acquired'=>$rival];
            $fault=['journal_missing'=>'journal','committing_corrupt'=>'committing','rollback_missing'=>'file_0','recover_missing'=>'config'][$d['mode']]??null;
            if(!$fired&&$phase===$fault){$fired=true;$p=$r.'/journal/'.$id.'.file-1';
                if($d['mode']==='committing_corrupt')file_put_contents($p,'CORRUPT_BACKUP');else unlink($p);
                if($d['mode']==='rollback_missing'||$d['mode']==='recover_missing')throw new RuntimeException('fixture_abort');
            }
        };
        $t=new AsusImportTransaction($s,new AsusSmartDnsStore($r.'/dns',$uid),$r.'/resources',$r.'/resources/nfqws2.conf',$uid,['checkpoint'=>$checkpoint]);
        $p=$t->prepare($d['documents'],$d['selection']);if(!$p['ready'])throw new RuntimeException('FIXTURE_PLAN_NOT_READY');$out['plan']=$p;
        try{$out['applied']=$t->apply($p,$id);
            if($d['mode']==='undo_missing')unlink($r.'/journal/'.$id.'.file-1');
            if($d['mode']==='undo_corrupt')file_put_contents($r.'/journal/'.$id.'.file-1','CORRUPT_BACKUP');
            if(in_array($d['mode'],['normal','undo_missing','undo_corrupt','buffered_delete'],true))$out['undone']=$t->undo($id);
        }catch(Throwable $e){$out['error']=$e->getMessage();}
        $f=fopen($r.'/journal/writer.lock','rb');$out['lock_free_after']=flock($f,LOCK_EX|LOCK_NB);if($out['lock_free_after'])flock($f,LOCK_UN);fclose($f);
        $files=[];foreach(scandir($r.'/journal')as $name)if($name!=='.'&&$name!=='..')$files[$name]=['raw_base64'=>base64_encode(file_get_contents($r.'/journal/'.$name)),'metadata'=>lstat($r.'/journal/'.$name)];
        echo json_encode($out+['state'=>$s->state(),'events'=>$events,'backups'=>$files,
            'config_base64'=>base64_encode(file_get_contents($r.'/resources/nfqws2.conf')),
            'lists'=>[file_get_contents($r.'/resources/lists/original-0.list'),file_get_contents($r.'/resources/lists/original-1.list')]],JSON_THROW_ON_ERROR);'''
        request=json.dumps(dict(mode=mode,documents=[json.dumps(strategy),json.dumps(resource_doc)],selection=selection)).encode()
        (root/'php-r.private').write_text(code);(root/'request.private.json').write_bytes(request)
        p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(root),str(os.getuid())],input=request,capture_output=True,timeout=25)
        (root/'stdout.private').write_bytes(p.stdout);(root/'stderr.private').write_bytes(p.stderr)
        self.assertEqual((p.returncode,p.stderr),(0,b''),p.stdout.decode()+p.stderr.decode());v=json.loads(p.stdout)
        self.assertTrue(v['lock_free_after']);self.assertTrue(v['events']);self.assertTrue(all(e['rival_acquired']is False for e in v['events']))
        return v,root

    def attention(self,v,config,lists):
        self.assertEqual(v['state']['current']['state'],'restore_required',v)
        self.assertNotIn('undone',v);self.assertEqual(base64.b64decode(v['config_base64']),config)
        self.assertEqual(v['lists'],lists)

    def test_missing_later_backup_refuses_undo_before_config_or_first_resource_restore(self):
        v,r=self.call('undo_missing');self.attention(v,v['plan']['config'].encode(),['NEW_0\n','NEW_1\n'])

    def test_corrupt_later_backup_is_preserved_without_partial_undo(self):
        v,r=self.call('undo_corrupt');self.attention(v,v['plan']['config'].encode(),['NEW_0\n','NEW_1\n'])
        self.assertEqual((r/'journal'/('a'*32+'.file-1')).read_bytes(),b'CORRUPT_BACKUP')

    def test_missing_backup_after_prepared_journal_refuses_before_first_resource_write(self):
        v,r=self.call('journal_missing');self.attention(v,CURRENT.encode(),['OLD_0\n','OLD_1\n'])
        self.assertFalse(any(e['phase'].startswith('stage_')for e in v['events']))

    def test_corrupt_backup_before_config_commit_preserves_original_config_and_published_files(self):
        v,r=self.call('committing_corrupt');self.attention(v,CURRENT.encode(),['NEW_0\n','NEW_1\n'])
        self.assertNotIn('applied',v)

    def test_failed_rollback_validates_even_later_original_before_restoring_first_file(self):
        v,r=self.call('rollback_missing');self.attention(v,CURRENT.encode(),['NEW_0\n','OLD_1\n'])

    def test_recovery_cannot_accept_committing_state_with_missing_original(self):
        v,r=self.call('recover_missing');self.attention(v,v['plan']['config'].encode(),['NEW_0\n','NEW_1\n'])
        self.assertNotIn('applied',v)

    def test_valid_complete_original_set_still_commits_and_restores_under_same_writer(self):
        v,r=self.call('normal');self.assertNotIn('error',v,v.get('error'));self.assertEqual(v['applied']['state'],'committed');self.assertEqual(v['undone']['state'],'undone')
        self.assertEqual(base64.b64decode(v['config_base64']),CURRENT.encode());self.assertEqual(v['lists'],['OLD_0\n','OLD_1\n'])
        for i in range(2):self.assertEqual((r/'journal'/('a'*32+f'.file-{i}')).read_bytes(),f'OLD_{i}\n'.encode())


    def test_restore_uses_verified_buffer_if_later_backup_disappears_after_validation(self):
        v,r=self.call('buffered_delete');self.assertNotIn('error',v,v.get('error'));self.assertEqual(v['undone']['state'],'undone')
        self.assertEqual(base64.b64decode(v['config_base64']),CURRENT.encode());self.assertEqual(v['lists'],['OLD_0\n','OLD_1\n'])
        self.assertFalse((r/'journal'/('a'*32+'.file-1')).exists())

    def dns_case(self, corrupt):
        root=Path(tempfile.mkdtemp(prefix=self._testMethodName+'-',dir=os.environ['NFQWS_SUPPLEMENT_ARTIFACT_DIR']))
        resources=root/'resources';resources.mkdir(mode=0o755)
        for kind in ('lists','lua','blobs'):(resources/kind).mkdir(mode=0o755)
        (resources/'nfqws2.conf').write_text(CURRENT)
        code=r'''require $argv[1].'/import-transaction.php';$d=json_decode(stream_get_contents(STDIN),true,32,JSON_THROW_ON_ERROR);
        $r=$argv[2];$uid=(int)$argv[3];$id=str_repeat('b',32);$store=new AsusImportStore($r.'/journal',$uid);$dns=new AsusSmartDnsStore($r.'/dns',$uid);
        $u=['id'=>'quad9','label'=>'Quad9','protocol'=>'dot','address'=>'9.9.9.9','port'=>853,'tls_name'=>'dns.quad9.net','url'=>'','bootstrap'=>[],'default'=>true,'domains'=>[]];
        $before=['schema_version'=>1,'upstreams'=>[$u],'records'=>[]];$dns->saveDraft($before);$before=$dns->draft();$u['domains']=[['name'=>'target.example','include_subdomains'=>true]];
        $profile=['schema_version'=>1,'upstreams'=>[$u],'records'=>[]];$sha=str_repeat('a',64);
        $doc=['type'=>'nfqws2_dns','schema_version'=>1,'context'=>['purpose'=>'Local','operator'=>'Fixture','comment'=>''],
            'sources'=>[['id'=>'legacy','origin'=>'legacy','sha256'=>$sha,'profile'=>$profile,'complete'=>true,'warnings'=>[],'scope'=>'upstreams_and_domain_rules']]];
        $selection=['blocks'=>[],'shared'=>[],'ports'=>[],'files'=>[],'dns'=>[['source_id'=>'legacy','source_sha256'=>$sha,'upstreams'=>[$u],'records'=>[]]],'allow_shared_impact'=>false,'allow_incomplete'=>false,'trusted_lua'=>false];
        $t=new AsusImportTransaction($store,$dns,$r.'/resources',$r.'/resources/nfqws2.conf',$uid);$p=$t->prepare([json_encode($doc,JSON_THROW_ON_ERROR)],$selection);
        if(!$p['ready'])throw new RuntimeException('FIXTURE_DNS_PLAN_NOT_READY');$out=['plan'=>$p,'original_draft'=>$before];
        try{$out['applied']=$t->apply($p,$id);$out['committed_draft']=$dns->draft();
            if($d['corrupt'])file_put_contents($r.'/journal/'.$id.'.draft','{"INVALID":"BACKUP"}');
            $out['undone']=$t->undo($id);
        }catch(Throwable $e){$out['error']=$e->getMessage();}
        $f=fopen($r.'/journal/writer.lock','rb');$out['lock_free_after']=flock($f,LOCK_EX|LOCK_NB);if($out['lock_free_after'])flock($f,LOCK_UN);fclose($f);
        echo json_encode($out+['state'=>$store->state(),'final_draft'=>$dns->draft(),'config'=>file_get_contents($r.'/resources/nfqws2.conf')],JSON_THROW_ON_ERROR);'''
        request=json.dumps(dict(corrupt=corrupt)).encode();(root/'php-r.private').write_text(code);(root/'request.private.json').write_bytes(request)
        q=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(root),str(os.getuid())],input=request,capture_output=True,timeout=25)
        (root/'stdout.private').write_bytes(q.stdout);(root/'stderr.private').write_bytes(q.stderr)
        self.assertEqual((q.returncode,q.stderr),(0,b''),q.stdout.decode()+q.stderr.decode());v=json.loads(q.stdout);self.assertTrue(v['lock_free_after']);self.assertEqual(v['config'],CURRENT)
        return v,root

    def test_complete_valid_DNS_original_is_checked_and_restored_as_draft_only(self):
        v,r=self.dns_case(False);self.assertNotIn('error',v,v.get('error'));self.assertEqual(v['undone']['state'],'undone')
        self.assertNotEqual(v['committed_draft'],v['original_draft']);self.assertEqual(v['final_draft'],v['original_draft'])

    def test_invalid_DNS_original_preserves_committed_draft_and_requires_attention(self):
        v,r=self.dns_case(True);self.assertEqual(v['state']['current']['state'],'restore_required');self.assertNotIn('undone',v)
        self.assertEqual(v['final_draft'],v['committed_draft']);self.assertEqual((r/'journal'/('b'*32+'.draft')).read_text(),'{"INVALID":"BACKUP"}')


if __name__=='__main__':unittest.main()

"""New journal backups retain source-observed identity; old journals stay legacy.

Actual LOCAL original importer/store, with owned backup-file fault injection.
"""
import base64, hashlib, json, os, subprocess, tempfile, unittest
from pathlib import Path
from test_dpi_normalize import PHP, PUBLIC

CURRENT='ISP_INTERFACE="eth9"\nNFQWS_BASE_ARGS=""\nNFQWS_ARGS="--filter-tcp=80"\n'


class ImportBackupIdentityTests(unittest.TestCase):
    def call(self,mode):
        root=Path(tempfile.mkdtemp(prefix=self._testMethodName+'-',dir=os.environ['NFQWS_SUPPLEMENT_ARTIFACT_DIR']))
        resources=root/'resources';resources.mkdir(mode=0o755)
        for kind in ('lists','lua','blobs'):(resources/kind).mkdir(mode=0o755)
        (resources/'nfqws2.conf').write_text(CURRENT);(resources/'lists/original.list').write_bytes(b'ORIGINAL\n');(resources/'lists/original.list').chmod(0o640)
        raw=b'NEW\n';sha=hashlib.sha256(raw).hexdigest();row=dict(id='1'*32,kind='lists',name='original.list',encoding='utf8',source_sha256=sha,sha256=sha,byte_length=len(raw),data_base64=base64.b64encode(raw).decode(),aliases=[])
        strategy=dict(type='nfqws2_strategy',schema_version=1,versions=dict(core='unverified',web='local'),purpose='Local',operator='Fixture',comment='',mode='blocks',blocks=[dict(key='NFQWS_ARGS',value='--filter-tcp=443')],dependencies=[])
        resdoc=dict(type='nfqws2_resources',schema_version=1,context=dict(purpose='Local',operator='Fixture',comment=''),files=[row],audit=dict(scope='files_only',references=[],unresolved=[],missing_reason='',complete=True))
        selection=dict(blocks=strategy['blocks'],shared=[],ports=[],files=[dict(id=row['id'])],dns=[],allow_shared_impact=False,allow_incomplete=False,trusted_lua=False)
        code=r'''require $argv[1].'/import-transaction.php';$d=json_decode(stream_get_contents(STDIN),true,32,JSON_THROW_ON_ERROR);
        $r=$argv[2];$u=(int)$argv[3];$id=str_repeat('a',32);$s=new AsusImportStore($r.'/journal',$u);$journal=null;$rival=null;
        $tx=new AsusImportTransaction($s,new AsusSmartDnsStore($r.'/dns',$u),$r.'/resources',$r.'/resources/nfqws2.conf',$u,
            ['checkpoint'=>function($phase)use($s,$r,&$journal,&$rival){if($phase==='journal'){$journal=$s->state()['current'];$f=fopen($r.'/journal/writer.lock','rb');$rival=flock($f,LOCK_EX|LOCK_NB);if($rival)flock($f,LOCK_UN);fclose($f);}}]);
        $p=$tx->prepare($d['documents'],$d['selection']);if(!$p['ready'])throw new RuntimeException('FIXTURE_PLAN_NOT_READY');$out=['plan'=>$p];
        try{$out['applied']=$tx->apply($p,$id);$out['committed_state']=$s->state();
            $name=$id.($d['mode']==='swap_config'?'.conf':'.file-0');$path=$r.'/journal/'.$name;$out['target_before']=lstat($path);
            if(in_array($d['mode'],['swap_config','swap_file'],true)){rename($path,$path.'.displaced');copy($path.'.displaced',$path);chmod($path,0600);}
            if($d['mode']==='touch_backup')touch($path,1234567890);
            if(in_array($d['mode'],['missing_pair','extra_manifest','legacy'],true)){
                $state=$s->state();
                if($d['mode']==='missing_pair')unset($state['current']['backups']);
                elseif($d['mode']==='extra_manifest')$state['current']['backups']['unexpected']=['dev'=>0];
                else{unset($state['current']['backup_binding_version'],$state['current']['backups']);}
                $s->save($state);
            }
            $out['undone']=$tx->undo($id);
        }catch(Throwable $e){$out['error']=$e->getMessage();}
        try{$out['state']=$s->state();}catch(Throwable $e){$out['state_error']=$e->getMessage();}
        $pin=null;$raw=$s->read($id.'.conf',262144,$pin);$f=fopen($r.'/journal/writer.lock','rb');$out['lock_free_after']=flock($f,LOCK_EX|LOCK_NB);if($out['lock_free_after'])flock($f,LOCK_UN);fclose($f);
        $named=[];foreach(['conf','file-0']as $tail){$path=$r.'/journal/'.$id.'.'.$tail;clearstatcache(true,$path);$named[$id.'.'.$tail]=lstat($path);}
        echo json_encode($out+['prepared_journal'=>$journal,'rival_acquired'=>$rival,'read_pin'=>$pin,'named'=>$named,
            'config'=>file_get_contents($r.'/resources/nfqws2.conf'),'list'=>file_get_contents($r.'/resources/lists/original.list')],JSON_THROW_ON_ERROR);'''
        request=json.dumps(dict(mode=mode,documents=[json.dumps(strategy),json.dumps(resdoc)],selection=selection)).encode()
        (root/'php-r.private').write_text(code);(root/'request.private.json').write_bytes(request)
        p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(root),str(os.getuid())],input=request,capture_output=True,timeout=25)
        (root/'stdout.private').write_bytes(p.stdout);(root/'stderr.private').write_bytes(p.stderr)
        self.assertEqual((p.returncode,p.stderr),(0,b''),p.stdout.decode()+p.stderr.decode());v=json.loads(p.stdout);self.assertTrue(v['lock_free_after']);self.assertIs(v['rival_acquired'],False)
        return v,root

    def test_new_journal_pins_complete_actual_backup_inode_metadata(self):
        v,r=self.call('normal');j=v['prepared_journal'];self.assertEqual(j.get('backup_binding_version'),1)
        self.assertEqual(set(j['backups']),{'a'*32+'.conf','a'*32+'.file-0'})
        for name,pin in j['backups'].items():self.assertEqual(pin,{k:v['named'][name][k]for k in ['dev','ino','mode','uid','gid','nlink','size','mtime','ctime']})
        self.assertEqual(v['undone']['state'],'undone');self.assertEqual(v['config'],CURRENT);self.assertEqual(v['list'],'ORIGINAL\n')

    def test_guarded_read_option_returns_exact_full_pin(self):
        v,r=self.call('normal');self.assertEqual(v['read_pin'],{k:v['named']['a'*32+'.conf'][k]for k in ['dev','ino','mode','uid','gid','nlink','size','mtime','ctime']})

    def assert_attention(self,v):
        self.assertNotIn('undone',v);self.assertEqual(v['state']['current']['state'],'restore_required')
        self.assertEqual(v['config'],v['plan']['config']);self.assertEqual(v['list'],'NEW\n')

    def test_same_bytes_config_backup_inode_replacement_is_preserved_and_refused(self):
        v,r=self.call('swap_config');self.assert_attention(v);p=r/'journal'/('a'*32+'.conf')
        self.assertEqual(p.read_bytes(),p.with_name(p.name+'.displaced').read_bytes());self.assertNotEqual(v['target_before']['ino'],v['named'][p.name]['ino'])

    def test_same_bytes_resource_backup_inode_replacement_prevents_partial_restore(self):
        v,r=self.call('swap_file');self.assert_attention(v);p=r/'journal'/('a'*32+'.file-0')
        self.assertEqual(p.read_bytes(),b'ORIGINAL\n');self.assertEqual(p.with_name(p.name+'.displaced').read_bytes(),b'ORIGINAL\n')

    def test_changed_backup_timestamp_is_preserved_and_refused(self):
        v,r=self.call('touch_backup');self.assert_attention(v);self.assertEqual(v['named']['a'*32+'.file-0']['mtime'],1234567890)

    def test_unpaired_or_extra_manifest_cannot_downgrade_new_journal(self):
        for mode in ['missing_pair','extra_manifest']:
            with self.subTest(mode=mode):
                v,r=self.call(mode);self.assertNotIn('undone',v);self.assertEqual(v.get('state_error'),'invalid_state')
                self.assertEqual(v['config'],v['plan']['config']);self.assertEqual(v['list'],'NEW\n')

    def test_explicit_legacy_without_both_fields_keeps_content_only_compatibility(self):
        v,r=self.call('legacy');self.assertNotIn('error',v,v.get('error'));self.assertEqual(v['undone']['state'],'undone');self.assertEqual(v['config'],CURRENT);self.assertEqual(v['list'],'ORIGINAL\n')


    def test_DNS_backup_pin_is_complete_and_actual_with_existing_draft_fixture(self):
        from test_import_backup_preflight import ImportBackupPreflightTests
        for corrupt in [False,True]:
            with self.subTest(corrupt=corrupt):
                v,r=ImportBackupPreflightTests.dns_case(self,corrupt)
                j=v['state']['current'];self.assertEqual(j.get('backup_binding_version'),1)
                self.assertEqual(set(j['backups']),{'b'*32+'.conf','b'*32+'.draft'})
                if corrupt:
                    self.assertEqual(j['state'],'restore_required');self.assertNotIn('undone',v);self.assertEqual(v['final_draft'],v['committed_draft'])
                    self.assertEqual((r/'journal'/('b'*32+'.draft')).read_text(),'{"INVALID":"BACKUP"}')
                else:
                    self.assertEqual(j['state'],'undone');self.assertEqual(v['final_draft'],v['original_draft'])
                    for name,pin in j['backups'].items():
                        s=(r/'journal'/name).stat();actual=dict(dev=s.st_dev,ino=s.st_ino,mode=s.st_mode,uid=s.st_uid,gid=s.st_gid,nlink=s.st_nlink,size=s.st_size,mtime=s.st_mtime_ns//1000000000,ctime=s.st_ctime_ns//1000000000)
                        self.assertEqual(pin,actual)


if __name__=='__main__':unittest.main()

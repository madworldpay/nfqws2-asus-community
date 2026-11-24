"""Real local Import API commits for Avatar; never starts an engine or service.

Run with a safe ordinary-owner TMPDIR and NFQWS_SUPPLEMENT_ARTIFACT_DIR.
Only the package-profile selector's fixture-owner argument is bound in an
isolated PHP copy; all API, journal, CAS, inventory and file writers are real.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from test_dpi_normalize import PHP, PUBLIC, ROOT


class AvatarPackApplyTests(unittest.TestCase):
    def run_profile(self, profile):
        artifact = os.environ.get('NFQWS_SUPPLEMENT_ARTIFACT_DIR')
        if not artifact:
            self.skipTest('requires owned artifact fixture directory and ordinary filesystem UID view')
        artifact = Path(artifact)
        self.assertTrue(artifact.is_dir())
        self.assertEqual(artifact.stat().st_uid, os.getuid())
        root = Path(tempfile.mkdtemp(prefix='avatar-apply-'+profile+'-', dir=artifact))
        public = root/'package/project/webui/web/public'
        public.mkdir(parents=True, mode=0o755)
        for source in PUBLIC.glob('*.php'):
            shutil.copyfile(source, public/source.name)
        shutil.copytree(PUBLIC/'zapret2-pack', public/'zapret2-pack')
        shutil.copytree(ROOT/'support', root/'package/project/support')
        # Actual packaged profile selection and path translation, with the
        # ordinary fixture owner's UID rather than root-only installation UID.
        platform = public/'platform.php'
        text = platform.read_text()
        self.assertEqual(text.count('self::readProfile($file);'), 1)
        platform.write_text(text.replace('self::readProfile($file);',
                                        'self::readProfile($file, fileowner(__DIR__));'))
        (public/'platform-profile.json').write_text(json.dumps({'schema_version':1,'platform':profile}))
        (public/'platform-profile.json').chmod(0o600)
        packaged = {}
        pool = json.loads((PUBLIC/'zapret2-pack/resources.json').read_bytes())
        with tarfile.open(ROOT.parent/'sources/zapret2-038c97e5.tar.gz') as archive:
            for name in ['zapret-lib.lua','zapret-antidpi.lua']:
                raw = archive.extractfile(next(n for n in archive.getnames() if n.endswith('/lua/'+name))).read()
                pin = next(row for row in pool.values() if row['name']==name)
                self.assertEqual(hashlib.sha256(raw).hexdigest(), pin['sha256'])
                self.assertEqual(len(raw), pin['byte_length'])
                packaged[name] = raw
        rows = json.loads((PUBLIC/'zapret2-pack/collections.json').read_bytes())['entries']
        cases = []
        for row in rows:
            case = root/row['source_id'];resources=case/'resources'
            for kind in ['lua','blobs','lists']:
                (resources/kind).mkdir(parents=True, mode=0o755)
            manifest = {}
            for name, raw in packaged.items():
                path = resources/'lua'/name;path.write_bytes(raw);path.chmod(0o644)
                manifest['lua/'+name]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
            user_files = {'lists/auto.list':b'owner.example.org\n',
                          'blobs/owner.bin':b'\0owner fixture\xff',
                          'lua/owner-helper.lua':b'-- owner fixture; not loaded\n'}
            for relative, raw in user_files.items():
                (resources/relative).write_bytes(raw);(resources/relative).chmod(0o644)
            before=('# fixture owner\nISP_INTERFACE="eth9"\nASUS_CLIENTS4="192.0.2.9"\n'
                    'USER="nobody"\nNFQUEUE_NUM="321"\nLOG_LEVEL="0"\n'
                    'TCP_PORTS="80"\nUDP_PORTS=""\nNFQWS_BASE_ARGS=""\n'
                    'NFQWS_ARGS="--filter-tcp=80 --lua-desync=pass"\n'
                    'NFQWS_ARGS_CUSTOM=""\nNFQWS_ARGS_QUIC=""\nNFQWS_ARGS_UDP=""\n'
                    'NFQWS_EXTRA_ARGS=""\nNFQWS_ARGS_IPSET=""\n')
            (resources/'nfqws2.conf').write_text(before);(resources/'nfqws2.conf').chmod(0o600)
            cases.append({'id':row['id'],'source_id':row['source_id'],'root':str(case),
                          'before':before,'manifest':manifest})
        code=r'''require $argv[1].'/import-api.php';$v=json_decode(stream_get_contents(STDIN),true,32,JSON_THROW_ON_ERROR);$u=(int)$argv[2];$out=[];
        function resourcesSnapshot(string $root):array{
            $out=[];$it=new RecursiveIteratorIterator(new RecursiveDirectoryIterator($root,FilesystemIterator::SKIP_DOTS));
            foreach($it as $file){$path=$file->getPathname();$name=substr($path,strlen($root)+1);if($name==='nfqws2.conf')continue;
                clearstatcache(true,$path);$s=lstat($path);$out[$name]=['sha256'=>hash_file('sha256',$path)]+array_intersect_key($s,array_flip(['dev','ino','mode','uid','gid','nlink','size','mtime','ctime']));}
            ksort($out);return $out;
        }
        foreach($v['cases']as $case){$r=$case['root'];$config=$r.'/resources/nfqws2.conf';$store=new AsusImportStore($r.'/journal',$u);$dns=new AsusSmartDnsStore($r.'/dns',$u);
            $resources=new AsusShareResources($r.'/resources',$u,$case['manifest']);
            $tx=new AsusImportTransaction($store,$dns,$r.'/resources',$config,$u,['resources'=>$resources]);
            // The global updater boundary is isolated. The actual shared import
            // mutex, durable journal and ordinary API mutation path remain active.
            $api=new AsusImportApi($tx,fn()=>null,$dns);$key=str_repeat('f',64);$now=1000;$csrf=['csrf_token'=>'fixture'];
            try{
                $loaded=$api->handle(['cmd'=>'importlocalentry','entry'=>$case['id']]+$csrf,$key,$now);
                $docs=$loaded['documents'];$doc=$api->handle(['cmd'=>'importinspect','documents'=>json_encode($docs)]+$csrf,$key,$now);
                $selection=['blocks'=>[],'shared'=>[],'ports'=>[],'files'=>[],'dns'=>[],'trusted_lua'=>false,'allow_shared_impact'=>true,'allow_incomplete'=>false];
                foreach($doc['values']as $k=>$value){$area=in_array($k,AsusImportConfig::BLOCKS,true)?'blocks':'shared';$selection[$area][]=['key'=>$k,'value'=>$value];}
                foreach($doc['ports']as $k=>$value)$selection['ports'][]=['key'=>$k,'value'=>$value];
                $post=['documents'=>json_encode($docs),'selection'=>json_encode($selection)]+$csrf;
                $beforeResources=resourcesSnapshot($r.'/resources');$p=$api->handle(['cmd'=>'importprepare']+$post,$key,$now);
                $prepareUnchanged=file_get_contents($config)===$case['before']&&resourcesSnapshot($r.'/resources')===$beforeResources;
                file_put_contents($config,$case['before'].'# operator changed after preview'.PHP_EOL);
                $edited=file_get_contents($config);$stale=null;
                try{$api->handle(['cmd'=>'importapply','proof'=>$p['proof'],'request_id'=>str_repeat('a',32)]+$post,$key,$now);}catch(Throwable $e){$stale=$e->getMessage();}
                $staleUnchanged=file_get_contents($config)===$edited&&resourcesSnapshot($r.'/resources')===$beforeResources;
                file_put_contents($config,$case['before']);
                $p=$api->handle(['cmd'=>'importprepare']+$post,$key,$now);
                $applyPost=['cmd'=>'importapply','proof'=>$p['proof'],'request_id'=>str_repeat('b',32)]+$post;
                $applied=$api->handle($applyPost,$key,$now);$saved=file_get_contents($config);clearstatcache(true,$config);$firstStat=lstat($config);
                $journalBefore=$store->state();$repeated=$api->handle($applyPost,$key,$now);clearstatcache(true,$config);$secondStat=lstat($config);
                $status=$api->handle(['cmd'=>'importstatus']+$csrf,$key,$now);
                $out[$case['source_id']]=['profile'=>NfqwsPlatform::current(),'prepare_ready'=>$p['ready'],'proof_issued'=>is_string($p['proof']),
                    'prepare_unchanged'=>$prepareUnchanged,'preview_config'=>$p['config'],'saved_config'=>$saved,'saved_again'=>file_get_contents($config),
                    'planned_files'=>$p['files'],'applied'=>$applied,'repeated'=>$repeated,'status'=>$status,
                    'stale_error'=>$stale,'stale_unchanged'=>$staleUnchanged,'resource_before'=>$beforeResources,'resource_after'=>resourcesSnapshot($r.'/resources'),
                    'config_stat_before_repeat'=>array_intersect_key($firstStat,array_flip(['dev','ino','mode','uid','gid','size','mtime','ctime'])),
                    'config_stat_after_repeat'=>array_intersect_key($secondStat,array_flip(['dev','ino','mode','uid','gid','size','mtime','ctime'])),
                    'journal_unchanged_by_repeat'=>$store->state()===$journalBefore,'journal'=>$journalBefore['current'],
                    'backup_config'=>$store->read(str_repeat('b',32).'.conf'),'dns_draft'=>$dns->draft()];
            }catch(Throwable $e){$out[$case['source_id']]=['error'=>$e->getMessage(),'trace'=>$e->getTraceAsString()];}
        }echo json_encode($out,JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR);'''
        request=json.dumps({'cases':cases})
        (root/'request.json').write_text(request)
        result=subprocess.run([PHP,'-n','-r',code,str(public),str(os.getuid())],input=request,capture_output=True,text=True,timeout=60)
        (root/'stdout.json').write_text(result.stdout);(root/'stderr.txt').write_text(result.stderr)
        self.assertEqual(result.returncode,0,result.stdout[-2000:]+result.stderr)
        self.assertEqual(result.stderr,'')
        values=json.loads(result.stdout)
        self.assertEqual(set(values),{'tcp_alt1','tcp_hostfake','full_combo','tcp_oob'})
        for case in cases:
            name=case['source_id'];value=values[name]
            with self.subTest(profile=profile,source_id=name):
                self.assertNotIn('error',value,value)
                self.assertEqual(value['profile'],profile)
                self.assertTrue(value['prepare_ready'],value)
                self.assertTrue(value['proof_issued'])
                self.assertTrue(value['prepare_unchanged'])
                self.assertEqual(value['stale_error'],'stale_preview')
                self.assertTrue(value['stale_unchanged'])
                self.assertEqual(value['applied']['state'],'committed')
                self.assertTrue(value['applied']['config_saved'])
                self.assertEqual(value['applied']['id'],'b'*32)
                self.assertFalse(value['applied']['dns_draft_saved'])
                self.assertEqual(value['saved_config'],value['preview_config'])
                self.assertEqual((Path(case['root'])/'resources/nfqws2.conf').read_text(),value['preview_config'])
                self.assertEqual(value['saved_again'],value['saved_config'])
                self.assertEqual(value['applied'],value['repeated'])
                self.assertEqual(value['config_stat_before_repeat'],value['config_stat_after_repeat'])
                self.assertTrue(value['journal_unchanged_by_repeat'])
                self.assertEqual(value['backup_config'],case['before'])
                self.assertEqual(value['resource_before'],value['resource_after'])
                self.assertEqual(value['planned_files'],[])
                self.assertEqual(len(value['journal']['inputs']),2)
                self.assertEqual(value['dns_draft'],None)
                self.assertEqual(value['status']['state'],'committed')
                self.assertTrue(value['status']['can_undo'])
                self.assertEqual(value['journal']['state'],'committed')
                self.assertEqual(value['journal']['before'],hashlib.sha256(case['before'].encode()).hexdigest())
                self.assertEqual(value['journal']['after'],hashlib.sha256(value['saved_config'].encode()).hexdigest())
                self.assertEqual({Path(path).name:sha for path,sha in value['journal']['inputs'].items()},
                                 {name:hashlib.sha256(raw).hexdigest()for name,raw in packaged.items()})
                self.assertEqual(value['config_stat_after_repeat']['uid'],os.getuid())
                self.assertEqual(value['config_stat_after_repeat']['mode']&0o777,0o600)
                for keep in ['ISP_INTERFACE="eth9"','ASUS_CLIENTS4="192.0.2.9"','USER="nobody"','NFQUEUE_NUM="321"']:
                    self.assertIn(keep,value['saved_config'])
                prefix='/etc/nfqws2/'if profile=='openwrt'else'/opt/etc/nfqws2/'
                self.assertIn('--lua-init=@'+prefix+'lua/zapret-lib.lua',value['saved_config'])
                self.assertIn('--lua-init=@'+prefix+'lua/zapret-antidpi.lua',value['saved_config'])
                if profile=='openwrt':self.assertNotIn('/opt/',value['saved_config'])
                for filename,raw in packaged.items():
                    self.assertEqual((Path(case['root'])/'resources/lua'/filename).read_bytes(),raw)
                for relative,raw in user_files.items():
                    self.assertEqual((Path(case['root'])/'resources'/relative).read_bytes(),raw)
        print('Avatar actual commits:',profile,len(values),'evidence:',root)

    def test_asus_prepare_apply_exact_preview_receipt_and_stale_guard(self):
        self.run_profile('asus-entware')

    def test_openwrt_prepare_apply_exact_preview_receipt_and_stale_guard(self):
        self.run_profile('openwrt')

    def test_keenetic_prepare_apply_exact_preview_receipt_and_stale_guard(self):
        self.run_profile('keenetic-entware')


if __name__=='__main__':unittest.main()

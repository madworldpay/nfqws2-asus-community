"""Actual selection → audit → exact reviewed attachments, with no source writes."""
import base64,hashlib,json,os,subprocess,tempfile,unittest
from pathlib import Path
from test_dpi_normalize import PHP,PUBLIC
from test_share_dns import LEGACY

class SharePrepareV4Tests(unittest.TestCase):
    def call(self,mode='complete'):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);files=root/'resources';files.mkdir(mode=0o755)
            for k in ['lists','lua','blobs']:(files/k).mkdir(mode=0o755)
            (files/'lists/sites.list').write_text('image.tmdb.org\n');(files/'lua/custom.lua').write_text('function custom() return 1 end\n');(files/'blobs/hello.bin').write_bytes(b'\0\xffHELLO')
            if mode in ('one_file','one_file_only'):
                for i in range(100):(files/f'lists/unused-{i}.list').write_text(f'UNSELECTED_CANARY_{i}\n')
            config='NFQWS_BASE_ARGS="--blob=hello:@/opt/etc/nfqws2/blobs/hello.bin --lua-init=@/opt/etc/nfqws2/lua/custom.lua"\nMODE_LIST="--hostlist=/opt/etc/nfqws2/lists/sites.list"\nNFQWS_ARGS="--filter-tcp=443 $MODE_LIST --lua-desync=fake:blob=hello"\n'
            
            if mode=='minimal':config='NFQWS_ARGS="--filter-tcp=443"\n'
            if mode=='destination':config='NFQWS_ARGS="--ipset-ip=162.159.0.0/16 --filter-tcp=443"\nASUS_CLIENTS4="192.168.1.201/32"\n'
            (root/'config').write_text(config);(root/'smartdns.conf').write_text(LEGACY)
            before={str(f.relative_to(root)):f.read_bytes() for f in root.rglob('*') if f.is_file()}
            code='''require $argv[1].'/share-api.php';
            class V4IO extends AsusReportIO {public function streamCommand(string $id,callable $c,float $timeout=1.0):array{$c('productid=GT-BE19000AI');return ['state'=>'available'];}public function read(string $source,int $limit=262144):array{return ['state'=>'available','value'=>'4.19.294'];}}
            try{$d=$argv[2];$owner=(int)$argv[3];$mode=$argv[4];$key=str_repeat('a',64);$v=['core'=>'1.3.1-asus6+b35','web'=>'0.1.4'];
            $resources=new AsusShareResources($d.'/resources',$owner);$dns=new AsusShareDns($d.'/smartdns.conf',$owner,['managed'=>fn()=>[]]);$api=new AsusShareApi(null,null,null,$d.'/config',$v,new AsusShareSource($d.'/identity',$owner,new V4IO()),$resources,$dns);
            $inventory=$api->handle(['cmd'=>'shareinventory','csrf_token'=>'fixture'],$key,1000);$rows=$inventory['files'];$context=['purpose'=>'Poster','operator'=>'Example ISP','comment'=>''];
            $draft=AsusShareStrategy::discover(file_get_contents($d.'/config'));$strategy=['mode'=>'blocks','draft'=>$draft,'context'=>$context];
            $selectedRows=$mode==='missing'?[]:$rows;
            if(in_array($mode,['one_file','one_file_only'],true))$selectedRows=array_values(array_filter($rows,fn($r)=>$r['kind']==='lists'&&$r['name']==='sites.list'));
            $chosen=array_column($selectedRows,'id');
            $a=$api->handle(['cmd'=>'shareanalyze','csrf_token'=>'fixture','selection'=>json_encode(['strategy'=>$strategy,'resource_ids'=>$chosen])],$key,1000);
            $selection=['version'=>4,'strategy'=>$strategy,'analysis_config_sha256'=>$a['config_sha256'],'context'=>$context,'resources'=>['files'=>array_map(fn($r)=>['id'=>$r['id'],'source_sha256'=>$r['sha256']],$selectedRows),'missing_reason'=>'']];
            if($mode==='changed')file_put_contents($d.'/config',"# changed\\n",FILE_APPEND);
            if(in_array($mode,['resources_only','one_file_only'],true))unset($selection['strategy'],$selection['analysis_config_sha256']);
            if($mode==='dns_only'){$s=$api->handle(['cmd'=>'sharednssources','csrf_token'=>'fixture'],$key,1000)['sources'][0];$selection=['version'=>4,'context'=>$context,'dns'=>[['source_id'=>$s['id'],'source_sha256'=>$s['sha256'],'upstreams'=>[$s['profile']['upstreams'][0]],'records'=>[]]]];}
            $p=$api->handle(['cmd'=>'shareprepare','csrf_token'=>'fixture','selection'=>json_encode($selection)],$key,1000);
            echo json_encode(['prepared'=>$p,'audit'=>$a,'valid'=>AsusShareBundle::verify($p['proof'],$p['files'],$key,1001,$p['source']??null)]);
            }catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
            cp=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),d,str(os.getuid()),mode],capture_output=True,text=True,timeout=12)
            self.assertEqual(cp.returncode,0,cp.stdout+cp.stderr);self.assertEqual(cp.stderr,'');result=json.loads(cp.stdout)
            if mode!='changed':self.assertEqual(before,{str(f.relative_to(root)):f.read_bytes() for f in root.rglob('*') if f.is_file()})
            return result
    def test_complete_selected_block_includes_shared_definitions_and_exact_files(self):
        v=self.call();self.assertNotIn('error',v);self.assertTrue(v['valid']);self.assertTrue(v['audit']['audit']['complete'])
        bodies={f['type']:json.loads(base64.b64decode(f['data_base64'])) for f in v['prepared']['files']}
        self.assertEqual(set(bodies),{'strategy','resources'});s=bodies['strategy'];r=bodies['resources']
        self.assertEqual(s['schema_version'],2);self.assertIn('--blob=hello:',s['shared']['NFQWS_BASE_ARGS']);self.assertNotIn('/opt/etc',json.dumps(bodies));self.assertEqual(len(r['files']),3)
        self.assertTrue(all(x['included'] for x in s['dependencies']));self.assertEqual({x['name'] for x in r['files']},{'sites.list','custom.lua','hello.bin'})
        blob=next(f for f in r['files'] if f['kind']=='blobs');self.assertEqual(base64.b64decode(blob['data_base64']),b'\0\xffHELLO')
    def test_strategy_alone_needs_no_files_or_missing_reason(self):
        v=self.call('missing');self.assertNotIn('error',v);self.assertTrue(v['valid'])
        self.assertEqual([f['type'] for f in v['prepared']['files']],['strategy'])
        s=json.loads(base64.b64decode(v['prepared']['files'][0]['data_base64']))
        self.assertTrue(s['dependencies']);self.assertTrue(all(not dep['included'] for dep in s['dependencies']))
    def test_only_selected_file_travels_despite_hundred_other_lists(self):
        for mode in ('one_file','one_file_only'):
            v=self.call(mode);self.assertNotIn('error',v);self.assertTrue(v['valid'])
            bodies={f['type']:json.loads(base64.b64decode(f['data_base64'])) for f in v['prepared']['files']}
            self.assertEqual(set(bodies),{'strategy','resources'} if mode=='one_file' else {'resources'})
            self.assertEqual([f['name'] for f in bodies['resources']['files']],['sites.list'])
            self.assertNotIn('UNSELECTED_CANARY',json.dumps(bodies))
    def test_dns_or_files_are_independent_of_strategy(self):
        for mode,kind in [('resources_only','resources'),('dns_only','dns')]:
            v=self.call(mode);self.assertNotIn('error',v);self.assertTrue(v['valid']);self.assertEqual([f['type'] for f in v['prepared']['files']],[kind])
    def test_config_change_between_analysis_and_preparation_is_refused(self):
        v=self.call('changed');self.assertEqual(v.get('error'),'source_changed')

    def test_simple_strategy_without_shared_globals_is_valid(self):
        v=self.call('minimal');self.assertNotIn('error',v);self.assertTrue(v['valid'])

    def test_v4_keeps_explicit_destination_filter_but_omits_client_identity(self):
        v=self.call('destination');self.assertNotIn('error',v)
        s=json.loads(base64.b64decode(next(f for f in v['prepared']['files'] if f['type']=='strategy')['data_base64']))
        self.assertIn('--ipset-ip=162.159.0.0/16',s['blocks'][0]['value']);self.assertNotIn('192.168.1.201',json.dumps(s))

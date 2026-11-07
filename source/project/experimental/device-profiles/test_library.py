import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import test_lab as lab

HERE=Path(__file__).resolve().parent
PHP=os.environ.get('PHP_TEST_BINARY','/usr/bin/php')


class Library(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        for name in ['config/lists','config/lua','config/blobs','private','engines']:
            (self.root/name).mkdir(parents=True,exist_ok=True)
        for path in self.root.rglob('*'):
            if path.is_dir():path.chmod(0o755)
        (self.root/'private').chmod(0o700)
        (self.root/'config/lists/user.list').write_text('example.org\n')
        (self.root/'config/lua/sample.lua').write_text('sample=true\n')
        (self.root/'config/nfqws2.conf').write_text('NFQWS_BASE_ARGS="--lua-init=@/etc/nfqws2/lua/sample.lua"\nNFQWS_ARGS="--filter-tcp=443 --hostlist=/etc/nfqws2/lists/user.list"\nTCP_PORTS=443\nUDP_PORTS=443\nIPV6_ENABLED=0\n')

    def call(self,operation='capture',name='Телевизор',document=None,trusted=False):
        request=self.root/'request.json';request.write_text(json.dumps({'operation':operation,'name':name,'document':document,'trusted':trusted}))
        code='''require $argv[1].'/platform.php';require $argv[1].'/import-config.php';
        require $argv[1].'/share-resources.php';require $argv[1].'/import-plan.php';
        require $argv[2].'/openwrt/config.php';
        $file=$argv[2].'/experimental/device-profiles/device-profiles-library.php';
        if(!is_file($file)){echo json_encode(['error'=>'missing_library']);exit;}
        require $file;
        try{$s=new NfqwsDeviceProfilesLibrary($argv[3].'/private',$argv[3].'/engines',$argv[3].'/config',(int)$argv[4]);
        $v=json_decode(file_get_contents($argv[3].'/request.json'),true);
        $out=match($v['operation']){'list'=>$s->listing(),'import'=>$s->import($v['name'],$v['document'],$v['trusted']),
          'stock'=>$s->stock($v['document']),default=>$s->capture($v['name'])};
        echo json_encode($out,JSON_THROW_ON_ERROR);
        }catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        p=subprocess.run([PHP,'-n','-r',code,str(lab.PUBLIC),str(HERE.parents[1]),str(self.root),str(os.getuid())],capture_output=True,text=True,timeout=10)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'')
        self.assertTrue(p.stdout.lstrip().startswith(('{','[')),p.stdout)
        return json.loads(p.stdout)

    def test_snapshot_isolated_resources_survive_changes_of_global_files(self):
        result=self.call();self.assertNotIn('error',result)
        ident=result['id'];self.assertRegex(ident,r'^saved-[a-f0-9]{16}$')
        meta=json.loads((self.root/'private/library'/f'{ident}.json').read_text())
        config=meta['config'];path=self.root/'engines'/ident/'lists/user.list'
        self.assertIn(str(path),config['NFQWS_ARGS'])
        self.assertEqual(path.read_text(),'example.org\n')
        (self.root/'config/lists/user.list').write_text('changed.invalid\n')
        self.assertEqual(path.read_text(),'example.org\n')
        self.assertEqual(self.call('list'),[{'id':ident,'name':'Телевизор'}])

    def test_unknown_paths_or_shell_programs_never_become_a_snapshot(self):
        (self.root/'config/nfqws2.conf').write_text('NFQWS_ARGS="--hostlist=/etc/shadow"\n')
        self.assertEqual(self.call(),{'error':'unresolved_profile_resource'})
        self.assertEqual(self.call('list'),[])
        (self.root/'config/nfqws2.conf').write_text('NFQWS_ARGS="$(touch bad)"\n')
        self.assertIn('error',self.call())
        self.assertFalse((self.root/'bad').exists())

    def test_symlinked_resource_is_not_copied_or_followed(self):
        p=self.root/'config/lists/user.list';p.unlink();p.symlink_to('/etc/passwd')
        self.assertEqual(self.call(),{'error':'unresolved_profile_resource'})
        self.assertEqual(self.call('list'),[])

    def test_dns_only_import_is_refused_without_touching_main_config(self):
        before=(self.root/'config/nfqws2.conf').read_bytes()
        self.assertIn('error',self.call('import',document='{}'))
        self.assertEqual((self.root/'config/nfqws2.conf').read_bytes(),before)

    def test_valid_strategy_export_is_a_separate_profile_without_global_changes(self):
        document={'type':'nfqws2_strategy','schema_version':2,'versions':{'core':'1.3.2','web':'0.1.4'},
                  'mode':'blocks','blocks':[{'key':'NFQWS_ARGS','value':'--filter-tcp=443'}],
                  'shared':{'NFQWS_BASE_ARGS':'--debug=0'},'purpose':'Example',
                  'operator':'Example ISP','comment':'','dependencies':[]}
        before=(self.root/'config/nfqws2.conf').read_bytes()
        result=self.call('import',name='Imported',document=json.dumps(document))
        self.assertNotIn('error',result)
        meta=json.loads((self.root/'private/library'/f'{result["id"]}.json').read_text())
        self.assertEqual(meta['config']['NFQWS_ARGS'],'--filter-tcp=443')
        self.assertEqual((self.root/'config/nfqws2.conf').read_bytes(),before)

    def test_explicit_lua_trust_allows_complete_import_but_never_missing_resource(self):
        document={'type':'nfqws2_strategy','schema_version':2,'versions':{'core':'1.3.2','web':'0.1.4'},
                  'mode':'blocks','blocks':[{'key':'NFQWS_ARGS','value':'--filter-tcp=443'}],
                  'shared':{'NFQWS_BASE_ARGS':'--lua-init=@/etc/nfqws2/lua/sample.lua'},'purpose':'Example',
                  'operator':'Example ISP','comment':'','dependencies':[]}
        raw=json.dumps(document)
        self.assertIn('error',self.call('import',document=raw))
        self.assertNotIn('error',self.call('import',document=raw,trusted=True))
        document['shared']['NFQWS_BASE_ARGS']='--lua-init=@/etc/nfqws2/lua/absent.lua'
        self.assertIn('error',self.call('import',document=json.dumps(document),trusted=True))

    def test_library_limit_is_bounded_and_failure_does_not_overwrite_entries(self):
        for i in range(8):self.assertNotIn('error',self.call(name='Snapshot '+str(i)))
        self.assertEqual(self.call(),{'error':'library_limit'})
        self.assertEqual(len(self.call('list')),8)

    def test_stock_is_one_separate_persistent_snapshot_outside_custom_limit(self):
        raw=(self.root/'config/nfqws2.conf').read_text()
        first=self.call('stock',document=raw);self.assertNotIn('error',first)
        self.assertEqual(first['id'],'stock');self.assertEqual(self.call('stock',document=raw),first)
        self.assertEqual(self.call('list'),[])
        self.assertIn(str(self.root/'engines/stock/lists/user.list'),first['config']['NFQWS_ARGS'])

    def test_auto_learning_file_is_private_to_the_profile_and_debug_output_disabled(self):
        with (self.root/'config/nfqws2.conf').open('a')as f:
            f.write('NFQWS_EXTRA_ARGS="--hostlist-auto=/etc/nfqws2/lists/auto.list --hostlist-auto-debug=/var/log/nfqws2-auto.log"\n')
        result=self.call();self.assertNotIn('error',result)
        row=json.loads((self.root/'private/library'/f'{result["id"]}.json').read_text())
        self.assertEqual(row['mutable_files'],['lists/auto.list'])
        self.assertEqual((self.root/'engines'/result['id']/'lists/auto.list').read_text(),'')
        self.assertNotIn('--hostlist-auto-debug',row['config']['NFQWS_EXTRA_ARGS'])

if __name__=='__main__':unittest.main()

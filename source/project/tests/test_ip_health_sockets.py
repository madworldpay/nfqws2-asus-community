"""Pinned optional module: actual archives, PHP loader and private-root Entware opkg."""
import copy
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import tarfile
import unittest
from test_dpi_normalize import PHP, PUBLIC, ROOT

FIXTURES=Path(os.environ.get('NFQWS_SOCKETS_FIXTURES',str(ROOT/'.work/ip-health-sockets-fixtures')))
TOOLS=ROOT/'.work/packaging-audit-20261012'
OPKG=TOOLS/'opkg-x64'
CATALOG=ROOT/'asus/ip-health-sockets.json'

class SocketsPassiveStatusTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name);self.opt=self.base/'opt';self.opt.mkdir(mode=0o755)
        self.state=self.opt/'var/lib/nfqws2-asus/ip-health-sockets'
    def root(self):
        self.state.mkdir(parents=True,mode=0o700)
        for p in [self.opt/'var',self.opt/'var/lib',self.opt/'var/lib/nfqws2-asus']:p.chmod(0o755)
    def call(self):
        code="require $argv[1].'/ip-health-sockets.php';try{echo json_encode(['value'=>(new NfqwsIpHealthSockets(json_decode($argv[2],true)))->status()]);}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}"
        p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),json.dumps({'opt':str(self.opt),'state':str(self.state),'owner':os.getuid()})],capture_output=True,text=True,timeout=5)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'');return json.loads(p.stdout)
    def test_absent_and_empty_interrupted_roots_are_read_without_creating_any_files(self):
        expected={'value':{'state':'unavailable','code':'sockets_unprepared'}}
        self.assertEqual(self.call(),expected);self.assertFalse(self.state.exists())
        self.root();self.assertEqual(self.call(),expected);self.assertEqual(list(self.state.iterdir()),[])
    def test_valid_partial_status_is_read_without_creating_operation_directory(self):
        self.root();status=self.state/'status.json';raw='{"state":"pending","code":"sockets_preparing"}';status.write_text(raw);status.chmod(0o600);before=status.stat()
        self.assertEqual(self.call(),{'value':{'state':'pending','code':'sockets_preparing'}})
        self.assertEqual(sorted(p.name for p in self.state.iterdir()),['status.json']);self.assertEqual(status.read_text(),raw);after=status.stat();self.assertEqual((before.st_ino,before.st_mtime_ns),(after.st_ino,after.st_mtime_ns))
    def test_unknown_status_code_or_unsafe_root_never_gets_returned_or_repaired(self):
        self.root();status=self.state/'status.json';status.write_text('{"state":"failed","code":"PRIVATE_CANARY"}');status.chmod(0o600)
        self.assertEqual(self.call(),{'error':'invalid_state'});self.assertEqual(sorted(p.name for p in self.state.iterdir()),['status.json'])
        status.unlink();self.state.chmod(0o755);self.assertEqual(self.call(),{'error':'invalid_state'});self.assertEqual(list(self.state.iterdir()),[])
    def test_linked_or_nonprivate_status_is_refused_without_writes(self):
        self.root();outside=self.base/'outside';outside.write_text('{"state":"ready","code":null}');outside.chmod(0o600);status=self.state/'status.json';status.symlink_to(outside)
        self.assertEqual(self.call(),{'error':'invalid_state'});self.assertTrue(status.is_symlink());status.unlink();status.write_text(outside.read_text());status.chmod(0o644)
        self.assertEqual(self.call(),{'error':'invalid_state'});self.assertEqual(sorted(p.name for p in self.state.iterdir()),['status.json'])

@unittest.skipUnless(OPKG.is_file() and (FIXTURES/'php8-mod-sockets_8.2.8-1_armv7-2.6.ipk').is_file(), 'verified official fixture and actual Entware opkg required')
class IpHealthSocketsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name);self.opt=self.base/'opt'
        self.state=self.opt/'var/lib/nfqws2-asus/ip-health-sockets';self.status=self.opt/'lib/opkg/status'
        for path in ['lib/opkg/info','tmp','etc/php8','lib/php8','bin','etc','share/nfqws2-asus/ip-health-sockets/ipks']:(self.opt/path).mkdir(parents=True,exist_ok=True)
        self.opt.chmod(0o755)
        self.resources=self.opt/'share/nfqws2-asus/ip-health-sockets'
        self.catalog=json.loads(CATALOG.read_text());(self.resources/'catalog.json').write_text(json.dumps(self.catalog));(self.resources/'catalog.json').chmod(0o644)
        for e in self.catalog['entries']:
            shutil.copyfile(FIXTURES/e['filename'],self.resources/'ipks'/e['filename']);(self.resources/'ipks'/e['filename']).chmod(0o644)
        self.config=self.base/'opkg.conf';self.config.write_text('dest root /\narch all 100\narch armv7-2.6 200\n')
        self.opkg=self.base/'opkg';self.opkg.write_text('#!/bin/sh\nexec '+shlex.join([str(OPKG),'-f',str(self.config),'-o',str(self.base),'--tmp-dir',str(self.opt/'tmp'),'--force-postinstall'])+' "$@"\n');self.opkg.chmod(0o700)
        self.status.write_text('\n\n'.join(self.row(name,version) for name,version in [('nfqws2-asus','1.3.2-asus6+b82'),('php8','8.2.8-1'),('libc','1'),('libssp','1'),('librt','1'),('libpthread','1')])+'\n\n')
        self.status.chmod(0o644)
        for name in ['nfqws2-asus','php8','libc','libssp','librt','libpthread']:
            (self.opt/'lib/opkg/info'/(name+'.list')).write_text('')
            (self.opt/'lib/opkg/info'/(name+'.list')).chmod(0o644)
        for p in self.opt.rglob('*'):
            if p.is_dir():p.chmod(0o755)
        self.options={'opt':str(self.opt),'owner':os.getuid(),'abi':'armv7-2.6','machine':'armv7l','state':str(self.state),'launcher':str(self.base/'launcher'),
            'php':[str(TOOLS/'qemu-arm'),'-L',str(TOOLS/'armv7-legacy-sysroot'),str(TOOLS/'armv7-legacy-sysroot/opt/bin/php8-cgi')]}
        self.runner=self.base/'runner.php';self.runner.write_text('''<?php require '''+repr(str(PUBLIC/'ip-health-sockets.php'))+''';
        try{$service=new NfqwsIpHealthSockets(json_decode(file_get_contents($argv[1]),true));$v=match($argv[2]){'prepare'=>$service->prepare(),'preflight'=>$service->preflight($argv[3],$argv[4]),'apply'=>$service->apply($argv[3]),'status'=>$service->status()};echo json_encode(['value'=>$v]);}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);exit(3);}''')
        self.options['entry']=[PHP,'-n',str(self.runner)] # appended trusted config, mode and IDs by generated check.sh
        self.options_file=self.base/'options.json';self.options['entry_config']=str(self.options_file);self.save_options()
        subprocess.run(['gcc','-Os','-nostdlib','-static','-fno-builtin','-fno-stack-protector','-fno-pie','-no-pie','-DSOCKETS_ONLY=1','-DUPDATE_ROOT="'+str(self.state)+'"','-DOPKG_LOCK="'+str(self.opt/'tmp/opkg.lock')+'"','-DOPKG_BIN="'+str(self.opkg)+'"','-DUPDATE_OWNER='+str(os.getuid()),str(ROOT/'asus/update/opkg-launch.c'),'-o',str(self.base/'launcher')],check=True,capture_output=True)
        (self.base/'launcher').chmod(0o755)
    def save_options(self):self.options_file.write_text(json.dumps(self.options))
    @staticmethod
    def row(name,version,state='install ok installed'):
        return f'Package: {name}\nVersion: {version}\nArchitecture: all\nStatus: {state}'
    def call(self,mode,*args):
        self.save_options();p=subprocess.run([PHP,'-n',str(self.runner),str(self.options_file),mode,*args],capture_output=True,text=True,timeout=20)
        self.assertEqual(p.stderr,'',p.stdout);self.assertIn(p.returncode,[0,3],p.stdout);return json.loads(p.stdout)
    def prepare(self):
        v=self.call('prepare');self.assertIn('value',v,v);return v['value']['id']
    def foreign(self):
        return sorted(tuple(sorted(s.splitlines())) for s in self.status.read_text().strip().split('\n\n') if not s.startswith('Package: php8-mod-sockets\n'))
    def installed(self):return 'Package: php8-mod-sockets\n' in self.status.read_text()
    def test_real_manager_installs_only_pinned_absent_module_and_real_php_loads_it(self):
        before=self.foreign();job=self.prepare();value=self.call('apply',job)
        self.assertEqual(value,{'value':{'state':'ready','code':None}});self.assertTrue(self.installed());self.assertEqual(self.foreign(),before)
        self.assertEqual((self.opt/'etc/php8/20_sockets.ini').read_text(),'extension=sockets.so\n')
        self.assertEqual(hashlib.sha256((self.opt/'lib/php8/sockets.so').read_bytes()).hexdigest(),'70be5b56578d4e859061488e297450856ad6801b09a90e1ec6d21ead8e751db2')
        self.assertFalse((self.opt/'etc/nfqws2').exists(),'module task must not start/alter core')
        self.assertEqual(self.call('prepare')['value']['state'],'ready','healthy installed module is reused')
    def install_legacy_foreign_index(self):
        def section(files):
            out=io.BytesIO()
            with tarfile.open(fileobj=out,mode='w:gz',format=tarfile.USTAR_FORMAT) as archive:
                for name,raw in files.items():
                    member=tarfile.TarInfo(name);member.mode=0o644;member.size=len(raw);archive.addfile(member,io.BytesIO(raw))
            return out.getvalue()
        control=b'Package: foreign-lib\nVersion: 1\nArchitecture: all\nDescription: foreign inventory fixture\n'
        package=self.base/'foreign.ipk';package.write_bytes(section({'debian-binary':b'2.0\n','control.tar.gz':section({'control':control}),'data.tar.gz':section({'opt/share/foreign-marker':b'FOREIGN'})}))
        p=subprocess.run([str(OPKG),'-f',str(self.config),'-o',str(self.base),'--tmp-dir',str(self.opt/'tmp'),'--nodeps','install',str(package)],capture_output=True,text=True,timeout=5,umask=0)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        index=self.opt/'lib/opkg/info/foreign-lib.list';self.assertEqual(index.stat().st_mode&0o777,0o666)
        return index
    def test_actual_legacy_foreign_index_allows_pinned_module_without_chmod_or_foreign_changes(self):
        index=self.install_legacy_foreign_index();before=(index.read_bytes(),index.stat().st_ino,index.stat().st_mode,self.foreign())
        # Retry the real pre-plan failure shape without deleting its journal.
        (self.state/'operations').mkdir(parents=True,mode=0o700);self.state.chmod(0o700)
        for p in [self.opt/'var',self.opt/'var/lib',self.opt/'var/lib/nfqws2-asus']:p.chmod(0o755)
        status=self.state/'status.json';status.write_text('{"state":"failed","code":"invalid_state"}');status.chmod(0o600)
        job=self.prepare();self.assertEqual(self.call('apply',job),{'value':{'state':'ready','code':None}})
        self.assertEqual((index.read_bytes(),index.stat().st_ino,index.stat().st_mode,self.foreign()),before)
        self.assertEqual((self.opt/'share/foreign-marker').read_bytes(),b'FOREIGN')
    def test_legacy_foreign_claim_alias_or_link_never_permits_module_install(self):
        index=self.install_legacy_foreign_index()
        for claim,expected in [('/opt/lib/php8/sockets.so','sockets_path_conflict'),('//opt/lib/php8/sockets.so','invalid_state')]:
            with self.subTest(claim=claim):
                index.write_text(claim+'\n');self.assertEqual(self.call('prepare'),{'error':expected});self.assertFalse(self.installed())
        outside=self.base/'outside-index';index.rename(outside);index.symlink_to(outside)
        self.assertEqual(self.call('prepare'),{'error':'invalid_state'});self.assertFalse(self.installed())
    def test_real_manager_preserves_legacy_status_mode_while_only_module_is_installed(self):
        self.status.chmod(0o666);self.install_legacy_foreign_index()
        self.assertEqual(self.status.stat().st_mode&0o777,0o666)
        before=(self.status.read_bytes(),self.status.stat().st_ino,self.status.stat().st_mode,self.status.stat().st_mtime_ns);foreign=self.foreign()
        job=self.prepare()
        self.assertEqual((self.status.read_bytes(),self.status.stat().st_ino,self.status.stat().st_mode,self.status.stat().st_mtime_ns),before,'preparation only reads manager data')
        self.assertEqual(self.call('apply',job),{'value':{'state':'ready','code':None}});self.assertEqual(self.foreign(),foreign)
        self.assertEqual(self.status.stat().st_mode&0o777,0o666)
    def test_manager_status_uses_its_two_megabyte_cap_without_loosening_index_cap(self):
        records='\n\n'.join(self.row('inventory'+str(i),'1')+'\nDescription: '+'x'*8192 for i in range(20))
        self.status.write_text(self.status.read_text()+records+'\n\n');self.status.chmod(0o666)
        self.assertGreater(self.status.stat().st_size,131072);before=self.status.read_bytes();self.prepare()
        self.assertEqual(self.status.read_bytes(),before);self.assertFalse(self.installed())
    def stock_abi_config(self):
        self.options.pop('abi',None);path=self.opt/'etc/opkg.conf'
        path.write_text('src/gz entware https://bin.entware.net/armv7sf-k2.6\ndest root /\narch all 100\narch armv7-2.6 200\n');path.chmod(0o666)
        return path
    def test_stock_666_config_without_dropin_directory_allows_only_pinned_module(self):
        config=self.stock_abi_config();self.status.chmod(0o666);self.install_legacy_foreign_index()
        self.assertFalse((self.opt/'etc/opkg').exists());before=(config.read_bytes(),config.stat().st_ino,config.stat().st_mode,config.stat().st_mtime_ns);foreign=self.foreign()
        job=self.prepare();self.assertEqual(self.call('apply',job),{'value':{'state':'ready','code':None}})
        self.assertEqual((config.read_bytes(),config.stat().st_ino,config.stat().st_mode,config.stat().st_mtime_ns),before);self.assertEqual(self.foreign(),foreign)
    def test_666_abi_dropins_are_read_but_neighbors_and_include_directives_are_inert(self):
        config=self.stock_abi_config();config.write_text('include /outside/operator.conf\n')
        directory=self.opt/'etc/opkg';directory.mkdir(mode=0o755);drop=directory/'10_arch.conf';drop.write_text('arch all 100\narch armv7-2.6 200\n');drop.chmod(0o666)
        outside=self.base/'outside-config';outside.write_text('arch aarch64-3.10 900\n');outside.chmod(0o666)
        neighbor=directory/'ignored.bak';neighbor.symlink_to(outside);before=(outside.read_bytes(),outside.stat().st_mtime_ns)
        self.prepare();self.assertFalse(self.installed());self.assertEqual((outside.read_bytes(),outside.stat().st_mtime_ns),before)
        config.unlink();self.prepare()
    def test_abi_config_links_unsafe_modes_parents_and_unsupported_nodes_are_refused(self):
        config=self.stock_abi_config();raw=config.read_bytes();outside=self.base/'outside-config';outside.write_bytes(raw);outside.chmod(0o666)
        for kind in ['symlink','hardlink','fifo']:
            with self.subTest(kind=kind):
                config.unlink()
                if kind=='symlink':config.symlink_to(outside)
                elif kind=='hardlink':os.link(outside,config)
                else:os.mkfifo(config)
                self.assertEqual(self.call('prepare'),{'error':'invalid_state'});self.assertFalse(self.installed())
                config.unlink();config.write_bytes(raw);config.chmod(0o666)
        for mode in [0o664,0o646,0o1666,0o2666,0o4666]:
            with self.subTest(mode=oct(mode)):
                config.chmod(mode);self.assertEqual(self.call('prepare'),{'error':'invalid_state'})
        config.chmod(0o666);directory=self.opt/'etc/opkg';directory.symlink_to(self.base)
        self.assertEqual(self.call('prepare'),{'error':'invalid_state'});directory.unlink();directory.mkdir(mode=0o755)
        drop=directory/'arch.conf';drop.symlink_to(self.base/'absent')
        self.assertEqual(self.call('prepare'),{'error':'invalid_state'});drop.unlink()
        unusual=directory/'operator name.conf';unusual.write_text('arch armv7-2.6 200\n')
        self.assertEqual(self.call('prepare'),{'error':'invalid_state'});unusual.unlink();directory.chmod(0o777)
        self.assertEqual(self.call('prepare'),{'error':'invalid_state'});directory.chmod(0o755);config.parent.chmod(0o777)
        self.assertEqual(self.call('prepare'),{'error':'invalid_state'});self.assertEqual(outside.read_bytes(),raw)
    def test_abi_config_limits_are_bounded_before_parser_and_keep_near_cap_valid(self):
        config=self.stock_abi_config();directory=self.opt/'etc/opkg';directory.mkdir(mode=0o755)
        # Many short comments exercise ABI's explode() allocation under16M.
        main='arch all 100\narch armv7-2.6 200\n'+'#\n'*4000
        config.write_text(main+'#'+'x'*(65535-len(main)-1))
        for i in range(3):
            drop=directory/(str(i)+'.conf');drop.write_text('#'+'x'*65534);drop.chmod(0o666)
        self.prepare();self.assertFalse(self.installed())
        (directory/'3.conf').write_text('#'+'x'*65534)
        self.assertEqual(self.call('prepare'),{'error':'invalid_state'});(directory/'3.conf').unlink()
        config.write_text('arch armv7-2.6 200\n'+'\n'*4097)
        self.assertEqual(self.call('prepare'),{'error':'invalid_state'})
        config.write_text('arch armv7-2.6 200\n'+'x'*65537)
        self.assertEqual(self.call('prepare'),{'error':'invalid_state'})
        config.write_text('arch armv7-2.6 200\n')
        for i in range(129):(directory/(str(i)+'.conf')).write_text('')
        self.assertEqual(self.call('prepare'),{'error':'invalid_state'})
    def test_abi_config_replacement_between_stat_and_open_is_refused_before_plan(self):
        config=self.stock_abi_config();config.chmod(0o644)
        public=self.base/'config-race-app';shutil.copytree(PUBLIC,public);self.runner.write_text(self.runner.read_text().replace(str(PUBLIC),str(public)))
        source=public/'update-rollback.php';code=source.read_text();barrier="$f=@fopen($path,'rb');if(!$f)throw new RuntimeException('rollback_unavailable');"
        self.assertIn(barrier,code);mutation="if(basename($path)==='opkg.conf'){copy($path,$path.'.replacement');chmod($path.'.replacement',0644);rename($path.'.replacement',$path);}"
        source.write_text(code.replace(barrier,mutation+barrier,1))
        self.assertEqual(self.call('prepare'),{'error':'invalid_state'});self.assertFalse((self.state/'current.json').exists());self.assertFalse(self.installed())
    def test_manager_status_links_unsafe_modes_parents_and_size_are_refused(self):
        raw=self.status.read_bytes();outside=self.base/'outside-status';outside.write_bytes(raw);outside.chmod(0o666)
        for kind in ['symlink','hardlink']:
            with self.subTest(kind=kind):
                self.status.unlink()
                if kind=='symlink':self.status.symlink_to(outside)
                else:os.link(outside,self.status)
                self.assertEqual(self.call('prepare'),{'error':'invalid_state'});self.assertFalse(self.installed());self.assertEqual(outside.read_bytes(),raw)
                self.status.unlink();self.status.write_bytes(raw);self.status.chmod(0o644)
        for mode in [0o664,0o646,0o1666,0o2666,0o4666]:
            with self.subTest(mode=oct(mode)):
                self.status.chmod(mode);self.assertEqual(self.call('prepare'),{'error':'invalid_state'});self.assertFalse(self.installed())
        self.status.chmod(0o666);self.status.parent.chmod(0o777)
        self.assertEqual(self.call('prepare'),{'error':'invalid_state'});self.status.parent.chmod(0o755)
        self.status.write_bytes(raw+b'\n'*2097153)
        self.assertEqual(self.call('prepare'),{'error':'invalid_state'});self.assertFalse(self.installed())
    def test_status_replacement_between_stat_and_open_is_refused_before_plan(self):
        public=self.base/'race-app';shutil.copytree(PUBLIC,public)
        self.runner.write_text(self.runner.read_text().replace(str(PUBLIC),str(public)))
        source=public/'update-rollback.php';code=source.read_text();barrier="$f=@fopen($path,'rb');if(!$f)throw new RuntimeException('rollback_unavailable');"
        self.assertIn(barrier,code)
        mutation="if(basename($path)==='status'){copy($path,$path.'.replacement');chmod($path.'.replacement',lstat($path)['mode']&0777);rename($path.'.replacement',$path);}"
        source.write_text(code.replace(barrier,mutation+barrier,1))
        self.assertEqual(self.call('prepare'),{'error':'invalid_state'});self.assertFalse(self.installed());self.assertFalse((self.state/'current.json').exists())
    def test_late_manager_growth_never_causes_an_unbounded_second_read(self):
        public=self.base/'budget-app';shutil.copytree(PUBLIC,public);source=public/'update-rollback.php';original=source.read_text();marker=self.base/'hash-budget-exceeded'
        barrier="if(!is_string($raw)||strlen($raw)!==$before['size']";self.assertIn(barrier,original)
        # Instrument the filesystem-read budget, not the returned error: both
        # old and new code reject growth, but the old path hash reads past cap.
        prefix='''<?php
namespace NfqwsInventoryReadBudget;
use \\AsusUpdateStore;
use \\RuntimeException;
function hash_file($algorithm,$path){
    clearstatcache(true,$path);$cap=basename($path)==='status'?2097152:131072;
    if(filesize($path)>$cap){file_put_contents('''+json.dumps(str(marker))+''','attempted');throw new RuntimeException('hash_budget_exceeded');}
    return \\hash_file($algorithm,$path);
}
'''
        script='''require $argv[1].'/update-rollback.php';try{
        if($argv[4]==='status')\\NfqwsInventoryReadBudget\\AsusUpdateRollback::managerStatus($argv[2],(int)$argv[3]);
        else foreach(\\NfqwsInventoryReadBudget\\AsusUpdateRollback::inventory($argv[2],(int)$argv[3]) as $record){}
        echo json_encode(['ok'=>true]);}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        for mode,name,cap in [('status','status',2097152),('inventory','nfqws2-asus.list',131072)]:
            with self.subTest(mode=mode):
                marker.unlink(missing_ok=True)
                mutation="if(basename($path)==="+json.dumps(name)+"){file_put_contents($path,str_repeat('x',"+str(cap+1)+"),FILE_APPEND);}"
                source.write_text(original.replace('<?php\n',prefix,1).replace(barrier,mutation+barrier,1))
                p=subprocess.run([PHP,'-n','-r',script,str(public),str(self.opt),str(os.getuid()),mode],capture_output=True,text=True,timeout=3)
                self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'')
                self.assertEqual(json.loads(p.stdout),{'error':'rollback_unavailable'});self.assertFalse(marker.exists(),'second filesystem read must remain bounded')
    def test_legacy_status_does_not_relax_catalog_or_module_payload_permissions(self):
        self.status.chmod(0o666);catalog=self.resources/'catalog.json';catalog.chmod(0o666)
        self.assertEqual(self.call('prepare'),{'error':'invalid_state'});catalog.chmod(0o644)
        job=self.prepare();self.assertEqual(self.call('apply',job),{'value':{'state':'ready','code':None}})
        (self.opt/'lib/php8/sockets.so').chmod(0o666)
        self.assertEqual(self.call('prepare'),{'error':'invalid_state'})
    def test_php_upgrade_and_unsupported_abi_are_refused_before_any_opkg(self):
        self.status.write_text(self.status.read_text().replace('Version: 8.2.8-1','Version: 8.2.8-2'))
        self.assertEqual(self.call('prepare'),{'error':'sockets_php_unsupported'});self.assertFalse(self.installed())
    def test_true_foreign_pending_refuses_but_healthy_held_php_is_allowed(self):
        before=self.status.read_text();self.status.write_text(before.replace('install ok installed','install hold installed'))
        # The app itself cannot be held; keep its ordinary update policy.
        self.status.write_text(self.status.read_text().replace('Architecture: all\nStatus: install hold installed','Architecture: all\nStatus: install ok installed',1))
        self.prepare();self.status.write_text(before.rstrip()+'\n\n'+self.row('foreign','1','install user unpacked')+'\n\n')
        self.assertEqual(self.call('prepare'),{'error':'pending_packages'});self.assertFalse(self.installed())
    def test_owner_files_existing_module_and_unknown_pending_are_never_overwritten(self):
        file=self.opt/'lib/php8/sockets.so';file.write_text('OWNER')
        self.assertEqual(self.call('prepare'),{'error':'sockets_path_conflict'});self.assertEqual(file.read_text(),'OWNER');file.unlink()
        self.status.write_text(self.status.read_text()+self.row('php8-mod-sockets','8.2.8-1','install user unpacked')+'\n\n')
        self.assertEqual(self.call('prepare'),{'error':'sockets_recovery_required'})
    def test_catalog_ipk_mutation_or_symlink_never_reaches_manager(self):
        item=self.catalog['entries'][0];path=self.resources/'ipks'/item['filename'];path.write_bytes(path.read_bytes()+b'X')
        self.assertEqual(self.call('prepare'),{'error':'sockets_artifact_invalid'});self.assertFalse(self.installed())
    def test_php_loader_api_mismatch_exit_zero_is_not_success(self):
        self.options['php']=[str(TOOLS/'qemu-arm'),'-L',str(TOOLS/'armv7-sysroot'),str(TOOLS/'armv7-sysroot/opt/bin/php8-cgi')]
        self.assertEqual(self.call('prepare'),{'error':'sockets_probe_failed'});self.assertFalse(self.installed())
    def test_native_mutex_contention_leaves_real_database_and_payload_untouched(self):
        job=self.prepare();before=self.status.read_bytes();lock=self.opt/'tmp/opkg.lock';lock.touch(mode=0o600)
        with lock.open('r+') as f:
            fcntl.lockf(f,fcntl.LOCK_EX|fcntl.LOCK_NB);self.assertEqual(self.call('apply',job)['value']['code'],'opkg_busy')
        self.assertEqual(self.status.read_bytes(),before);self.assertFalse((self.opt/'lib/php8/sockets.so').exists())
        self.assertFalse((self.state/'operations'/job/'boundary.json').exists(),'busy launcher never owned an unpack boundary')
    def test_foreign_database_change_after_prepare_refuses_before_install(self):
        job=self.prepare();self.status.write_text(self.status.read_text()+self.row('later','1')+'\n\n')
        self.assertEqual(self.call('apply',job)['value']['code'],'sockets_baseline_changed');self.assertFalse(self.installed())
    def test_owned_exact_unpack_can_resume_only_after_native_boundary_proof(self):
        job=self.prepare();self.assertIn('value',self.call('preflight',job,'install'))
        artifact=self.state/'operations'/job/'package.ipk'
        p=subprocess.run([str(OPKG),'-f',str(self.config),'-o',str(self.base),'--tmp-dir',str(self.opt/'tmp'),'--nodeps','install',str(artifact)],capture_output=True,text=True,timeout=5,umask=0o022)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        # The official module has no scripts, so real opkg configures it
        # immediately. Model a persisted interrupted boundary after its actual
        # unpack, preserving every real payload and manager metadata byte.
        self.pending_fixture()
        self.assertIn('unpacked',self.status.read_text())
        prepared=self.call('prepare');self.assertEqual(prepared['value']['id'],job)
        self.assertEqual(self.call('apply',job),{'value':{'state':'ready','code':None}})
        self.assertNotIn('unpacked',self.status.read_text())
    def test_owned_exact_unpack_accepts_real_legacy_module_index_with_current_boundary_proof(self):
        job=self.prepare();self.assertIn('value',self.call('preflight',job,'install'));artifact=self.state/'operations'/job/'package.ipk'
        p=subprocess.run([str(OPKG),'-f',str(self.config),'-o',str(self.base),'--tmp-dir',str(self.opt/'tmp'),'--nodeps','install',str(artifact)],capture_output=True,text=True,timeout=5,umask=0)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        index=self.opt/'lib/opkg/info/php8-mod-sockets.list';self.assertEqual(index.stat().st_mode&0o777,0o666);before=(index.read_bytes(),index.stat().st_ino,index.stat().st_mode)
        self.pending_fixture();prepared=self.call('prepare');self.assertIn('value',prepared,prepared);self.assertEqual(prepared['value']['id'],job)
        self.assertEqual(self.call('apply',job),{'value':{'state':'ready','code':None}})
        self.assertEqual((index.read_bytes(),index.stat().st_ino,index.stat().st_mode),before)
    def test_tampered_owned_unpack_payload_does_not_get_configured(self):
        job=self.prepare();self.call('preflight',job,'install');artifact=self.state/'operations'/job/'package.ipk'
        subprocess.run([str(OPKG),'-f',str(self.config),'-o',str(self.base),'--tmp-dir',str(self.opt/'tmp'),'--nodeps','install',str(artifact)],capture_output=True,check=True,umask=0o022)
        self.pending_fixture()
        (self.opt/'lib/php8/sockets.so').write_bytes(b'BROKEN')
        self.assertEqual(self.call('prepare'),{'error':'sockets_recovery_required'})
    def pending_fixture(self):
        rows=self.status.read_text().strip().split('\n\n')
        self.status.write_text('\n\n'.join(row.replace(' installed',' unpacked') if row.startswith('Package: php8-mod-sockets\n') else row for row in rows)+'\n\n')
    def test_absent_foreign_owned_payload_path_still_blocks_install(self):
        for path in ['/opt/lib/php8/sockets.so',str(self.opt/'lib/php8/sockets.so')]:
            with self.subTest(path=path):
                (self.opt/'lib/opkg/info/php8.list').write_text(path+'\n')
                self.assertEqual(self.call('prepare'),{'error':'sockets_path_conflict'});self.assertFalse(self.installed())
    def test_tampered_private_probe_payload_is_not_executed(self):
        job=self.prepare();(self.state/'operations'/job/'runtime/sockets.so').write_bytes(b'BROKEN')
        self.assertEqual(self.call('apply',job)['value']['code'],'sockets_artifact_invalid');self.assertFalse(self.installed())
    def test_healthy_existing_module_with_other_packaging_release_is_reused_without_upgrade(self):
        job=self.prepare();self.assertEqual(self.call('apply',job)['value']['state'],'ready')
        self.status.write_text(self.status.read_text().replace('Version: 8.2.8-1','Version: 8.2.8-2'))
        before=self.status.read_bytes();self.assertEqual(self.call('prepare')['value']['state'],'ready');self.assertEqual(self.status.read_bytes(),before)
    def test_unknown_own_generation_cannot_claim_earlier_unpacked_module(self):
        job=self.prepare();self.call('preflight',job,'install');artifact=self.state/'operations'/job/'package.ipk'
        subprocess.run([str(OPKG),'-f',str(self.config),'-o',str(self.base),'--tmp-dir',str(self.opt/'tmp'),'--nodeps','install',str(artifact)],capture_output=True,check=True,umask=0o022)
        self.pending_fixture();self.status.write_text(self.status.read_text().replace('+b82','+b83'))
        self.assertEqual(self.call('prepare'),{'error':'sockets_recovery_required'})
    def test_both_modern_official_archives_install_and_probe_without_php_upgrade(self):
        for abi,machine,sysroot,qemu in [('armv7-3.2','armv7l','armv7-sysroot','qemu-arm'),('aarch64-3.10','aarch64','aarch64-sysroot','qemu-aarch64')]:
            with self.subTest(abi=abi):
                f=IpHealthSocketsTests();f.setUp()
                try:
                    f.options.update(abi=abi,machine=machine,php=[str(TOOLS/qemu),'-L',str(TOOLS/sysroot),str(TOOLS/sysroot/'opt/bin/php8-cgi')])
                    f.status.write_text(f.status.read_text().replace('Version: 8.2.8-1','Version: 8.4.16-4'))
                    f.config.write_text('dest root /\narch all 100\narch '+abi+' 200\n')
                    before=f.foreign();job=f.prepare();self.assertEqual(f.call('apply',job),{'value':{'state':'ready','code':None}});self.assertEqual(f.foreign(),before)
                finally:f.doCleanups()
    def test_stalled_installer_is_bounded_and_retains_its_partial_diagnostics(self):
        job=self.prepare();self.options['install_timeout']=1.0
        self.opkg.write_text('#!/bin/sh\nprintf "partial sockets installer diagnostic\\n"\nexec sleep 30\n')
        start=__import__('time').monotonic();v=self.call('apply',job)
        self.assertLess(__import__('time').monotonic()-start,3);self.assertEqual(v['value']['code'],'timed_out');self.assertFalse(self.installed())
        self.assertIn('partial sockets installer diagnostic',(self.state/'operations'/job/'opkg.log').read_text())
    def test_catalog_link_and_unsafe_payload_parent_refuse_without_changes(self):
        catalog=self.resources/'catalog.json';outside=self.base/'outside.json';catalog.rename(outside);catalog.symlink_to(outside)
        self.assertEqual(self.call('prepare'),{'error':'invalid_state'});catalog.unlink();outside.rename(catalog)
        (self.opt/'lib/php8').chmod(0o777)
        self.assertEqual(self.call('prepare'),{'error':'sockets_path_conflict'});self.assertFalse(self.installed())
    def test_failed_probe_retains_one_resumable_private_stage_instead_of_leaking_retries(self):
        self.options['php']=[str(TOOLS/'qemu-arm'),'-L',str(TOOLS/'armv7-sysroot'),str(TOOLS/'armv7-sysroot/opt/bin/php8-cgi')]
        self.assertEqual(self.call('prepare'),{'error':'sockets_probe_failed'})
        self.assertTrue((self.state/'current.json').is_file(),'failed preparation must retain its indexed stage')
        job=self.prepare();self.assertEqual(self.call('apply',job)['value']['code'],'sockets_probe_failed')
        self.assertEqual(len(list((self.state/'operations').iterdir())),1);self.assertFalse(self.installed())
    def test_status_is_passive_and_does_not_prepare_or_create_state(self):
        self.assertEqual(self.call('status'),{'value':{'state':'unavailable','code':'sockets_unprepared'}})
        self.assertFalse(self.state.exists());self.assertFalse(self.installed())

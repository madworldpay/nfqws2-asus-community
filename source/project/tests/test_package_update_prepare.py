import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import time
import unittest
from test_dpi_normalize import PHP, PUBLIC


class PackageUpdatePrepareTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.pkg=self.base/'package.ipk'
        self.candidate={'package_version':'1.3.1-asus6+b11','package':{'family':'aarch64-3.10','filename':'nfqws2-asus_1.3.1-asus6+b11_aarch64-3.10.ipk'}}
        self.package()

    def package(self, **fields):
        control={'Package':'nfqws2-asus','Version':'1.3.1-asus6+b11','Architecture':'aarch64-3.10','Depends':'iptables, libc', 'Conflicts':'nfqws-asus-web','Replaces':'nfqws-asus-web'}
        control.update(fields)
        raw=''.join(f'{k}: {v}\n' for k,v in control.items()).encode();inner=io.BytesIO()
        with tarfile.open(fileobj=inner,mode='w:gz') as archive:
            info=tarfile.TarInfo('./control');info.size=len(raw);archive.addfile(info,io.BytesIO(raw))
        with tarfile.open(self.pkg,'w:gz') as archive:
            for name,data in [('control.tar.gz',inner.getvalue()),('data.tar.gz',gzip.compress(b'\0'*1024)),('debian-binary',b'2.0\n')]:
                info=tarfile.TarInfo(name);info.size=len(data);archive.addfile(info,io.BytesIO(data))
        self.candidate['package'].update(size=self.pkg.stat().st_size,sha256=hashlib.sha256(self.pkg.read_bytes()).hexdigest())

    def status(self, depends='iptables, libc', other=''):
        return 'Package: nfqws2-asus\nVersion: 1.3.1-asus6+b10\nArchitecture: aarch64-3.10\nStatus: install ok installed\nDepends: '+depends+'\n\n'+''.join('Package: '+p+'\nVersion: 1\nStatus: install ok installed\n\n' for p in ['iptables','libc'])+other

    def add_control_members(self, members):
        with tarfile.open(self.pkg) as outer:
            original={m.name:outer.extractfile(m).read() for m in outer if m.isfile()}
        stream=io.BytesIO()
        with tarfile.open(fileobj=stream,mode='w:gz') as target:
            with tarfile.open(fileobj=io.BytesIO(original['control.tar.gz'])) as source:
                for member in source:
                    target.addfile(member,source.extractfile(member))
            for name,data,kind in members:
                info=tarfile.TarInfo(name);info.mode=0o755;info.type=kind
                if kind==tarfile.SYMTYPE:info.linkname='/bin/sh'
                else:info.size=len(data)
                target.addfile(info,io.BytesIO(data) if info.isfile() else None)
        original['control.tar.gz']=stream.getvalue()
        with tarfile.open(self.pkg,'w:gz') as target:
            for name,data in original.items():
                info=tarfile.TarInfo(name);info.size=len(data);target.addfile(info,io.BytesIO(data))
        self.candidate['package'].update(size=self.pkg.stat().st_size,sha256=hashlib.sha256(self.pkg.read_bytes()).hexdigest())

    @staticmethod
    def helper_elf(arm=False, size=64):
        # Header-only fixtures are inspected as bytes and never executed.
        header=bytearray(20);header[:4]=b'\x7fELF';header[4]=1 if arm else 2;header[5]=1
        header[18:20]=(40 if arm else 183).to_bytes(2,'little')
        return bytes(header)+os.urandom(size-20)

    def test_reinstall_bootstrap_is_inspected_without_execution(self):
        self.add_control_members([('busybox-migration-aarch64-3.10',self.helper_elf(size=400000),tarfile.REGTYPE)])
        self.assertIn('value',self.call())
        self.candidate['package']['family']='armv7';self.package(Architecture='all')
        self.add_control_members([(name,self.helper_elf(arm=True),tarfile.REGTYPE) for name in ['busybox-migration-armv7-2.6','busybox-migration-armv7-3.2']])
        for abi in ['armv7-2.6','armv7-3.2']:self.assertIn('value',self.call(abi=abi,machine='armv7l'))

    def test_bootstrap_unknown_foreign_malformed_and_links_are_refused(self):
        for name,data,kind in [
            ('busybox-migration-other',self.helper_elf(),tarfile.REGTYPE),
            ('busybox-migration-armv7-2.6',self.helper_elf(arm=True),tarfile.REGTYPE),
            ('busybox-migration-aarch64-3.10',self.helper_elf(arm=True),tarfile.REGTYPE),
            ('busybox-migration-aarch64-3.10',b'#!/bin/sh\nexit 0',tarfile.REGTYPE),
            ('busybox-migration-aarch64-3.10',b'',tarfile.SYMTYPE),
        ]:
            with self.subTest(name=name,kind=kind):
                self.package();self.add_control_members([(name,data,kind)])
                self.assertEqual(self.call(),{'error':'invalid_package'})

    def test_bootstrap_and_script_size_limits_remain_bounded(self):
        for name,data in [('busybox-migration-aarch64-3.10',self.helper_elf(size=1048577)),('preinst',b'x'*131073)]:
            self.package();self.add_control_members([(name,data,tarfile.REGTYPE)])
            self.assertEqual(self.call(),{'error':'invalid_package'})

    def test_decompressed_control_cannot_exceed_four_mib_even_by_one_byte(self):
        with tarfile.open(self.pkg) as outer:
            members={m.name:outer.extractfile(m).read() for m in outer if m.isfile()}
        raw=gzip.decompress(members['control.tar.gz'])
        members['control.tar.gz']=gzip.compress(raw+b'\0'*(4194305-len(raw)))
        with tarfile.open(self.pkg,'w:gz') as outer:
            for name,data in members.items():
                info=tarfile.TarInfo(name);info.size=len(data);outer.addfile(info,io.BytesIO(data))
        self.candidate['package'].update(size=self.pkg.stat().st_size,sha256=hashlib.sha256(self.pkg.read_bytes()).hexdigest())
        self.assertEqual(self.call(),{'error':'invalid_package'})

    def call(self, action='inspect', **kwargs):
        payload={'action':action,'candidate':self.candidate,'status':self.status(), 'abi':'aarch64-3.10','machine':'aarch64',**kwargs}
        code='''if(!is_file($argv[1].'/update-prepare.php')){echo json_encode(['error'=>'missing_prepare']);exit;}
        require $argv[1].'/update-prepare.php';$p=json_decode(stream_get_contents(STDIN),true);
        try{if($p['action']==='inspect')$v=AsusUpdatePackage::inspect($argv[2],$p['candidate'],$p['status'],$p['abi'],$p['machine']);
        elseif($p['action']==='space')$v=AsusUpdatePackage::space($p['free'],$p['ipk'],$p['snapshot'],$p['runtime']);
        elseif($p['action']==='snapshot')$v=AsusUpdateSnapshot::capture($argv[3],$argv[4],(int)$argv[5]);
        else $v=AsusUpdateSnapshot::verify($argv[3],$argv[4],(int)$argv[5],$p['allow_defaults']??false);echo json_encode(['value'=>$v]);
        }catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        r=subprocess.run([PHP,'-n','-d','memory_limit=16M','-r',code,str(PUBLIC),str(self.pkg),str(self.base/'opt'),str(self.base/'backup'),str(os.getuid())],input=json.dumps(payload),capture_output=True,text=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stderr,'');return json.loads(r.stdout)

    def test_exact_ipk_and_installed_dependencies_are_required(self):
        result=self.call();self.assertIn('value',result);self.assertEqual(result['value']['Version'],'1.3.1-asus6+b11')
        self.assertEqual(self.call(status=self.status().replace('Package: libc','Package: missing')),{'error':'missing_dependencies'})

    def test_user_installed_flag_is_healthy_but_hold_is_not_automatically_changed(self):
        self.assertIn('value',self.call(status=self.status().replace('install ok installed','install user installed')))
        self.assertEqual(self.call(status=self.status().replace('install ok installed','install hold installed')),{'error':'pending_packages'})

    def test_obsolete_uninstalled_version_does_not_shadow_the_installed_package(self):
        obsolete='Package: nfqws2-asus\nVersion: 1.3.1-asus6+b7\nStatus: install prefer,user not-installed\n\n'
        for status in [obsolete+self.status(),self.status()+obsolete]:
            with self.subTest(status=status):self.assertIn('value',self.call(status=status))

    def test_uninstalled_record_cannot_hide_pending_or_unknown_flags(self):
        for state in ['install hold not-installed','install unknown not-installed','install user unpacked']:
            with self.subTest(state=state):
                record='Package: nfqws2-asus\nVersion: 1.3.1-asus6+b7\nStatus: '+state+'\n\n'
                self.assertEqual(self.call(status=self.status()+record),{'error':'pending_packages'})

    def test_two_installed_versions_are_still_an_invalid_database(self):
        self.assertEqual(self.call(status=self.status()+self.status().split('\n\n')[0]+'\n\n'),{'error':'pending_packages'})

    def test_old_dependency_removal_and_foreign_pending_configuration_are_refused(self):
        self.assertEqual(self.call(status=self.status('iptables, libc, old-auto-dep')),{'error':'dependency_change'})
        self.assertEqual(self.call(status=self.status(other='Package: other\nVersion: 1\nStatus: install ok unpacked\n')),{'error':'pending_packages'})

    def test_unknown_or_incompatible_primary_abi_and_cpu_refused(self):
        for abi,machine in [('armv7-2.6','armv7l'),('armv7-3.2','armv7l'),('mipsel-3.4','mips'),('aarch64-3.10','x86_64')]:
            self.assertEqual(self.call(abi=abi,machine=machine),{'error':'unsupported_abi'})
        self.candidate['package']['family']='armv7';self.package(Architecture='all')
        for abi in ['armv7-2.6','armv7-3.2']:self.assertIn('value',self.call(abi=abi,machine='armv7l'))

    def test_wrong_package_version_arch_and_dependency_grammar_refused(self):
        for changes in [{'Package':'other'},{'Version':'1.3.1-asus6+b9'},{'Architecture':'all'},{'Depends':'libc | evil'},{'Replaces':'other'}]:
            self.package(**changes)
            self.assertIn('error',self.call(),changes)

    def test_hash_size_and_truncated_archive_refused_without_extracting_scripts(self):
        self.pkg.write_bytes(self.pkg.read_bytes()+b'x')
        self.assertEqual(self.call(),{'error':'download_size'})
        self.candidate['package']['size']=self.pkg.stat().st_size
        self.assertEqual(self.call(),{'error':'download_hash'})
        self.pkg.write_bytes(b'not a tar archive');self.candidate['package'].update(size=self.pkg.stat().st_size,sha256=hashlib.sha256(self.pkg.read_bytes()).hexdigest())
        self.assertEqual(self.call(),{'error':'invalid_package'})

    def test_tiny_header_member_cannot_allocate_an_unbounded_decompressed_buffer(self):
        with tarfile.open(self.pkg) as archive:control=archive.extractfile('control.tar.gz').read()
        with tarfile.open(self.pkg,'w:gz') as archive:
            for name,data in [('control.tar.gz',control),('debian-binary',b'X'*(20*1024*1024)),('data.tar.gz',gzip.compress(b'\0'*1024))]:
                info=tarfile.TarInfo(name);info.size=len(data);archive.addfile(info,io.BytesIO(data))
        self.candidate['package'].update(size=self.pkg.stat().st_size,sha256=hashlib.sha256(self.pkg.read_bytes()).hexdigest())
        self.assertEqual(self.call(),{'error':'invalid_package'})

    def test_space_includes_copy_backup_runtime_and_reserve(self):
        self.assertEqual(self.call('space',free=16*1024*1024+299,ipk=100,snapshot=100,runtime=100),{'error':'insufficient_space'})
        self.assertEqual(self.call('space',free=16*1024*1024+300,ipk=100,snapshot=100,runtime=100),{'value':True})

    def fixture(self):
        opt=self.base/'opt';config=opt/'etc/nfqws2';config.mkdir(parents=True)
        (config/'nfqws2.conf').write_text('PRIVATE_CONFIG');(config/'nfqws2.conf').chmod(0o640)
        lists=config/'lists';lists.mkdir();(lists/'domains.list').write_text('example.com\n')
        web=opt/'etc/nfqws-asus-web';web.mkdir();(web/'auth.json').write_text('{"SECRET":"PRIVATE"}');(web/'auth.json').chmod(0o600)
        (web/'unrelated').write_text('NOT_A_CONFIG')
        return opt,config,web

    def test_snapshot_copies_allowed_files_with_mode_and_hash_and_detects_later_edit(self):
        opt,config,web=self.fixture();result=self.call('snapshot');self.assertIn('value',result)
        self.assertEqual((self.base/'backup/etc/nfqws2/nfqws2.conf').read_text(),'PRIVATE_CONFIG')
        self.assertEqual((self.base/'backup/etc/nfqws2/nfqws2.conf').stat().st_mode&0o777,0o640)
        self.assertFalse((self.base/'backup/etc/nfqws-asus-web/unrelated').exists())
        self.assertEqual(self.call('verify'),{'value':True})
        (config/'nfqws2.conf').write_text('EDITED')
        self.assertEqual(self.call('verify'),{'error':'settings_changed'})

    def test_snapshot_symlink_never_reads_target_and_low_space_never_creates_backup(self):
        opt,config,web=self.fixture();outside=self.base/'outside';outside.write_text('PRIVATE_OUTSIDE')
        (config/'linked.conf').symlink_to(outside)
        self.assertEqual(self.call('snapshot'),{'error':'invalid_state'})
        self.assertFalse((self.base/'backup/etc/nfqws2/linked.conf').exists())
    def test_postflight_allows_package_defaults_but_never_active_settings_to_change(self):
        opt,config,web=self.fixture();stock=config/'nfqws2.conf.notactive';stock.write_text('old template');stock.chmod(0o600)
        self.assertIn('value',self.call('snapshot'));stock.write_text('new package template')
        self.assertEqual(self.call('verify'),{'error':'settings_changed'})
        self.assertEqual(self.call('verify',allow_defaults=True),{'value':True})
        (config/'nfqws2.conf').write_text('changed active settings')
        self.assertEqual(self.call('verify',allow_defaults=True),{'error':'settings_changed'})

    def test_only_engine_owned_list_files_are_accepted_as_delegated_settings(self):
        code="require $argv[1].'/update-prepare.php';if(!method_exists('AsusUpdateSnapshot','ownerAllowed')){echo 'missing';exit;} $m=new ReflectionMethod('AsusUpdateSnapshot','ownerAllowed');echo json_encode([$m->invoke(null,'etc/nfqws2/lists/auto.list',['uid'=>65534,'mode'=>0100766],0),$m->invoke(null,'etc/nfqws2/lists/auto.list-opkg.backup',['uid'=>65534,'mode'=>0100766],0),$m->invoke(null,'etc/nfqws2/nfqws2.conf',['uid'=>65534,'mode'=>0100644],0),$m->invoke(null,'etc/nfqws-asus-web/auth.json',['uid'=>65534,'mode'=>0100600],0),$m->invoke(null,'etc/nfqws2/lists',['uid'=>65534,'mode'=>0040755],0),$m->invoke(null,'etc/nfqws2/lists/user.list',['uid'=>123,'mode'=>0100644],0)]);"
        r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC)],capture_output=True,text=True,timeout=5)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stdout,'[true,true,false,false,false,false]')
    def test_snapshot_tracks_original_owner_and_group_but_keeps_backup_private(self):
        opt,config,web=self.fixture();self.assertIn('value',self.call('snapshot'))
        snapshot=json.loads((self.base/'backup/snapshot.json').read_text());row=snapshot['files']['etc/nfqws2/nfqws2.conf']
        self.assertEqual(row.get('uid'),os.getuid());self.assertEqual(row.get('gid'),(config/'nfqws2.conf').stat().st_gid)
        self.assertEqual((self.base/'backup/etc/nfqws2/nfqws2.conf').stat().st_uid,os.getuid())
    def stock_baseline(self,opt,resources):
        folder=opt/'share/nfqws2-asus';folder.mkdir(parents=True,exist_ok=True)
        (folder/'report-baseline.json').write_text(json.dumps({'schema_version':1,'resources':{name:{'sha256':hashlib.sha256(value.encode()).hexdigest(),'bytes':len(value)} for name,value in resources.items()}}));(folder/'report-baseline.json').chmod(0o644)
    def test_stock_resources_may_change_be_added_or_removed_after_install(self):
        opt,config,web=self.fixture();(config/'lua').mkdir();(config/'blobs').mkdir()
        (config/'lua/stock.lua').write_text('old');(config/'blobs/obsolete.bin').write_text('obsolete');(config/'lua/custom.lua').write_text('CUSTOM')
        self.stock_baseline(opt,{'lua/stock.lua':'old','blob/obsolete.bin':'obsolete'})
        self.assertIn('value',self.call('snapshot'))
        (config/'lua/stock.lua').write_text('new');(config/'blobs/obsolete.bin').unlink();(config/'lua/added.lua').write_text('added')
        self.stock_baseline(opt,{'lua/stock.lua':'new','lua/added.lua':'added'})
        self.assertEqual(self.call('verify'),{'error':'settings_changed'})
        self.assertEqual(self.call('verify',allow_defaults=True),{'value':True})
        (config/'lua/custom.lua').write_text('OVERWRITTEN');self.assertEqual(self.call('verify',allow_defaults=True),{'error':'settings_changed'})
    def test_customized_stock_resource_is_refused_before_snapshot_or_service_stop(self):
        opt,config,web=self.fixture();(config/'lua').mkdir();(config/'lua/stock.lua').write_text('MY CUSTOMIZATION')
        self.stock_baseline(opt,{'lua/stock.lua':'original stock'})
        self.assertEqual(self.call('snapshot'),{'error':'settings_changed'})
        self.assertFalse((self.base/'backup').exists())


class PackageUpdateCoordinatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.key=Path(cls.tmp.name)/'key.pem'
        subprocess.run(['openssl','genpkey','-algorithm','RSA','-pkeyopt','rsa_keygen_bits:3072','-out',str(cls.key)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        cls.public=subprocess.check_output(['openssl','pkey','-in',str(cls.key),'-pubout']).decode()
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def setUp(self):
        self.fixture=PackageUpdatePrepareTests('test_exact_ipk_and_installed_dependencies_are_required');self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.base=self.fixture.base;opt,config,web=self.fixture.fixture()
        (opt/'lib/opkg').mkdir(parents=True);(opt/'lib/opkg/status').write_text(self.fixture.status())
        self.manifest={'schema_version':1,'package_version':'1.3.1-asus6+b11','core_version':'1.3.1-asus6','web_version':'0.1.4','build':11,'notes':'Real test release.','packages':[self.fixture.candidate['package']]}
    def call(self, commands, error=None, free=100000000, installed_key=False):
        import base64
        raw=json.dumps(self.manifest,separators=(',',':'));sig=base64.b64encode(subprocess.check_output(['openssl','dgst','-sha256','-sign',str(self.key)],input=raw.encode())).decode()
        payload={'json':raw,'signature':sig,'public':None if installed_key else self.public,'commands':commands,'error':error,'free':free}
        if installed_key:
            resource=self.base/'resources';resource.mkdir(exist_ok=True)
            (resource/'update-release-key.pem').write_text(self.public)
        php=os.environ.get('PHP_TLS_TEST_BINARY',PHP);extension=os.environ.get('PHP_OPENSSL_TEST_EXTENSION')
        code='''require $argv[1].'/update-prepare.php';if(!class_exists('AsusUpdatePrepare')){echo json_encode(['error'=>'missing_coordinator']);exit;}
        $p=json_decode(stream_get_contents(STDIN),true);$count=0;
        $source=new class($p,$argv[2]) implements AsusUpdateSource{public function __construct(private array $p,private string $base){}
          public function manifest():array{file_put_contents($this->base.'/fetches','x',FILE_APPEND);if($this->p['error'])throw new RuntimeException($this->p['error']);return ['json'=>$this->p['json'],'signature'=>$this->p['signature']];}
          public function download(array $package,string $destination):void{copy($this->base.'/package.ipk',$destination);chmod($destination,0600);}};
        try{$resolved=AsusDpiStore::optPath('/var',$argv[2].'/opt');$resolved=dirname($resolved);$s=new AsusUpdateStore($argv[2].'/state',(int)$argv[3]);$c=new AsusUpdatePrepare($s,$source,['opt'=>$resolved,'resources'=>$argv[2].'/resources','abi'=>'aarch64-3.10','machine'=>'aarch64','owner'=>(int)$argv[3],'free'=>$p['free'],'runtime_bytes'=>1000],$p['public']);
        $out=[];foreach($p['commands'] as $cmd){if(in_array($cmd[0],['prepare','reserveCached'],true)&&$cmd[1][0]==='REV')$cmd[1][0]=hash('sha256',$p['json']);$out[]=$c->{$cmd[0]}(...$cmd[1]);}echo json_encode($out);
        }catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        argv=[php,'-n']+(['-d','extension='+extension] if extension else [])+['-r',code,str(PUBLIC),str(self.base),str(os.getuid())]
        r=subprocess.run(argv,input=json.dumps(payload),capture_output=True,text=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stderr,'');return json.loads(r.stdout)
    def test_check_is_cached_and_network_failure_is_never_current(self):
        r=self.call([['check',[]],['check',[]]])
        self.assertIsInstance(r,list);self.assertEqual(r[0]['state'],'available');self.assertEqual((self.base/'fetches').read_text(),'x')
        r=self.call([['check',[True]]],error='download_failed');self.assertEqual(r[0]['state'],'failed');self.assertIsNone(r[0]['candidate'])

    def test_installed_public_key_filename_matches_the_actual_ipk_layout(self):
        r=self.call([['check',[]]],installed_key=True)
        self.assertIsInstance(r,list);self.assertEqual(r[0]['state'],'available')
    def test_stale_candidate_cannot_download_and_prepare_is_idempotent(self):
        self.assertEqual(self.call([['prepare',['b'*64,'1'*32]]]),{'error':'stale_revision'})
        r=self.call([['prepare',['REV','1'*32]],['prepare',['REV','1'*32]]]);self.assertIsInstance(r,list)
        self.assertEqual(r[0]['id'],r[1]['id']);self.assertEqual(r[0]['state'],'prepared')
        self.assertEqual((self.base/'state/operations'/r[0]['id']/'package.ipk').read_bytes(),self.fixture.pkg.read_bytes())
    def test_cached_reservation_does_not_contact_network_in_http_request(self):
        r=self.call([['check',[]],['reserveCached',['REV','1'*32]],['reserveCached',['REV','1'*32]]])
        self.assertIsInstance(r,list);self.assertEqual(r[1]['state'],'preparing');self.assertEqual(r[1]['id'],r[2]['id'])
        self.assertEqual((self.base/'fetches').read_text(),'x')
        self.assertFalse((self.base/'state/operations'/r[1]['id']/'package.ipk').exists())
    def test_cached_reservation_requires_fresh_available_metadata(self):
        self.assertEqual(self.call([['reserveCached',['REV','1'*32]]]),{'error':'stale_revision'})
    def test_new_verified_release_can_replace_a_stale_prepared_operation(self):
        old=self.call([['prepare',['REV','1'*32]]])[0]
        self.fixture.package(Version='1.3.1-asus6+b12');self.fixture.candidate['package']['filename']='nfqws2-asus_1.3.1-asus6+b12_aarch64-3.10.ipk'
        self.manifest.update(package_version='1.3.1-asus6+b12',build=12)
        result=self.call([['check',[True]],['reserveCached',['REV','2'*32]]])
        self.assertIsInstance(result,list);self.assertEqual(result[1]['state'],'preparing');self.assertNotEqual(old['id'],result[1]['id'])
    def test_metadata_network_wait_does_not_hold_the_status_journal(self):
        source='''require $argv[1].'/update-prepare.php';$s=new AsusUpdateStore($argv[2].'/state',(int)$argv[3]);
        $source=new class($argv[2]) implements AsusUpdateSource{public function __construct(private string $base){}public function manifest():array{file_put_contents($this->base.'/waiting','yes');usleep(1000000);throw new RuntimeException('download_failed');}public function download(array $p,string $d):void{}};
        (new AsusUpdatePrepare($s,$source,['opt'=>$argv[2].'/opt','abi'=>'aarch64-3.10','machine'=>'aarch64','owner'=>(int)$argv[3]]))->check(true);'''
        child=subprocess.Popen([PHP,'-n','-r',source,str(PUBLIC),str(self.base),str(os.getuid())],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            end=time.monotonic()+3
            while not (self.base/'waiting').exists() and time.monotonic()<end:time.sleep(.01)
            self.assertTrue((self.base/'waiting').exists())
            status='require $argv[1]."/update-store.php";try{echo json_encode((new AsusUpdateStore($argv[2]."/state",(int)$argv[3]))->status());}catch(Throwable $e){echo json_encode(["error"=>$e->getMessage()]);}'
            result=subprocess.run([PHP,'-n','-r',status,str(PUBLIC),str(self.base),str(os.getuid())],capture_output=True,text=True,timeout=3)
            self.assertEqual(json.loads(result.stdout),{'active':None,'history':[]})
        finally:
            out,err=child.communicate(timeout=5);self.assertEqual(child.returncode,0,err.decode());self.assertEqual(out,b'')
    def test_insufficient_space_fails_before_download_or_setting_changes(self):
        r=self.call([['prepare',['REV','1'*32]]],free=100)
        self.assertIsInstance(r,list);self.assertEqual(r[0]['state'],'failed');self.assertEqual(r[0]['code'],'insufficient_space')
        self.assertFalse(any((self.base/'state').glob('operations/*/package.ipk')))
        self.assertEqual((self.base/'opt/etc/nfqws2/nfqws2.conf').read_text(),'PRIVATE_CONFIG')

    def test_opt_alias_to_internal_storage_prepares_without_usb_or_mount_name(self):
        internal=self.base/'jffs'/'entware';internal.parent.mkdir();(self.base/'opt').rename(internal)
        (self.base/'opt').symlink_to(internal,target_is_directory=True)
        r=self.call([['prepare',['REV','1'*32]]]);self.assertIsInstance(r,list);self.assertEqual(r[0]['state'],'prepared')
        self.assertEqual((internal/'etc/nfqws2/nfqws2.conf').read_text(),'PRIVATE_CONFIG')

    def test_opt_alias_to_external_storage_prepares_without_fixed_usb_path(self):
        external=self.base/'mnt'/'disk1'/'entware';external.parent.mkdir(parents=True);(self.base/'opt').rename(external)
        (self.base/'opt').symlink_to(external,target_is_directory=True)
        r=self.call([['prepare',['REV','1'*32]]]);self.assertIsInstance(r,list);self.assertEqual(r[0]['state'],'prepared')
        self.assertEqual((external/'etc/nfqws2/nfqws2.conf').read_text(),'PRIVATE_CONFIG')


if __name__=='__main__':unittest.main()

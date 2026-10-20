"""Run a staged matching PHP after the original execution tree is removed."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from test_dpi_normalize import PHP, PUBLIC, ROOT

ABI=os.environ.get('UPDATE_RUNTIME_ABI','aarch64')
AUDIT=ROOT/'.work/packaging-audit-20261012'
TLS=Path(os.environ.get('PHP_TLS_FIXTURE_ROOT',Path.home()/'.local/state/nfqws2-asus/development/support-email-20261015/tls'))/ABI
SYSROOT=AUDIT/(ABI+'-sysroot')


class PackageUpdateRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name)
        self.opt=self.base/'original/opt';self.opt.mkdir(parents=True)
        shutil.copytree(SYSROOT/'opt/lib',self.opt/'lib',symlinks=True)
        shutil.copytree(TLS/'opt/lib',self.opt/'lib',dirs_exist_ok=True,symlinks=True)
        (self.opt/'bin').mkdir();shutil.copy2(SYSROOT/'opt/bin/php8-cgi',self.opt/'bin/php-cgi')
        self.application=self.base/'original/app';shutil.copytree(PUBLIC,self.application,ignore=shutil.ignore_patterns('*.js','*.css','assets','*.svg','*.png'))
        for p in self.application.rglob('*'):
            if p.is_file():p.chmod(0o644)
        self.entry=self.base/'original/entry.php';self.entry.write_text('<?php require __DIR__."/app/update-store.php";echo json_encode(["ready"=>true,"ssl"=>extension_loaded("openssl"),"maps"=>file_get_contents("/proc/self/maps")]);')
        self.entry.chmod(0o644);self.runtime=self.base/'runtime'
        # Unchanged base data belongs to the timezone package, not this update.
        # Keep only that data in QEMU's prefix; no original interpreter/libs.
        self.system=self.base/'system';shutil.copytree(SYSROOT/'opt/share/zoneinfo',self.system/'opt/share/zoneinfo',symlinks=True)
        resources=self.base/'original/resources';resources.mkdir()
        for source,name in [('package-manifest.schema.json','package-manifest.schema.json'),('trusted-release-key.pem','update-release-key.pem')]:
            shutil.copyfile(ROOT/'updates'/source,resources/name);(resources/name).chmod(0o644)
        launcher=self.base/'original/update-launch';shutil.copyfile(ROOT/'asus/update/bin'/('aarch64-opkg-launch' if ABI=='aarch64' else 'armv7-opkg-launch'),launcher);launcher.chmod(0o755)
        self.config={'opt':str(self.opt),'binary':str(self.opt/'bin/php-cgi'),'application':str(self.application),'entry':str(self.entry),
                     'resources':str(resources),'launcher':str(launcher)}
    def call(self,action='stage',**options):
        code='''if(!is_file($argv[1].'/update-runtime.php')){echo json_encode(['error'=>'missing_runtime']);exit;}
        require $argv[1].'/update-runtime.php';$p=json_decode(stream_get_contents(STDIN),true);
        try{$v=$p['action']==='stage'?AsusUpdateRuntime::stage($argv[2],$p['config'],(int)$argv[3]):AsusUpdateRuntime::load($argv[2],(int)$argv[3]);echo json_encode(['value'=>$v]);}
        catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(self.runtime),str(os.getuid())],input=json.dumps({'action':action,'config':{**self.config,**options}}),capture_output=True,text=True,timeout=20)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stderr,'');return json.loads(r.stdout)
    def test_staged_php_and_openssl_run_after_original_tree_disappears(self):
        result=self.call();self.assertIn('value',result)
        self.assertTrue((self.runtime/'check.sh').is_file(),'native installer preflight must use the staged interpreter')
        self.assertTrue((self.runtime/'run.sh').is_file(),'detached guardian must use only the immutable staged closure')
        before=json.loads((self.runtime/'closure.json').read_text());self.assertLess(before['bytes'],32*1024*1024)
        shutil.rmtree(self.base/'original')
        loaded=self.call('load');self.assertIn('value',loaded)
        runner=AUDIT/('qemu-aarch64' if ABI=='aarch64' else 'qemu-arm')
        r=subprocess.run([str(runner),'-L',str(self.system),*loaded['value']['argv'],'--','noop','a'*32],capture_output=True,text=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stderr,'')
        answer=json.loads(r.stdout);self.assertTrue(answer['ready']);self.assertTrue(answer['ssl'])
        self.assertNotIn(str(self.base/'original'),answer['maps'])
        for file,record in before['files'].items():
            p=self.runtime/file;self.assertEqual(p.stat().st_mode&0o777,record['mode']);self.assertFalse(p.is_symlink())
            self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),record['sha256'])
    def test_all_installed_defaults_resolve_the_supported_opt_alias(self):
        alias=self.base/'opt-alias';alias.symlink_to(self.opt,target_is_directory=True)
        app=self.opt/'share/nfqws-asus-web';shutil.copytree(self.application,app)
        dpi=app/'dpi-store.php';dpi.write_text(dpi.read_text().replace("string $alias='/opt'","string $alias="+json.dumps(str(alias))))
        for source,dest in [(self.entry,self.opt/'lib/nfqws2-asus/update/worker.php'),(Path(self.config['launcher']),self.opt/'libexec/nfqws2-asus/update-launch')]:
            dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
        shutil.copytree(self.config['resources'],self.opt/'share/nfqws2-asus')
        code="require $argv[1].'/update-runtime.php';try{$r=AsusUpdateRuntime::stage($argv[2],['binary'=>$argv[3]],(int)$argv[4]);echo json_encode(['ready'=>true]);}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}"
        r=subprocess.run([PHP,'-n','-r',code,str(app),str(self.runtime),self.config['binary'],str(os.getuid())],capture_output=True,text=True,timeout=20)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(json.loads(r.stdout),{'ready':True})
    def test_modified_or_replaced_closure_file_never_executes(self):
        self.assertIn('value',self.call());(self.runtime/'app/update-store.php').write_text('<?php echo "UNTRUSTED";')
        self.assertEqual(self.call('load'),{'error':'runtime_changed'})
    def test_symlink_and_existing_runtime_are_never_overwritten(self):
        outside=self.base/'outside';outside.mkdir();(outside/'keep').write_text('KEEP');self.runtime.symlink_to(outside,target_is_directory=True)
        self.assertEqual(self.call(),{'error':'invalid_state'});self.assertEqual((outside/'keep').read_text(),'KEEP')
    def test_space_refusal_precedes_creation_and_unsupported_elf_is_refused(self):
        self.assertEqual(self.call(free=1),{'error':'insufficient_space'});self.assertFalse(self.runtime.exists())
        (self.opt/'bin/php-cgi').write_text('#!/bin/sh\necho NO\n')
        self.assertEqual(self.call(),{'error':'unsupported_runtime'});self.assertFalse(self.runtime.exists())
    def test_library_alias_must_resolve_inside_trusted_entware_lib(self):
        source=self.opt/'lib/php8/openssl.so';source.unlink();outside=self.base/'foreign.so';outside.write_bytes(b'FOREIGN');source.symlink_to(outside)
        self.assertEqual(self.call(),{'error':'invalid_state'});self.assertFalse(self.runtime.exists())


if __name__=='__main__':unittest.main()

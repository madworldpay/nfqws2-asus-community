"""A read-only baseline binds previews to DNS files, firmware settings and engine."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_dpi_normalize import PHP,PUBLIC


class SmartDnsBaselineTests(unittest.TestCase):
    def collect(self,changes=None,nvram='',operation=None):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ['opt','proc','tmp','jffs','etc','sys','ark']:(root/name).mkdir()
            files={'tmp/etc/dnsmasq.conf':'interface=br0\ndhcp-range=192.0.2.10,192.0.2.20\nresolv-file=/tmp/resolv.dnsmasq\n',
                   'tmp/resolv.dnsmasq':'nameserver 9.9.9.9\n','proc/sys/kernel/random/boot_id':'12345678-1234-1234-1234-123456789abc\n',
                   'jffs/scripts/dnsmasq.postconf':'#!/bin/sh\nprintf "foreign"\n'}
            files.update(changes or {})
            for name,body in files.items():
                f=root/name
                if body is not None:f.parent.mkdir(parents=True,exist_ok=True);f.write_text(body)
            hook=root/'jffs/scripts/dnsmasq.postconf'
            if hook.exists():hook.chmod(0o755)
            if operation=='unsafe_mode':hook.chmod(0o777)
            if operation=='nonexec_mode':hook.chmod(0o644)
            command=root/'nvram';command.write_text("#!/bin/sh\ncat <<'FIXTURE'\njffs2_scripts=1\nwan0_dnsenable_x=0\nwan0_dns1_x=9.9.9.9\n"+nvram+"\nFIXTURE\n");command.chmod(0o700)
            before={str(f.relative_to(root)):f.read_bytes() for f in root.rglob('*') if f.is_file()}
            code=r'''$file=$argv[1].'/smartdns-baseline.php';if(!is_file($file)){echo json_encode(['error'=>'missing_baseline']);exit;}
            require $file;$r=$argv[2];$roots=[];foreach(['opt','proc','tmp','jffs','etc','sys','ark'] as $name)$roots[$name]=$r.'/'.$name;
            $roots['commands']=['nvram'=>[$r.'/nvram']];$engine=str_repeat('a',64);
            $deps=['owner'=>(int)$argv[3],'engine'=>function()use(&$engine){return ['sha256'=>$engine,'version'=>'48.4'];}];
            try{
              $b=new AsusSmartDnsBaseline(new AsusReportIO($roots),new AsusSmartDnsInstaller(),$deps);$out=[$b->collect()];
              if($argv[4]==='config')file_put_contents($r.'/tmp/etc/dnsmasq.conf',"server=1.1.1.1\n");
              if($argv[4]==='engine')$engine=str_repeat('b',64);
              $out[]=$b->collect();echo json_encode($out);
            }catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
            p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(root),str(os.getuid()),operation or 'none'],capture_output=True,text=True,timeout=8)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'')
            if operation is None:self.assertEqual(before,{str(f.relative_to(root)):f.read_bytes() for f in root.rglob('*') if f.is_file()})
            return json.loads(p.stdout)

    def test_unchanged_readonly_baseline_is_stable_and_preserves_private_snapshot(self):
        out=self.collect();self.assertIsInstance(out,list)
        self.assertEqual(out[0]['hash'],out[1]['hash']);self.assertEqual(out[0]['conflicts'],[])
        self.assertIn('foreign',out[0]['snapshot']['hook']['value'])

    def test_config_and_engine_changes_invalidate_the_preview_hash(self):
        for operation in ['config','engine']:
            with self.subTest(operation=operation):
                out=self.collect(operation=operation);self.assertIsInstance(out,list)
                self.assertNotEqual(out[0]['hash'],out[1]['hash'])

    def test_foreign_runtime_configuration_is_a_conflict_not_a_takeover(self):
        out=self.collect({'opt/etc/smartdns/smartdns.conf':'server-https https://example.org/?PRIVATE_CANARY\n'})
        self.assertIsInstance(out,list);self.assertIn('external_smartdns',out[0]['conflicts'])
        self.assertNotIn('PRIVATE_CANARY',json.dumps(out))

    def test_conditional_routes_and_early_exit_are_visible_conflicts(self):
        for changes,expected in [({'tmp/etc/dnsmasq.conf':'server=/corp.example/192.0.2.1\n'},'existing_dns_rules'),
                                 ({'jffs/scripts/dnsmasq.postconf':'#!/bin/sh\nexit 0\n'},'hook_conflict')]:
            with self.subTest(expected=expected):
                out=self.collect(changes);self.assertIsInstance(out,list);self.assertIn(expected,out[0]['conflicts'])

    def test_missing_generated_config_is_not_an_empty_safe_baseline(self):
        self.assertEqual(self.collect({'tmp/etc/dnsmasq.conf':None}),{'error':'baseline_unavailable'})

    def test_writable_foreign_hook_is_never_accepted_for_root_execution(self):
        out=self.collect(operation='unsafe_mode');self.assertIsInstance(out,list)
        self.assertIn('hook_permissions',out[0]['conflicts'])

    def test_nonexecutable_hook_cannot_silently_skip_the_new_forwarder(self):
        out=self.collect(operation='nonexec_mode');self.assertIsInstance(out,list)
        self.assertIn('hook_permissions',out[0]['conflicts'])

    def test_usb_or_unverified_local_resolver_cannot_be_independent_fallback(self):
        # A rollback that still needs the lost USB is not an independent path.
        for config in ['resolv-file=/opt/etc/resolv.conf\n',
                       'server=127.0.0.1#5353\n', 'server=::1#5453\n',
                       'servers-file=/opt/etc/servers.conf\n']:
            with self.subTest(config=config):
                out=self.collect({'tmp/etc/dnsmasq.conf':config})
                self.assertIsInstance(out,list)
                self.assertIn('native_fallback_unavailable',out[0]['conflicts'])

    def test_missing_default_resolver_is_not_a_working_native_fallback(self):
        out=self.collect({'tmp/resolv.dnsmasq':'# no upstream\n'})
        self.assertIsInstance(out,list);self.assertIn('native_fallback_unavailable',out[0]['conflicts'])


if __name__=='__main__':unittest.main()

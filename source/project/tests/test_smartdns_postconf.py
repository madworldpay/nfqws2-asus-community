"""Native config regeneration must preserve LAN names and fail closed on includes."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_dpi_normalize import ROOT

LIB=ROOT/'asus/smartdns'


class SmartDnsPostconfTests(unittest.TestCase):
    def filter(self,config,server_file='server=9.9.9.9\n'):
        script=LIB/'forwarding.awk'
        if not script.is_file():return 2,b'missing_native_forwarding'
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'resolv.dnsmasq';source.write_text(server_file)
            p=subprocess.run(['/bin/busybox','awk','-v','servers1='+str(source),'-v','servers2=/never-present','-f',str(script)],input=config.replace(b'/tmp/resolv.dnsmasq',str(source).encode()),capture_output=True,timeout=3)
            self.assertEqual(p.stderr,b'');return p.returncode,p.stdout

    def test_known_default_sources_replaced_local_names_and_dhcp_kept(self):
        rc,out=self.filter(b'interface=br0\ndhcp-range=192.0.2.2,192.0.2.9\nlocal=/lan/\naddress=/router.lan/192.0.2.1\nserver=9.9.9.9\nservers-file=/tmp/resolv.dnsmasq\nno-resolv\nall-servers\n')
        self.assertEqual(rc,0)
        self.assertEqual(out,b'interface=br0\ndhcp-range=192.0.2.2,192.0.2.9\nlocal=/lan/\naddress=/router.lan/192.0.2.1\nno-resolv\nserver=127.0.0.1#6054\n')

    def test_conditional_routes_dynamic_includes_or_missing_source_are_rejected(self):
        for body,servers in [(b'server=/corp.example/192.0.2.1\n',''),(b'conf-file=/tmp/include\n',''),
                             (b'conf-script=/opt/bin/generate\n',''),(b'conf-dir=/tmp/conf.d\n',''),
                             (b'servers-file=/unknown\n',''),(b'servers-file=/tmp/resolv.dnsmasq\n','server=/corp.example/192.0.2.1\n')]:
            with self.subTest(body=body):self.assertNotEqual(self.filter(body,servers)[0],0)

    def test_only_fixed_config_is_changed_after_native_syntax_check(self):
        source=LIB/'lifecycle.sh'
        self.assertTrue(source.is_file(),'missing_native_lifecycle')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);jffs=root/'jffs';jffs.mkdir(mode=0o700)
            (root/'app').mkdir(mode=0o700)
            alias=root/'firmware-dnsmasq.conf'
            config=root/'dnsmasq.conf';config.write_text('interface=br0\nserver=9.9.9.9\n');config.chmod(0o600)
            outside=root/'outside';outside.write_text('untouched')
            boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
            ticks=Path('/proc/self/stat').read_text().rsplit(') ',1)[1].split()[19]
            exe=os.readlink('/proc/self/exe')
            state=dict(schema='1',request_id='e'*32,boot_id=boot,phase='awaiting_confirmation',deadline='99999999.000',guard_pid=str(os.getpid()),guard_ticks=ticks,runtime_pid=str(os.getpid()),runtime_ticks=ticks,runtime_exe=exe,hook_created='0',profile_hash='f'*64)
            def write_state():
                (jffs/'state').write_text(''.join(k+'\t'+v+'\n' for k,v in state.items()));(jffs/'state').chmod(0o600)
            write_state();(jffs/'state.lock').touch(mode=0o600)
            syntax=root/'dnsmasq';syntax.write_text('#!/bin/sh\n[ "$1" = --test ] && [ "$2" = --conf-file="'+str(config)+'.nfqws2.new" ] || exit 9\n[ ! -f "'+str(root/'syntax-fail')+'" ]\n');syntax.chmod(0o700)
            for name in ['native-state.sh','native-common.sh','primary-dns.sh','lifecycle.sh','forwarding.awk']:
                text=(LIB/name).read_text().replace('/jffs/nfqws2-asus-smartdns',str(jffs)).replace('/opt/etc/nfqws-asus-web',str(root/'app')).replace('/tmp/etc/dnsmasq.conf',str(config)).replace('/etc/dnsmasq.conf',str(alias)).replace('/usr/sbin/dnsmasq',str(syntax)).replace('sd_owner=0','sd_owner='+str(os.getuid()))
                (jffs/name).write_text(text);(jffs/name).chmod(0o700)
            def run(path):return subprocess.run(['/bin/sh',str(jffs/'lifecycle.sh'),'postconf',str(path)],capture_output=True,timeout=5)
            self.assertNotEqual(run(outside).returncode,0);self.assertEqual(outside.read_text(),'untouched')
            original=config.read_bytes();(root/'syntax-fail').touch()
            self.assertNotEqual(run(config).returncode,0);self.assertEqual(config.read_bytes(),original)
            (root/'syntax-fail').unlink();self.assertEqual(run(config).returncode,0)
            self.assertEqual(config.read_text(),'interface=br0\nno-resolv\nserver=127.0.0.1#6054\n')
            self.assertEqual(config.stat().st_mode&0o777,0o600)
            # Merlin chmods the generated file to 0644 only AFTER postconf.
            config.write_bytes(original);config.chmod(0o666)
            self.assertEqual(run(config).returncode,0,'secure the firmware staging mode before the protected edit')
            self.assertEqual(config.stat().st_mode&0o777,0o644)
            self.assertIn('server=127.0.0.1#6054',config.read_text())
            config.write_bytes(original);config.chmod(0o777)
            self.assertNotEqual(run(config).returncode,0,'do not adopt an executable/world-writable file')
            self.assertEqual(config.read_bytes(),original)
            config.chmod(0o600)
            config.write_bytes(original);alias.symlink_to(config)
            self.assertEqual(run(alias).returncode,0,'Merlin passes its fixed /etc alias to postconf')
            self.assertIn('server=127.0.0.1#6054',config.read_text())
            alias.unlink();alias.symlink_to(outside);config.write_bytes(original)
            self.assertNotEqual(run(alias).returncode,0);self.assertEqual(config.read_bytes(),original)
            alias.unlink();alias.symlink_to(config)
            for patch in [dict(boot_id='00000000-0000-0000-0000-000000000000'),dict(phase='rolling_back'),dict(runtime_ticks=str(int(ticks)+1))]:
                saved=dict(state);state.update(patch);write_state();config.write_bytes(original)
                self.assertEqual(run(config).returncode,0);self.assertEqual(config.read_bytes(),original)
                state=saved
            # A mapped executable can survive removal of the USB file. A
            # subsequent firmware DNS regeneration must leave native DNS.
            import time
            code=root/'engine.c';code.write_text('#include <unistd.h>\nint main(void){for(;;)sleep(1);}\n')
            engine=root/'engine';subprocess.run(['gcc',str(code),'-o',str(engine)],capture_output=True,check=True)
            child=subprocess.Popen([str(engine)])
            try:
                for _ in range(100):
                    if os.readlink(f'/proc/{child.pid}/exe')==str(engine):break
                    time.sleep(.005)
                state.update(runtime_pid=str(child.pid),runtime_ticks=Path(f'/proc/{child.pid}/stat').read_text().rsplit(') ',1)[1].split()[19],runtime_exe=str(engine))
                write_state();engine.unlink();config.write_bytes(original)
                self.assertEqual(run(config).returncode,0);self.assertEqual(config.read_bytes(),original)
            finally:child.terminate();child.wait()


if __name__=='__main__':unittest.main()

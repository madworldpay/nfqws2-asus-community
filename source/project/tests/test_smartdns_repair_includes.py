"""Exercise the one-off repair against the native recovery filesystem fixture."""
import fcntl
import hashlib
import os
from pathlib import Path
import subprocess
import unittest
import test_smartdns_recovery as recovery

REPAIR=recovery.LIB/'repair-includes.sh'


class SmartDnsIncludeRepairTests(unittest.TestCase):
    def setUp(self):
        self.case=recovery.SmartDnsRecoveryTests();self.case.setUp();self.addCleanup(self.case.tearDown)
        self.assertTrue(REPAIR.is_file(),'missing include recovery repair')
        self.root=self.case.root
        self.case.state(phase='conflict')
        source=self.case.jffs/'native-common.sh'
        self.payload=self.root/'download.sh';self.payload.write_bytes(source.read_bytes())
        source.write_text(source.read_text()+'\nsd_restored_config() { return 1; }\n')
        self.original=source.read_bytes()
        include=self.root/'vpn.conf';self.vpn=include
        include.write_text('filter-AAAA\nipset=/video.example/awg_dst\nno-resolv\nserver=1.1.1.1@awg0\n');include.chmod(0o600)
        apply=self.root/'apply-dns.sh'
        apply.write_text(apply.read_text()+'printf "conf-file=%s\\n" "'+str(include)+'" >> "'+str(self.root/'dnsmasq.conf')+'"\n')
        self.updates=self.case.opt/'updates';self.updates.mkdir(mode=0o700);(self.updates/'apply.lock').touch(mode=0o600)
        self.bin=self.root/'bin';self.bin.mkdir()
        curl=self.bin/'curl'
        curl.write_text('#!/bin/sh\nwhile [ "$#" -gt 0 ];do if [ "$1" = -o ];then shift;cp "'+str(self.payload)+'" "$1";exit;fi;shift;done\nexit 9\n');curl.chmod(0o700)
        control=self.bin/'control'
        control.write_text('#!/bin/sh\n[ "$1" = status ] || exit 9\nprintf \'{"state":"rolled_back"}\\n\'\n');control.chmod(0o700)
        php=self.bin/'php'
        php.write_text('#!/bin/sh\n[ ! -e "'+str(self.root/'live-installer')+'" ]\n');php.chmod(0o700)
        self.helper=self.root/'repair.sh'
        text=REPAIR.read_text().replace('nfqws_owner=0','nfqws_owner='+str(os.getuid()))
        text=text.replace('PATH=', 'PATH='+str(self.bin)+':',1)
        text=text.replace('/jffs/nfqws2-asus-smartdns',str(self.case.jffs))
        text=text.replace('/opt/var/lib/nfqws2-asus/updates',str(self.updates))
        text=text.replace('/opt/bin/nfqws2-smartdns-control',str(control))
        text=text.replace('/opt/bin/php-cgi',str(php))
        expected=hashlib.sha256((recovery.LIB/'native-common.sh').read_bytes()).hexdigest()
        text=text.replace(expected,hashlib.sha256(self.payload.read_bytes()).hexdigest())
        self.helper.write_text(text)

    def run_repair(self):
        p=subprocess.run(['/bin/busybox','ash',str(self.helper)],capture_output=True,text=True,timeout=25)
        self.assertEqual((self.case.jffs/'native-common.sh').read_bytes(),self.original)
        self.assertIn('server=1.1.1.1@awg0',self.vpn.read_text())
        self.assertIsNone(self.case.foreign.poll())
        return p

    def test_repair_restores_dns_without_modifying_installed_recovery_or_vpn(self):
        p=self.run_repair();self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        self.assertEqual(self.case.read_state()['phase'],'rolled_back')
        self.case.runtime.wait(timeout=2)
        self.assertEqual(self.case.hook.read_bytes(),b'#!/bin/sh\n# foreign\n\n# later foreign edit')

    def test_unverified_download_does_not_change_dns(self):
        self.payload.write_bytes(self.payload.read_bytes()+b'\n')
        p=self.run_repair();self.assertNotEqual(p.returncode,0)
        self.assertEqual(self.case.read_state()['phase'],'conflict')
        self.assertEqual(self.case.events.read_text(),'');self.assertIsNone(self.case.runtime.poll())

    def test_active_update_prevents_repair_without_removing_any_lock(self):
        with (self.updates/'apply.lock').open('r+') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            p=self.run_repair();self.assertNotEqual(p.returncode,0)
            self.assertEqual(self.case.read_state()['phase'],'conflict')
            self.assertEqual(self.case.events.read_text(),'')
        self.assertTrue((self.updates/'apply.lock').is_file())

    def test_live_installer_with_released_worker_lease_prevents_repair(self):
        (self.root/'live-installer').touch()
        p=self.run_repair();self.assertNotEqual(p.returncode,0)
        self.assertEqual(self.case.read_state()['phase'],'conflict')
        self.assertEqual(self.case.events.read_text(),'');self.assertIsNone(self.case.runtime.poll())


if __name__=='__main__':unittest.main()

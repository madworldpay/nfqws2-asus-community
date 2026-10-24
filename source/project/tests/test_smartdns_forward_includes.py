"""VPN-style DNS includes stay data; policy survives managed forwarding."""
import json
import os
from pathlib import Path
import signal
import subprocess
import unittest
from test_dpi_normalize import PHP, PUBLIC
import test_smartdns_connect as hooks
import test_smartdns_recovery as recovery


class ForwardIncludeTests(unittest.TestCase):
    def render(self, text, files):
        return hooks.SmartDnsHookTests().call('forwarding', text, files)

    def test_global_dns_in_include_is_replaced_without_discarding_policy(self):
        policy = 'filter-AAAA\nipset=/video.example/geo_dst\nlocal=/office/\ndhcp-option=tag:guest,6,192.0.2.1\n'
        result = self.render('interface=br0\nconf-file=/opt/vpn/dns.conf\n',
                             {'/opt/vpn/dns.conf': policy+'no-resolv\nserver=1.1.1.1@vpn0\nserver=1.0.0.1@vpn0\n'})
        self.assertIn('value', result)
        self.assertIn(policy, result['value'])
        self.assertNotIn('conf-file=', result['value'])
        self.assertNotIn('@vpn0', result['value'])
        self.assertEqual(result['value'].count('server=127.0.0.1#6054'), 1)

    def test_nested_repeated_includes_keep_original_directive_order(self):
        result = self.render('conf-file="/jffs/a.conf" # first\nconf-file=/jffs/a.conf\n',
                             {'/jffs/a.conf': 'tag-if=set:first,tag:source\nconf-file=/jffs/b.conf\n',
                              '/jffs/b.conf': 'tag-if=set:second,tag:first\n'})
        self.assertIn('value', result)
        expected = 'tag-if=set:first,tag:source\ntag-if=set:second,tag:first\n'
        self.assertIn(expected+expected, result['value'])

    def test_many_short_lines_within_byte_bounds_are_supported(self):
        result=self.render('conf-file=/opt/vpn/dns.conf\n',
                           {'/opt/vpn/dns.conf':'# policy entry\n'*4097+'server=1.1.1.1@vpn0\n'})
        self.assertIn('value',result)
        self.assertIn('server=127.0.0.1#6054',result['value'])

    def test_unsupported_routing_or_executable_includes_are_not_discarded(self):
        for body in ['server=/private.example/192.0.2.1\n', 'rev-server=192.0.2.0/24,192.0.2.1\n',
                     'conf-script=/jffs/program\n', 'conf-dir=/jffs/configs\n',
                     'conf-file=/jffs/a.conf\n']:
            with self.subTest(body=body):
                self.assertEqual(self.render('conf-file=/jffs/a.conf\n', {'/jffs/a.conf': body}),
                                 {'error': 'existing_dns_rules'})

    def test_unknown_or_ambiguous_paths_and_excess_output_fail(self):
        for text, files in [('conf-file=relative.conf\n', {}),
                            ('conf-file=/jffs/../a.conf\n', {}),
                            ('conf-file=/jffs/missing.conf\n', {}),
                            ('conf-file=/jffs/a.conf\nconf-file=/jffs/a.conf\n',
                             {'/jffs/a.conf': '#'+('x'*140000)+'\n'})]:
            with self.subTest(text=text):
                self.assertEqual(self.render(text, files), {'error': 'existing_dns_rules'})


class NativeForwardIncludeTests(unittest.TestCase):
    def setUp(self):
        self.case = recovery.SmartDnsRecoveryTests()
        self.case.setUp()
        self.addCleanup(self.case.tearDown)
        self.root = self.case.root
        guard = self.case.foreign.pid
        ticks = Path(f'/proc/{guard}/stat').read_text().rsplit(') ', 1)[1].split()[19]
        self.case.state(phase='confirmed', guard_pid=str(guard), guard_ticks=ticks)
        self.main = self.root/'dnsmasq.conf'
        self.include = self.root/'vpn.conf'
        self.policy = 'filter-AAAA\nipset=/video.example/geo_dst\nlocal=/office/\n'
        self.include.write_text(self.policy+'no-resolv\nserver=1.1.1.1@vpn0\n')
        self.include.chmod(0o600)
        self.main.write_text('interface=br0\nconf-file='+str(self.include)+'\n')
        self.main.chmod(0o600)
        checker = self.root/'dnsmasq-check'
        checker.write_text('#!/bin/sh\nexit 0\n')
        checker.chmod(0o700)
        for name in ['lifecycle.sh', 'forwarding.awk']:
            body = (recovery.LIB/name).read_text().replace('/jffs/nfqws2-asus-smartdns', str(self.case.jffs))
            body = body.replace('/tmp/etc/dnsmasq.conf', str(self.main)).replace('/usr/sbin/dnsmasq', str(checker))
            (self.case.jffs/name).write_text(body)
            (self.case.jffs/name).chmod(0o700)

    def run_postconf(self, timeout=8):
        p = subprocess.Popen(['/bin/busybox', 'ash', str(self.case.jffs/'lifecycle.sh'), 'postconf', str(self.main)],
                             stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
        try:
            stdout,stderr=p.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid,signal.SIGKILL);p.communicate()
            self.fail('postconf exceeded bounded processing time')
        return subprocess.CompletedProcess(p.args,p.returncode,stdout,stderr)

    def apply(self):
        before = self.include.read_bytes()
        p = self.run_postconf()
        self.assertEqual(self.include.read_bytes(), before)
        return p

    def test_postconf_keeps_policy_and_uses_managed_default_with_foreign_file_unchanged(self):
        p = self.apply()
        self.assertEqual(p.returncode, 0, p.stdout+p.stderr)
        text = self.main.read_text()
        self.assertIn(self.policy, text)
        self.assertNotIn('conf-file=', text)
        self.assertNotIn('@vpn0', text)
        self.assertIn('server=127.0.0.1#6054', text)

    def test_include_changed_during_syntax_check_is_not_installed_from_stale_rendering(self):
        before=self.main.read_bytes()
        checker=self.root/'dnsmasq-check'
        checker.write_text('#!/bin/sh\nprintf "%s\\n" "ipset=/new.example/geo_dst" "server=1.1.1.1@vpn0" > "'+str(self.include)+'"\nexit 0\n')
        p=self.run_postconf()
        self.assertNotEqual(p.returncode,0)
        self.assertEqual(self.main.read_bytes(),before)
        self.assertIn('ipset=/new.example/geo_dst',self.include.read_text())

    def test_many_short_include_lines_match_the_php_byte_bounds(self):
        self.include.write_text('# policy entry\n'*4097+'server=1.1.1.1@vpn0\n')
        p=self.apply()
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        self.assertEqual(self.main.read_text().count('# policy entry'),4097)

    def test_repeated_discarded_directives_are_bounded_before_filtering(self):
        middle=self.root/'middle.conf'
        leaf=self.root/'leaf.conf'
        leaf.write_text('server=1.1.1.1\n'*1000);leaf.chmod(0o600)
        middle.write_text(('conf-file='+str(leaf)+'\n')*1000);middle.chmod(0o600)
        self.include.write_text(('conf-file='+str(middle)+'\n')*1000)
        before=self.main.read_bytes()
        p=self.run_postconf(timeout=2)
        self.assertNotEqual(p.returncode,0)
        self.assertEqual(self.main.read_bytes(),before)

    def test_unsafe_include_does_not_replace_generated_main(self):
        before = self.main.read_bytes()
        self.include.chmod(0o666)
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(self.main.read_bytes(), before)

    def test_writable_include_parent_does_not_become_privileged_config_input(self):
        parent = self.root/'untrusted'
        parent.mkdir(mode=0o777)
        parent.chmod(0o777)
        moved = parent/'vpn.conf'
        moved.write_bytes(self.include.read_bytes())
        moved.chmod(0o600)
        self.main.write_text('conf-file='+str(moved)+'\n')
        before = self.main.read_bytes()
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(self.main.read_bytes(), before)

    def test_legacy_firmware_uses_packaged_hash_tool_without_requiring_native_applet(self):
        wrapper = self.root/'firmware-busybox'
        wrapper.write_text('#!/bin/sh\n[ "$1" != sha256sum ] || exit 127\nexec /bin/busybox "$@"\n')
        wrapper.chmod(0o700)
        state = self.case.jffs/'native-state.sh'
        state.write_text(state.read_text().replace('sd_bb=/bin/busybox', 'sd_bb='+str(wrapper)))
        common = self.case.jffs/'native-common.sh'
        common.write_text(common.read_text().replace('/opt/libexec/nfqws2-asus/busybox', '/bin/busybox'))
        p = self.apply()
        self.assertEqual(p.returncode, 0, p.stdout+p.stderr)
        self.assertIn('server=127.0.0.1#6054', self.main.read_text())

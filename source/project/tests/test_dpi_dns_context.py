"""Passive effective DNS identity: real protected files, no router or resolver changes."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'webui/web/public'
PHP = os.environ.get('PHP_TEST_BINARY', str(ROOT / '.work/packaging-audit-20261012/aarch64-cli-wrapper'))
UNKNOWN = {'schema_version': 1, 'state': 'unknown', 'sha256': None}


class DpiDnsContextTests(unittest.TestCase):
    def setUp(self):
        previous_umask = os.umask(0o077)
        self.addCleanup(os.umask, previous_umask)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in ['opt', 'tmp', 'etc', 'jffs']:
            (self.root / name).mkdir(mode=0o700)
        self.platform = 'asus-entware'
        self.primary_pid = 123
        self.config = '/tmp/etc/dnsmasq.conf'
        self.nvram = {'dnspriv_enable': '0', 'dnspriv_profile': '1', 'dnspriv_rulelist': '', 'dns_local_cache': '1'}
        self.native = {'state': None, 'healthy': False, 'forwarding': 'external'}
        self.processes = {'state': 'available', 'names': [], 'stubby_verified': True}
        self.write('/etc/resolv.conf', 'nameserver 127.0.0.1\n')
        self.write('/etc/hosts', '127.0.0.1 localhost\n')
        self.write('/tmp/resolv.dnsmasq', 'nameserver 9.9.9.9\n')
        self.write(self.config, 'resolv-file=/tmp/resolv.dnsmasq\n')

    def path(self, logical):
        if logical.startswith('/var/'):
            logical = '/tmp/' + logical[5:]
        return self.root / logical.lstrip('/')

    def write(self, logical, text, mode=0o600):
        path = self.path(logical)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_text(text)
        path.chmod(mode)
        return path

    def openwrt(self):
        self.platform = 'openwrt'
        self.config = '/var/etc/dnsmasq.conf.main'
        self.write(self.config, 'resolv-file=/tmp/resolv.dnsmasq\n')

    def firmware_layout(self):
        for item in self.path('/etc').iterdir():
            item.rename(self.path('/tmp/etc') / item.name)
        self.path('/etc').rmdir()
        self.path('/etc').symlink_to(self.path('/tmp/etc'))
        self.path('/tmp/etc').chmod(0o755)
        self.path('/tmp').chmod(0o777)
        self.write('/tmp/resolv.conf', 'nameserver 127.0.0.1\n')
        self.path('/etc/resolv.conf').unlink()
        self.path('/etc/resolv.conf').symlink_to(self.path('/tmp/resolv.conf'))

    def firmware_data(self):
        self.firmware_layout()
        self.path('/etc').unlink()
        self.path('/etc').symlink_to('tmp/etc')
        for path in ['/tmp/resolv.conf', '/tmp/resolv.dnsmasq', '/etc/hosts']:
            self.path(path).chmod(0o666)
        self.path(self.config).chmod(0o644)

    def ipv6_listener(self, udp_inode='111', tcp_inode='222', udp_state='07', tcp_state='0A'):
        self.openwrt()
        self.write('/etc/resolv.conf', 'search lan\nnameserver 127.0.0.1\nnameserver ::1\n')
        fields = ['S'] + ['0'] * 25
        fields[19] = '100'
        self.write('/proc/123/stat', '123 (dnsmasq) ' + ' '.join(fields) + '\n')
        self.write('/proc/sys/kernel/random/boot_id', '11111111-1111-1111-1111-111111111111\n')
        exe = self.path('/proc/123/exe')
        exe.unlink(missing_ok=True)
        exe.symlink_to('/usr/sbin/dnsmasq')
        fds = self.path('/proc/123/fd')
        fds.mkdir(exist_ok=True, mode=0o700)
        for fd in fds.iterdir():
            fd.unlink()
        for fd, inode in [('3', udp_inode), ('4', tcp_inode)]:
            (fds / fd).symlink_to('socket:[' + inode + ']')
        for protocol, inode, state in [('udp6', udp_inode, udp_state), ('tcp6', tcp_inode, tcp_state)]:
            self.write('/proc/net/' + protocol, self.socket_row(inode, state))

    @staticmethod
    def socket_row(inode, state):
        return ('0: 00000000000000000000000001000000:0035 '
                '00000000000000000000000000000000:0000 ' + state +
                ' 00000000:00000000 00:00000000 00000000 0 0 ' + inode + ' 2\n')

    def profile(self):
        return {'schema_version': 1, 'upstreams': [{'id': 'main', 'label': 'PRIVATE_CANARY label',
            'protocol': 'doh', 'address': '192.0.2.53', 'port': 443, 'tls_name': 'private.example',
            'url': 'https://private.example/dns-query?key=PRIVATE_CANARY', 'bootstrap': [],
            'default': True, 'domains': []}], 'records': [{'name': 'private.example',
            'include_subdomains': False, 'addresses': ['192.0.2.1'], 'checked_at': '2026-11-01'}]}

    def managed(self, profile=None, request='1' * 32):
        profile = profile or self.profile()
        store = '/etc/nfqws2-web/smartdns' if self.platform == 'openwrt' else '/opt/etc/nfqws-asus-web/smartdns'
        directory = self.path(store)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory.chmod(0o700)
        # Profile hash is computed by its existing, separately tested canonicalizer.
        code = "require $argv[1].'/smartdns-profile.php';$p=json_decode($argv[2],true);echo json_encode(['hash'=>AsusSmartDnsProfile::hash($p),'config'=>AsusSmartDnsProfile::render($p,6054)['config']]);"
        p = subprocess.run([PHP, '-n', '-r', code, str(PUBLIC), json.dumps(profile)], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        rendered = json.loads(p.stdout)
        journal = {'schema_version': 1, 'job': None, 'history': [], 'backups': [], 'active': {
            'profile': profile, 'profile_hash': rendered['hash'], 'backup_id': 'a' * 32}}
        self.write(store + '/state.json', json.dumps(journal))
        self.write(store + '/draft.json', json.dumps(profile))
        runtime = '/tmp/nfqws2-native-state/smartdns-runtime/runtime.conf' if self.platform == 'openwrt' else store + '/jobs/' + request + '/runtime.conf'
        self.write(runtime, rendered['config'] + (f'address /nfqws-{request}.example.net/1.0.0.1\n' if self.platform == 'openwrt' else ''))
        self.native = {'state': {'schema': '1', 'phase': 'confirmed', 'request_id': request,
            'profile_hash': rendered['hash'], 'runtime_exe': '/usr/lib/smartdns/' + 'b' * 64 + '/smartdns'},
            'healthy': True, 'forwarding': 'managed', 'engine_sha256': 'b' * 64,
            'argv': ['./smartdns' if self.platform == 'asus-entware' else '/usr/lib/smartdns/' + 'b' * 64 + '/smartdns',
                     '-f', '-c', runtime, '-p', str(Path(runtime).with_name('runtime.pid'))]}
        self.processes['names'] = ['smartdns']
        self.write(self.config, 'no-resolv\nserver=127.0.0.1#6054\n')
        self.write('/etc/ssl/certs/ca-certificates.crt' if self.platform == 'openwrt' else '/opt/etc/ssl/certs/ca-certificates.crt', 'FIXTURE CA\n')
        return store, runtime

    def collect(self, race=False, observe=False):
        self.write('/tmp/fixture-nvram.json', json.dumps(self.nvram))
        self.write('/tmp/fixture-native.json', json.dumps(self.native))
        self.write('/tmp/fixture-processes.json', json.dumps(self.processes))
        code = r'''$file=$argv[1].'/dpi-dns-context.php';if(!is_file($file)){echo '{"missing":"collector"}';exit;}
        require $file;$root=$argv[2];$roots=[];foreach(['opt','tmp','etc','jffs','proc']as $name)$roots['/'.$name]=$root.'/'.$name;
        $io=new AsusDpiDnsFiles($roots,(int)$argv[5]);
        if($argv[6]==='race')$io=new class($roots,(int)$argv[5])extends AsusDpiDnsFiles {
            private bool $changed=false;
            public function read(string $path,bool $resolver=false,bool $optional=false):?string {
                $value=parent::read($path,$resolver,$optional);
                if($path==='/tmp/resolv.dnsmasq'&&!$this->changed){$this->changed=true;file_put_contents($this->path($path),"nameserver 1.1.1.1\n");}
                return $value;
            }
        };
        if(in_array($argv[6],['etc-link-race','listener-identity-race','listener-fd-race','hosts-directory-race','hosts-content-race'],true))$io=new class($roots,(int)$argv[5],$argv[6])extends AsusDpiDnsFiles {
            private bool $changed=false;
            public function __construct(private array $fixtureRoots,int $owner,private string $race){parent::__construct($fixtureRoots,$owner);}
            public function read(string $path,bool $resolver=false,bool $optional=false):?string {
                $value=parent::read($path,$resolver,$optional);
                $hostsRace=str_starts_with($this->race,'hosts-');
                if(!$this->changed&&($hostsRace?str_starts_with($path,'/tmp/hosts/'):str_starts_with(basename($path),'dnsmasq.conf'))){
                    $this->changed=true;
                    if($this->race==='hosts-directory-race')file_put_contents($this->fixtureRoots['/tmp'].'/hosts/new-host','192.0.2.77 PRIVATE_CANARY.example'."\n");
                    elseif($this->race==='hosts-content-race')file_put_contents($this->path($path),'192.0.2.88 PRIVATE_CANARY.example'."\n");
                    elseif($this->race==='etc-link-race'){unlink($this->fixtureRoots['/etc']);symlink($this->fixtureRoots['/jffs'],$this->fixtureRoots['/etc']);}
                    elseif($this->race==='listener-identity-race'){$file=$this->fixtureRoots['/proc'].'/123/stat';file_put_contents($file,str_replace(' 100 ',' 200 ',file_get_contents($file)));}
                    else unlink($this->fixtureRoots['/proc'].'/123/fd/3');
                }
                return $value;
            }
        };
        $deps=['platform'=>$argv[3],'files'=>$io,'owner'=>(int)$argv[5],
          'primary'=>fn()=>['instance'=>'main','pid'=>(int)$argv[7],'config'=>$argv[4]],
          'nvram'=>fn()=>['state'=>'available','values'=>json_decode(file_get_contents($root.'/tmp/fixture-nvram.json'),true)],
          'native'=>fn()=>json_decode(file_get_contents($root.'/tmp/fixture-native.json'),true),
          'runtime_argv'=>fn($state)=>json_decode(file_get_contents($root.'/tmp/fixture-native.json'),true)['argv']??[],
          'stubby_proof'=>fn()=>json_decode(file_get_contents($root.'/tmp/fixture-processes.json'),true)['stubby_verified'],
          'processes'=>fn()=>json_decode(file_get_contents($root.'/tmp/fixture-processes.json'),true)];
        if($argv[6]==='diagnostic-throw')$deps['nvram']=fn()=>throw new RuntimeException('PRIVATE_CANARY /private/secret.txt');
        if($argv[6]==='diagnostic-processes-verify'){
            $reads=0;$deps['processes']=function()use(&$reads,$root){
                if(++$reads===1)return ['state'=>'available','names'=>[]];
                return json_decode(file_get_contents($root.'/tmp/fixture-processes.json'),true);
            };
        }
        echo json_encode($argv[8]==='observe'?AsusDpiDnsContext::observe($deps):AsusDpiDnsContext::collect($deps));'''
        before = {str(p.relative_to(self.root)): (p.lstat().st_mode, p.read_bytes()) for p in self.root.rglob('*') if p.is_file()}
        p = subprocess.run([PHP, '-n', '-r', code, str(PUBLIC), str(self.root), self.platform, self.config,
            str(os.getuid()), ('race' if race is True else race or 'none'), str(self.primary_pid), 'observe' if observe else 'collect'], capture_output=True, text=True, timeout=8)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(p.stderr, '')
        if not race:
            self.assertEqual(before, {str(p.relative_to(self.root)): (p.lstat().st_mode, p.read_bytes()) for p in self.root.rglob('*') if p.is_file()})
        value = json.loads(p.stdout)
        self.assertNotIn('PRIVATE_CANARY', p.stdout)
        return value

    def known(self, value):
        self.assertEqual(set(value), {'schema_version', 'state', 'sha256'})
        self.assertEqual(value['schema_version'], 1)
        self.assertEqual(value['state'], 'known', value)
        self.assertRegex(value['sha256'], r'^[a-f0-9]{64}$')
        return value

    def test_observer_preserves_exact_context_on_both_platforms(self):
        for platform in ['asus-entware', 'openwrt']:
            with self.subTest(platform=platform):
                if platform == 'openwrt':
                    self.openwrt()
                expected = self.known(self.collect())
                self.assertEqual(self.collect(observe=True), {'context': expected, 'failure': None})

    def test_observer_reports_real_untrusted_resolver_without_accepting_it(self):
        self.write('/tmp/resolv.dnsmasq', 'nameserver 9.9.9.9\n', mode=0o666)
        value = self.collect(observe=True)
        self.assertEqual(value['context'], UNKNOWN)
        self.assertEqual(self.collect(), UNKNOWN)
        self.assertEqual(value['failure']['stage'], 'resolvers')
        self.assertEqual(value['failure']['source'], 'dpi-dns-context.php')
        self.assertIsInstance(value['failure']['line'], int)
        self.assertGreater(value['failure']['line'], 0)
        self.assertLess(len(json.dumps(value['failure'])), 200)
        self.assertNotIn(str(self.root), json.dumps(value))
        self.write('/tmp/resolv.dnsmasq', 'nameserver 9.9.9.9\n')
        self.assertIsNone(self.collect(observe=True)['failure'])

    def test_observer_does_not_expose_exception_messages_or_external_paths(self):
        value = self.collect('diagnostic-throw', observe=True)
        self.assertEqual(value['context'], UNKNOWN)
        self.assertEqual(value['failure'], {'stage': 'nvram', 'source': 'external', 'line': 0})
        self.assertNotIn('secret', json.dumps(value))
        self.assertNotIn('PRIVATE_CANARY', json.dumps(value))

    def test_observer_distinguishes_closed_initial_process_scan_states(self):
        for state in ['missing', 'partial', 'truncated', 'timeout', 'denied']:
            with self.subTest(state=state):
                self.processes['state'] = state
                value = self.collect(observe=True)
                self.assertEqual(value['context'], UNKNOWN)
                self.assertEqual(self.collect(), UNKNOWN)
                self.assertEqual(value['failure']['stage'], 'processes_scan_' + state)
                self.assertEqual(set(value['failure']), {'stage', 'source', 'line'})
                self.assertEqual(value['failure']['source'], 'dpi-dns-context.php')

    def test_observer_distinguishes_final_process_scan_failure_on_both_platforms(self):
        for platform in ['asus-entware', 'openwrt']:
            if platform == 'openwrt':
                self.openwrt()
            for state in ['missing', 'partial', 'truncated', 'timeout', 'denied']:
                with self.subTest(platform=platform, state=state):
                    self.processes['state'] = state
                    value = self.collect('diagnostic-processes-verify', observe=True)
                    self.assertEqual(value['context'], UNKNOWN)
                    self.assertEqual(value['failure']['stage'], 'verify_scan_' + state)
                    self.assertEqual(value['failure']['source'], 'dpi-dns-context.php')

    def test_observer_never_copies_unknown_scan_state_values(self):
        for state in ['PRIVATE_CANARY /private/secret.txt', {'PRIVATE_CANARY': 'secret'}, None]:
            with self.subTest(state=state):
                self.processes['state'] = state
                value = self.collect(observe=True)
                self.assertEqual(value['context'], UNKNOWN)
                self.assertEqual(value['failure']['stage'], 'processes_scan_invalid')
                self.assertNotIn('secret', json.dumps(value))

    def test_plain_dns_stable_and_effective_upstream_change_invalidates_both_platforms(self):
        for native in [False, True]:
            with self.subTest(openwrt=native):
                if native:
                    self.openwrt()
                first = self.known(self.collect())
                self.assertEqual(first, self.collect())
                self.write('/tmp/resolv.dnsmasq', 'nameserver 8.8.8.8\n')
                self.assertNotEqual(first, self.known(self.collect()))
                self.write('/tmp/resolv.dnsmasq', 'nameserver 9.9.9.9\n')

    def test_managed_profile_change_and_runtime_are_bound_on_both_platforms(self):
        for native in [False, True]:
            with self.subTest(openwrt=native):
                if native:
                    self.openwrt()
                self.managed()
                first = self.known(self.collect())
                profile = self.profile()
                profile['upstreams'][0]['url'] += '-changed'
                self.managed(profile)
                self.assertNotEqual(first, self.known(self.collect()))

    def test_draft_metadata_history_and_restart_identity_do_not_change_effective_context(self):
        self.managed()
        first = self.known(self.collect())
        profile = self.profile()
        profile['upstreams'][0]['label'] = 'another label'
        profile['records'][0]['checked_at'] = '2026-11-08'
        store, _ = self.managed(profile, request='2' * 32)
        self.write(store + '/draft.json', '{"private":"PRIVATE_CANARY new draft"}')
        journal = json.loads(self.path(store + '/state.json').read_text())
        journal['history'] = [{'request_id': '3' * 32, 'state': 'rolled_back',
            'profile_hash': journal['active']['profile_hash'], 'baseline_hash': 'c' * 64, 'backup_id': None}]
        self.write(store + '/state.json', json.dumps(journal))
        self.native['state'].update(runtime_pid='999', guard_ticks='777', deadline='999.000')
        self.assertEqual(first, self.known(self.collect()))

    def test_openwrt_per_request_canary_is_verified_but_not_hashed(self):
        self.openwrt()
        self.managed()
        first = self.known(self.collect())
        _, runtime = self.managed(request='2' * 32)
        self.assertEqual(first, self.known(self.collect()))
        self.write(runtime, self.path(runtime).read_text().replace('1.0.0.1', '1.0.0.2'))
        self.assertEqual(self.collect(), UNKNOWN)

    def test_stale_profile_unhealthy_forwarding_and_untracked_local_chain_are_unknown(self):
        _, runtime = self.managed()
        self.write(runtime, self.path(runtime).read_text() + 'address /PRIVATE_CANARY.example/192.0.2.2\n')
        self.assertEqual(self.collect(), UNKNOWN)

        self.managed()
        self.native['healthy'] = False
        self.assertEqual(self.collect(), UNKNOWN)
        self.managed()
        self.native['forwarding'] = 'unknown'
        self.assertEqual(self.collect(), UNKNOWN)
        self.native = {'state': None, 'healthy': False, 'forwarding': 'external'}
        self.processes['names'] = ['AdGuardHome']
        self.write(self.config, 'no-resolv\nserver=127.0.0.1#5353\n')
        self.assertEqual(self.collect(), UNKNOWN)

    def test_live_runtime_using_another_config_is_not_the_journal_profile(self):
        for native in [False, True]:
            with self.subTest(openwrt=native):
                if native:
                    self.openwrt()
                self.managed()
                self.native['argv'][3] = '/tmp/PRIVATE_CANARY-other.conf'
                self.assertEqual(self.collect(), UNKNOWN)

    def test_dnsmasq_nested_sources_and_default_hosts_are_part_of_identity(self):
        self.write(self.config, 'conf-file=/jffs/dns-extra.conf\n')
        self.write('/jffs/dns-extra.conf', 'resolv-file=/tmp/resolv.dnsmasq\nserver=/PRIVATE_CANARY.example/192.0.2.53\n')
        first = self.known(self.collect())
        self.write('/jffs/dns-extra.conf', 'resolv-file=/tmp/resolv.dnsmasq\nserver=/PRIVATE_CANARY.example/192.0.2.54\n')
        second = self.known(self.collect())
        self.assertNotEqual(first, second)
        self.write('/etc/hosts', '127.0.0.1 localhost\n192.0.2.1 PRIVATE_CANARY.example\n')
        self.assertNotEqual(second, self.known(self.collect()))

    def test_dynamic_dhcp_hosts_directory_cannot_claim_a_known_context(self):
        for native in [False, True]:
            with self.subTest(openwrt=native):
                if native:
                    self.openwrt()
                self.known(self.collect())
                self.write(self.config, 'resolv-file=/tmp/resolv.dnsmasq\ndhcp-hostsdir=/tmp/dhcp-hosts\n')
                self.write('/tmp/dhcp-hosts/client', '00:11:22:33:44:55,192.0.2.1,PRIVATE_CANARY.example\n')
                self.assertEqual(self.collect(), UNKNOWN)
                self.write('/tmp/dhcp-hosts/client', '00:11:22:33:44:55,192.0.2.2,PRIVATE_CANARY.example\n')
                self.assertEqual(self.collect(), UNKNOWN)

    def test_multiple_resolver_files_are_unknown_across_mtime_selection_changes(self):
        for native in [False, True]:
            with self.subTest(openwrt=native):
                if native:
                    self.openwrt()
                self.known(self.collect())
                self.write(self.config, 'resolv-file=/tmp/resolv.dnsmasq\nconf-file=/jffs/extra-resolver.conf\n')
                self.write('/jffs/extra-resolver.conf', 'resolv-file=/tmp/resolv.conf.auto\n')
                first = self.path('/tmp/resolv.dnsmasq')
                second = self.write('/tmp/resolv.conf.auto', 'nameserver 1.1.1.1\n')
                os.utime(first, (1700000000, 1700000000))
                os.utime(second, (1700000001, 1700000001))
                self.assertEqual(self.collect(), UNKNOWN)
                os.utime(first, (1700000002, 1700000002))
                self.assertEqual(self.collect(), UNKNOWN)

    def test_no_resolv_ignores_multiple_disabled_resolver_files(self):
        self.write(self.config, 'no-resolv\nresolv-file=/tmp/resolv.dnsmasq\nresolv-file=/tmp/resolv.conf.auto\nserver=9.9.9.9\n')
        first = self.known(self.collect())
        self.write('/tmp/resolv.dnsmasq', 'nameserver 1.1.1.1\n')
        self.write('/tmp/resolv.conf.auto', 'nameserver 8.8.8.8\n')
        self.assertEqual(first, self.known(self.collect()))

    def test_openwrt_conf_directory_and_referenced_servers_file_are_bounded(self):
        self.openwrt()
        self.write(self.config, 'conf-dir=/tmp/dns-includes,*.conf\nresolv-file=/tmp/resolv.dnsmasq\n')
        self.write('/tmp/dns-includes/route.conf', 'servers-file=/tmp/extra-servers\n')
        self.write('/tmp/extra-servers', 'server=9.9.9.9\n')
        first = self.known(self.collect())
        self.write('/tmp/dns-includes/route2.conf', 'server=/private.example/192.0.2.1\n')
        self.assertNotEqual(first, self.known(self.collect()))

    def test_firmware_servers_file_is_observed_as_bounded_server_data(self):
        self.firmware_data()
        self.write(self.config, 'no-resolv\nservers-file=/tmp/resolv.dnsmasq\nno-poll\naddn-hosts=/etc/hosts\n', 0o644)
        self.write('/tmp/resolv.dnsmasq', '# firmware data\nserver=9.9.9.9\nrev-server=192.0.2.0/24,8.8.8.8\n', 0o666)
        first = self.known(self.collect())
        self.assertEqual(first, self.known(self.collect()))
        self.write('/tmp/resolv.dnsmasq', 'server=1.1.1.1\nrev-server=192.0.2.0/24,8.8.8.8\n', 0o666)
        self.assertNotEqual(first, self.known(self.collect()))
        self.assertEqual(self.collect(race=True), UNKNOWN)

    def test_servers_file_does_not_expand_nested_or_nonserver_directives(self):
        self.write(self.config, 'no-resolv\nservers-file=/jffs/server-data\n')
        self.write('/jffs/nested.conf', 'server=9.9.9.9\n')
        self.write('/jffs/other-hosts', '192.0.2.1 PRIVATE_CANARY.example\n')
        for directive in ['conf-file=/jffs/nested.conf', 'servers-file=/jffs/nested.conf',
                          'conf-script=/jffs/must-not-execute', 'conf-dir=/jffs',
                          'resolv-file=/tmp/resolv.dnsmasq', 'addn-hosts=/jffs/other-hosts',
                          'dhcp-hostsfile=/jffs/other-hosts', 'address=/private.example/192.0.2.1',
                          'no-resolv', 'nameserver 9.9.9.9']:
            with self.subTest(directive=directive):
                self.write('/jffs/server-data', 'server=8.8.8.8\n' + directive + '\n')
                self.assertEqual(self.collect(), UNKNOWN)

    def test_custom_servers_file_does_not_gain_fixed_firmware_write_permissions(self):
        self.firmware_data()
        self.write(self.config, 'no-resolv\nservers-file=/jffs/server-data\n', 0o644)
        self.write('/jffs/server-data', 'server=9.9.9.9\n', 0o666)
        self.assertEqual(self.collect(), UNKNOWN)

    def test_servers_file_preserves_local_upstream_guards_for_reverse_queries(self):
        self.write(self.config, 'no-resolv\nservers-file=/jffs/server-data\n')
        for line in ['rev-server=192.0.2.0/24,127.0.0.1#5353',
                     'rev-server=192.0.2.0/24,::1#5353',
                     'rev-server=192.0.2.0/24,::ffff:127.0.0.1#5353',
                     'server="127.0.0.1#5353"',
                     'rev-server=192.0.2.0/24,"127.0.0.1#5353"']:
            with self.subTest(line=line):
                self.write('/jffs/server-data', 'server=9.9.9.9\n' + line + '\n')
                self.assertEqual(self.collect(), UNKNOWN)

    def test_servers_file_comments_keep_ports_and_effective_identity_stable(self):
        self.write(self.config, 'no-resolv\nservers-file=/jffs/server-data\n')
        self.write('/jffs/server-data', '# initial comment\nserver=9.9.9.9#5353\nrev-server=192.0.2.0/24,8.8.8.8\n')
        first = self.known(self.collect())
        self.write('/jffs/server-data', '# changed comment\nserver=9.9.9.9#5353 # upstream\nrev-server=192.0.2.0/24,8.8.8.8 # reverse zone\n')
        self.assertEqual(first, self.known(self.collect()))

    def test_servers_file_allows_local_reverse_zones_without_an_upstream(self):
        self.write(self.config, 'no-resolv\nservers-file=/jffs/server-data\n')
        self.write('/jffs/server-data', 'server=9.9.9.9\nrev-server=192.0.2.0/24\n')
        self.known(self.collect())

    def test_legitimate_resolver_symlink_and_openwrt_var_alias_work(self):
        self.openwrt()
        self.write('/tmp/resolv.conf', 'nameserver 127.0.0.1\n')
        self.path('/etc/resolv.conf').unlink()
        self.path('/etc/resolv.conf').symlink_to(self.path('/tmp/resolv.conf'))
        self.known(self.collect())
        self.path('/etc/resolv.conf').unlink()
        self.path('/etc/resolv.conf').symlink_to('/proc/self/environ')
        self.assertEqual(self.collect(), UNKNOWN)

    def test_firmware_hosts_alias_is_read_without_following_arbitrary_data_links(self):
        self.write('/tmp/hosts', '127.0.0.1 localhost\n')
        self.path('/etc/hosts').unlink()
        self.path('/etc/hosts').symlink_to(self.path('/tmp/hosts'))
        first = self.known(self.collect())
        self.write('/tmp/hosts', '127.0.0.1 localhost\n192.0.2.1 PRIVATE_CANARY.example\n')
        self.assertNotEqual(first, self.known(self.collect()))
        self.path('/etc/hosts').unlink()
        self.path('/etc/hosts').symlink_to('/proc/self/environ')
        self.assertEqual(self.collect(), UNKNOWN)

    def test_firmware_etc_anchor_and_nonsticky_tmp_keep_protected_files_readable(self):
        self.firmware_layout()
        first = self.known(self.collect())
        self.assertEqual(first, self.known(self.collect()))
        self.write('/tmp/resolv.dnsmasq', 'nameserver 8.8.8.8\n')
        self.assertNotEqual(first, self.known(self.collect()))

    def test_firmware_direct_relative_etc_anchor_is_readable(self):
        self.firmware_layout()
        self.path('/etc').unlink()
        self.path('/etc').symlink_to('tmp/etc')
        first = self.known(self.collect())
        self.assertEqual(first, self.known(self.collect()))

    def test_fixed_writable_firmware_data_is_observed_and_content_changes_are_hashed(self):
        self.firmware_data()
        previous = self.known(self.collect())
        self.assertEqual(previous, self.known(self.collect()))
        changes = [('/tmp/resolv.conf', 'nameserver 9.9.9.9\n'),
                   ('/tmp/resolv.dnsmasq', 'nameserver 8.8.8.8\n'),
                   ('/etc/hosts', '127.0.0.1 localhost\n192.0.2.1 PRIVATE_CANARY.example\n')]
        for path, text in changes:
            with self.subTest(path=path):
                self.write(path, text, 0o666)
                current = self.known(self.collect())
                self.assertNotEqual(previous, current)
                previous = current

    def test_writable_firmware_data_requires_the_exact_nonsticky_tmp_anchor(self):
        self.firmware_data()
        for mode in [0o755, 0o1777]:
            with self.subTest(mode=oct(mode)):
                self.path('/tmp').chmod(mode)
                self.assertEqual(self.collect(), UNKNOWN)
        self.path('/tmp').chmod(0o777)
        self.known(self.collect())

    def test_writable_firmware_data_does_not_relax_configs_or_custom_inputs(self):
        self.firmware_data()
        for variant in ['config', 'include-fixed-data', 'custom-resolver', 'custom-alias', 'hosts-entry']:
            with self.subTest(variant=variant):
                self.write(self.config, 'resolv-file=/tmp/resolv.dnsmasq\n', 0o644)
                if variant == 'config':
                    self.path(self.config).chmod(0o666)
                elif variant == 'include-fixed-data':
                    self.write(self.config, 'conf-file=/tmp/resolv.dnsmasq\n', 0o644)
                elif variant == 'custom-resolver':
                    self.write('/jffs/resolv.conf', 'nameserver 9.9.9.9\n', 0o666)
                    self.write(self.config, 'resolv-file=/jffs/resolv.conf\n', 0o644)
                elif variant == 'custom-alias':
                    self.path('/jffs/resolver-link').symlink_to(self.path('/tmp/resolv.conf'))
                    self.write(self.config, 'resolv-file=/jffs/resolver-link\n', 0o644)
                else:
                    self.write('/tmp/hosts/entry', '192.0.2.1 PRIVATE_CANARY.example\n', 0o666)
                    self.write(self.config, 'resolv-file=/tmp/resolv.dnsmasq\naddn-hosts=/tmp/hosts\n', 0o644)
                self.assertEqual(self.collect(), UNKNOWN)

    def test_fixed_writable_firmware_data_keeps_read_race_and_hardlink_guards(self):
        self.firmware_data()
        self.known(self.collect())
        self.assertEqual(self.collect(race=True), UNKNOWN)
        os.link(self.path('/tmp/resolv.dnsmasq'), self.path('/tmp/other-link'))
        self.assertEqual(self.collect(), UNKNOWN)

    def test_fixed_writable_resolver_cannot_be_retargeted_to_another_fixed_file(self):
        self.firmware_data()
        self.known(self.collect())
        self.path('/tmp/resolv.dnsmasq').unlink()
        self.path('/tmp/resolv.dnsmasq').symlink_to(self.path('/tmp/resolv.conf'))
        self.assertEqual(self.collect(), UNKNOWN)

    def test_firmware_anchor_does_not_permit_insecure_descendants_or_other_aliases(self):
        self.firmware_layout()
        self.path('/tmp/etc').chmod(0o777)
        self.assertEqual(self.collect(), UNKNOWN)
        self.path('/tmp/etc').chmod(0o755)
        self.write('/tmp/insecure/extra.conf', 'server=9.9.9.9\n')
        self.path('/tmp/insecure').chmod(0o777)
        self.write(self.config, 'conf-file=/tmp/insecure/extra.conf\n')
        self.assertEqual(self.collect(), UNKNOWN)
        self.path('/etc').unlink()
        self.path('/etc').symlink_to(self.path('/jffs'))
        self.assertEqual(self.collect(), UNKNOWN)

    def test_firmware_etc_alias_retarget_during_snapshot_is_unknown(self):
        self.firmware_layout()
        self.assertEqual(self.collect(race='etc-link-race'), UNKNOWN)

    def test_firmware_anchor_requires_the_direct_etc_alias(self):
        self.firmware_layout()
        self.known(self.collect())
        self.path('/tmp/etc-alias').symlink_to(self.path('/tmp/etc'))
        for target in [self.path('/tmp/etc-alias'), 'tmp/etc-alias', 'tmp/../tmp/etc', './tmp/etc']:
            with self.subTest(target=str(target)):
                self.path('/etc').unlink()
                self.path('/etc').symlink_to(target)
                self.assertEqual(self.collect(), UNKNOWN)

    def test_additional_hosts_directory_tracks_contents_additions_and_removals(self):
        self.openwrt()
        self.write(self.config, 'resolv-file=/tmp/resolv.dnsmasq\naddn-hosts=/tmp/hosts\n')
        self.write('/tmp/hosts/10', '192.0.2.10 PRIVATE_CANARY.example\n')
        self.write('/tmp/hosts/2', '192.0.2.2 other.example\n')
        first = self.known(self.collect())
        self.assertEqual(first, self.known(self.collect()))
        self.write('/tmp/hosts/10', '192.0.2.11 PRIVATE_CANARY.example\n')
        second = self.known(self.collect())
        self.assertNotEqual(first, second)
        self.write('/tmp/hosts/new-host', '192.0.2.3 new.example\n')
        self.assertNotEqual(second, self.known(self.collect()))
        self.path('/tmp/hosts/new-host').unlink()
        self.assertEqual(second, self.known(self.collect()))

    def test_empty_additional_hosts_directory_is_a_known_input(self):
        self.openwrt()
        self.write(self.config, 'resolv-file=/tmp/resolv.dnsmasq\naddn-hosts=/tmp/hosts\n')
        self.path('/tmp/hosts').mkdir(mode=0o700)
        self.known(self.collect())

    def test_additional_hosts_directory_names_are_complete_and_alphabetical(self):
        for name in ['2', '10', '.entry', '#entry', 'entry~']:
            self.write('/tmp/hosts/' + name, '192.0.2.1 host.example\n')
        code = r'''require $argv[1].'/dpi-dns-context.php';
        $files=new AsusDpiDnsFiles(['/tmp'=>$argv[2].'/tmp'],(int)$argv[3]);
        echo json_encode($files->names('/tmp/hosts',null,true));'''
        p = subprocess.run([PHP, '-n', '-r', code, str(PUBLIC), str(self.root), str(os.getuid())], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stderr, '')
        self.assertEqual(json.loads(p.stdout), ['#entry', '.entry', '10', '2', 'entry~'])

    def test_additional_hosts_directory_rejects_unsafe_entries_and_limits(self):
        self.openwrt()
        for variant in ['symlink', 'fifo', 'writable-file', 'writable-directory', 'nested-directory', 'oversized', 'too-many']:
            with self.subTest(variant=variant):
                directory = '/tmp/hosts/' + variant
                self.write(self.config, 'resolv-file=/tmp/resolv.dnsmasq\naddn-hosts=' + directory + '\n')
                entry = self.write(directory + '/entry', '192.0.2.1 PRIVATE_CANARY.example\n')
                if variant == 'symlink':
                    entry.unlink()
                    entry.symlink_to(self.write('/jffs/other-hosts', '192.0.2.2 other.example\n'))
                elif variant == 'fifo':
                    entry.unlink()
                    os.mkfifo(entry, mode=0o600)
                elif variant == 'writable-file':
                    entry.chmod(0o666)
                elif variant == 'writable-directory':
                    self.path(directory).chmod(0o777)
                elif variant == 'nested-directory':
                    self.path(directory + '/subdirectory').mkdir(mode=0o700)
                elif variant == 'oversized':
                    entry.write_text('x' * 262145)
                else:
                    for i in range(129):
                        self.write(directory + f'/h{i}', '192.0.2.2 host.example\n')
                self.assertEqual(self.collect(), UNKNOWN)

    def test_additional_hosts_directory_and_entry_read_races_are_unknown(self):
        self.openwrt()
        self.write(self.config, 'resolv-file=/tmp/resolv.dnsmasq\naddn-hosts=/tmp/hosts\n')
        self.write('/tmp/hosts/entry', '192.0.2.1 PRIVATE_CANARY.example\n')
        for race in ['hosts-directory-race', 'hosts-content-race']:
            with self.subTest(race=race):
                self.assertEqual(self.collect(race=race), UNKNOWN)

    def test_hosts_file_reader_rejects_a_foreign_owned_regular_file(self):
        # A public, root-owned file exercises the owner guard without requiring chown privileges.
        foreign = Path('/usr/share/common-licenses/GPL-3')
        if not foreign.is_file() or foreign.stat().st_uid == os.getuid():
            self.skipTest('public foreign-owner sample unavailable')
        code = r'''require $argv[1].'/dpi-dns-context.php';$files=new AsusDpiDnsFiles(['/usr'=>'/usr'],(int)$argv[2]);
        try{$files->read('/usr/share/common-licenses/GPL-3');echo '"accepted"';}
        catch(Throwable $e){echo json_encode($e->getMessage());}'''
        p = subprocess.run([PHP, '-n', '-r', code, str(PUBLIC), str(os.getuid())], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stderr, '')
        self.assertEqual(json.loads(p.stdout), 'dns_context_unknown')

    def test_nonsticky_writable_tmp_without_the_firmware_anchor_is_unknown(self):
        self.path('/tmp').chmod(0o777)
        self.assertEqual(self.collect(), UNKNOWN)

    def test_ipv6_system_resolver_requires_both_primary_listener_sockets(self):
        self.ipv6_listener()
        first = self.known(self.collect())
        self.ipv6_listener(udp_inode='333', tcp_inode='444')
        self.assertEqual(first, self.known(self.collect()))
        self.write(self.config, 'no-resolv\nserver=::1#53\n')
        self.assertEqual(self.collect(), UNKNOWN)

    def test_ipv6_listener_missing_foreign_or_wrong_state_is_unknown(self):
        for variant in ['missing-udp', 'missing-tcp', 'foreign', 'udp-state', 'tcp-state', 'different-primary', 'different-exe']:
            with self.subTest(variant=variant):
                self.primary_pid = 123
                self.ipv6_listener()
                if variant == 'missing-udp':
                    self.path('/proc/123/fd/3').unlink()
                elif variant == 'missing-tcp':
                    self.path('/proc/123/fd/4').unlink()
                elif variant == 'foreign':
                    self.write('/proc/net/udp6', self.socket_row('111', '07') + self.socket_row('999', '07'))
                elif variant == 'udp-state':
                    self.write('/proc/net/udp6', self.socket_row('111', '01'))
                elif variant == 'tcp-state':
                    self.write('/proc/net/tcp6', self.socket_row('222', '01'))
                elif variant == 'different-primary':
                    self.primary_pid = 456
                else:
                    self.path('/proc/123/exe').unlink()
                    self.path('/proc/123/exe').symlink_to('/usr/bin/PRIVATE_CANARY')
                self.assertEqual(self.collect(), UNKNOWN)

    def test_ipv6_primary_identity_or_socket_owner_change_during_snapshot_is_unknown(self):
        for race in ['listener-identity-race', 'listener-fd-race']:
            with self.subTest(race=race):
                self.ipv6_listener()
                self.assertEqual(self.collect(race=race), UNKNOWN)

    def test_missing_required_unsafe_oversized_cycles_and_read_races_are_unknown(self):
        first = self.known(self.collect())
        self.path('/tmp/resolv.dnsmasq').unlink()
        self.assertEqual(self.collect(), UNKNOWN)
        self.write('/tmp/resolv.dnsmasq', 'nameserver 9.9.9.9\n', mode=0o666)
        self.assertEqual(self.collect(), UNKNOWN)
        self.write('/tmp/resolv.dnsmasq', 'x' * 262145)
        self.assertEqual(self.collect(), UNKNOWN)
        self.write('/tmp/resolv.dnsmasq', 'nameserver 9.9.9.9\n')
        self.assertEqual(self.collect(race=True), UNKNOWN)
        self.write('/tmp/resolv.dnsmasq', 'nameserver 9.9.9.9\n')
        self.write(self.config, 'conf-file=/jffs/cycle.conf\n')
        self.write('/jffs/cycle.conf', 'conf-file=/jffs/cycle.conf\n')
        self.assertEqual(self.collect(), UNKNOWN)
        self.assertNotEqual(first, UNKNOWN)

    def test_firmware_dot_config_and_nvram_are_bound_without_private_export(self):
        self.nvram['dnspriv_enable'] = '1'
        self.nvram['dnspriv_rulelist'] = '<192.0.2.53>853>PRIVATE_CANARY.example>PRIVATE_CANARY_PIN'
        self.processes['names'] = ['stubby']
        self.write('/etc/stubby/stubby.yml', 'listen_addresses:\n  - 127.0.0.1@5453\nupstream_recursive_servers:\n  - address_data: 192.0.2.53\n    tls_auth_name: PRIVATE_CANARY.example\n')
        self.write(self.config, 'no-resolv\nserver=127.0.0.1#5453\n')
        first = self.known(self.collect())
        self.nvram['dnspriv_rulelist'] += '-changed'
        self.assertNotEqual(first, self.known(self.collect()))
        self.path('/etc/stubby/stubby.yml').unlink()
        self.assertEqual(self.collect(), UNKNOWN)

    def test_stubby_without_proof_of_the_fixed_firmware_config_is_unknown(self):
        self.nvram['dnspriv_enable'] = '1'
        self.processes['names'] = ['stubby']
        self.processes['stubby_verified'] = False
        self.write('/etc/stubby/stubby.yml', 'listen_addresses:\n  - 127.0.0.1@5453\n')
        self.write(self.config, 'no-resolv\nserver=127.0.0.1#5453\n')
        self.assertEqual(self.collect(), UNKNOWN)

    def test_ipv6_expanded_and_mapped_local_upstreams_are_not_assumed_external(self):
        for address in ['0:0:0:0:0:0:0:1', '::ffff:127.0.0.1']:
            with self.subTest(address=address):
                self.write(self.config, f'no-resolv\nserver={address}#5353\n')
                self.assertEqual(self.collect(), UNKNOWN)

    def test_ipv6_system_listener_without_an_owner_proof_is_unknown(self):
        self.write('/etc/resolv.conf', 'nameserver ::1\n')
        self.assertEqual(self.collect(), UNKNOWN)

    def test_resolver_link_retarget_during_read_cannot_form_a_known_mixed_snapshot(self):
        self.write('/tmp/resolv.conf', 'nameserver 127.0.0.1\n')
        self.path('/etc/resolv.conf').unlink()
        self.path('/etc/resolv.conf').symlink_to(self.path('/tmp/resolv.conf'))
        self.known(self.collect())
        self.path('/tmp/resolv.conf').unlink()
        self.path('/tmp/resolv.conf').symlink_to('/proc/self/environ')
        self.assertEqual(self.collect(), UNKNOWN)

    def test_inactive_resume_intent_and_disabled_resolver_file_are_not_effective_inputs(self):
        self.write('/opt/etc/nfqws-asus-web/smartdns/resume-intent.json', '{"private":"PRIVATE_CANARY intent"}')
        self.path('/opt/etc/nfqws-asus-web/smartdns').chmod(0o700)
        self.write(self.config, 'no-resolv\nresolv-file=/tmp/disabled-resolver\nserver=9.9.9.9\n')
        first = self.known(self.collect())
        self.write('/tmp/disabled-resolver', 'nameserver 1.1.1.1\n')
        self.write('/opt/etc/nfqws-asus-web/smartdns/resume-intent.json', '{"other":"PRIVATE_CANARY intent2"}')
        self.assertEqual(first, self.known(self.collect()))

    def test_executable_include_hard_links_partial_processes_and_deep_includes_are_unknown(self):
        self.write(self.config, 'conf-script=/tmp/would-be-program\n')
        self.write('/tmp/would-be-program', '#!/bin/sh\ntouch /tmp/PRIVATE_CANARY_SHOULD_NOT_EXIST\n', 0o700)
        self.assertEqual(self.collect(), UNKNOWN)
        self.write(self.config, 'resolv-file=/tmp/resolv.dnsmasq\n')
        os.link(self.path('/tmp/resolv.dnsmasq'), self.path('/tmp/extra-link'))
        self.assertEqual(self.collect(), UNKNOWN)
        self.path('/tmp/extra-link').unlink()
        self.processes['state'] = 'partial'
        self.assertEqual(self.collect(), UNKNOWN)
        self.processes['state'] = 'available'
        self.write(self.config, 'conf-file=/jffs/include0.conf\n')
        for i in range(10):
            self.write(f'/jffs/include{i}.conf', f'conf-file=/jffs/include{i + 1}.conf\n')
        self.assertEqual(self.collect(), UNKNOWN)

    def test_optional_dns_schema_accepts_legacy_and_rejects_raw_or_incoherent_new_fields(self):
        code = r'''require $argv[1].'/support-json-schema.php';
        $root=$argv[2];$out=[];foreach(['dpi-report.schema.json','dpi-analysis-v2.schema.json']as $name){
          $schema=json_decode(file_get_contents($root.'/'.$name),true);$context=$schema['properties']['context'];
          foreach(json_decode($argv[3])as $v){try{AsusSupportSchema::projection($v,$context,$schema);$out[]=true;}catch(Throwable $e){$out[]=false;}}
        }echo json_encode($out);'''
        base = {'nfqws': 'running', 'ark': 'absent', 'tun_observed': False}
        values = []
        for dns in [None, UNKNOWN, {'schema_version': 1, 'state': 'known', 'sha256': 'a' * 64},
                    {'schema_version': 1, 'state': 'known', 'sha256': None},
                    {'schema_version': 1, 'state': 'unknown', 'sha256': 'a' * 64},
                    {'schema_version': 1, 'state': 'known', 'sha256': 'a' * 64, 'url': 'PRIVATE_CANARY'}]:
            row = dict(base)
            if dns is not None:
                row['dns'] = dns
            values.append({'before': row, 'after': row, 'changed': False})
        p = subprocess.run([PHP, '-n', '-r', code, str(PUBLIC), str(ROOT / 'support'), json.dumps(values)], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stderr, '')
        self.assertEqual(json.loads(p.stdout), [True, True, True, False, False, False] * 2)


if __name__ == '__main__':
    unittest.main()

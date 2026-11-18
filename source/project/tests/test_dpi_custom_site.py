"""Owner445: custom public targets in the existing bounded panel diagnostics."""
import json
import unittest
import test_dpi_site_check as fixture

class DpiCustomSiteTests(unittest.TestCase):
    def setUp(self):
        self.fixed = fixture.DpiSiteCheckTests()
        self.fixed.setUp()
        self.addCleanup(self.fixed.doCleanups)

    def test_custom_domain_request_reaches_existing_verified_https_probe(self):
        target = 'custom-https:www.facebook.com'
        post = {'cmd': 'dpisitecheck', 'csrf_token': 'token', 'target': target}
        self.assertEqual(self.fixed.validate(post), {'valid': True})
        with self.fixed.server(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nOK') as (port, seen):
            self.fixed.worker(port)
            value = self.fixed.check(target)
        self.assertEqual(value.get('schema_version'), 2, value)
        self.assertEqual(value['target'], target)
        self.assertEqual(value['host'], 'www.facebook.com')
        self.assertEqual(value['addresses'], ['93.184.216.34'])
        self.assertEqual(value['response']['http_status'], 200)
        self.assertEqual(value['operation'], 'https')
        self.assertIsNone(value['network'])
        self.assertIs(value['full_service_verified'], False)
        self.assertEqual(len(seen), 1)

    def test_custom_ipv4_route_uses_only_actual_pinned_destination(self):
        target = 'custom-route:1.1.1.1'
        self.fixed.worker()
        value = self.fixed.php('''require $argv[1].'/dpi-site-check.php';
          $calls=[];$deps=['config_path'=>$argv[2].'/nfqws2.conf','proc_root'=>$argv[2].'/proc',
            'worker_argv'=>fn($target,$scope)=>[$argv[3],'-n','-f',$argv[2].'/worker.php','--',$target,$scope],
            'network_run'=>static function($argv,$seconds,$limit)use(&$calls){$calls[]=$argv;return ['status'=>0,'output'=>['ROUTE_OUTPUT_DOUBLE']];}];
          try{$s=new AsusDpiStore($argv[2].'/state',getmyuid());$g=new AsusDpiTerminalLifecycle($argv[2].'/terminal',getmyuid());
            $v=(new AsusDpiSiteCheck($s,$g,$deps))->check($argv[4]);echo json_encode(['report'=>$v,'calls'=>$calls]);
          }catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}''', fixture.PHP, target)
        report = value.get('report', {})
        self.assertEqual(report.get('schema_version'), 2, value)
        self.assertEqual(report['kind'], 'ipv4')
        self.assertEqual(report['addresses'], ['1.1.1.1'])
        self.assertEqual(report['operation'], 'route')
        self.assertEqual(set(report['network']), {'ping', 'route', 'trace'})
        self.assertEqual(len(value['calls']), 3)
        self.assertTrue(all(argv[-1] == '1.1.1.1' for argv in value['calls']))
        self.assertTrue(all('custom-route' not in ' '.join(argv) for argv in value['calls']))
        self.assertEqual(self.fixed.validate({'cmd':'dpisitecheck','csrf_token':'token','target':'custom-route:127.0.0.1'}), {'error':'invalid_request'})

    def test_custom_dns_keeps_actual_rcode_and_nonpublic_stub_without_connecting(self):
        # Actual loopback UDP DNS replies; no external resolver or TLS connection.
        cases = [(3, [], 'rcode'), (0, ['127.0.0.1'], 'ready'),
                 (0, ['93.184.216.34', '0.0.0.0'], 'ready')]
        for rcode, answers, reason in cases:
            with self.subTest(rcode=rcode, answers=answers):
                sock = fixture.socket.socket(fixture.socket.AF_INET, fixture.socket.SOCK_DGRAM)
                sock.bind(('127.0.0.1', 0)); sock.settimeout(3)
                def serve():
                    query, peer = sock.recvfrom(4096)
                    records = b''.join(b'\xc0\x0c' + __import__('struct').pack('!HHIH', 1, 1, 60, 4) + fixture.socket.inet_aton(ip) for ip in answers)
                    header = query[:2] + __import__('struct').pack('!HHHHH', 0x8180 | rcode, 1, len(answers), 0, 0)
                    sock.sendto(header + query[12:] + records, peer)
                thread = fixture.threading.Thread(target=serve, daemon=True); thread.start()
                (self.fixed.base / 'worker.php').write_text('<?php require ' + json.dumps(str(fixture.PUBLIC / 'dpi-site-check.php')) + '; $deps=["dns_port"=>' + str(sock.getsockname()[1]) + ',"open"=>static function(){throw new RuntimeException("UNEXPECTED_CONNECT");}]; echo json_encode((new AsusDpiSiteCheckProbe($deps))->run($argv[1],$argv[2]));')
                try:
                    value = self.fixed.check('custom-https:www.facebook.com', scope='local_resolver')
                finally:
                    thread.join(timeout=3); sock.close()
                self.assertEqual(value.get('dns'), {'rcode': rcode, 'answers': answers, 'reason': reason}, value)
                self.assertEqual(value['addresses'], [])
                self.assertEqual(value['response']['error_code'], 'dns_failed' if rcode else 'non_public_address')

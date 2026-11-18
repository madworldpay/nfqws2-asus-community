"""Pinned custom HTTPS is verified against real local TLS, never real target DNS."""
import contextlib
import json
from pathlib import Path
import unittest
import test_dpi_site_check as fixed_fixture


class PinnedHttpsTests(unittest.TestCase):
    def setUp(self):
        self.fixed=fixed_fixture.DpiSiteCheckTests('test_exact_fields_and_fixed_targets_reject_url_or_execution_input')
        self.fixed.setUp();self.addCleanup(self.fixed.doCleanups)

    def pinned(self, port, mode='tls12', host='www.facebook.com', addresses=None, seconds=8):
        values=json.dumps(addresses if addresses is not None else ['93.184.216.34'])
        return self.fixed.php('''require $argv[1].'/dpi-site-check.php';
          $deps=['ca'=>$argv[2].'/cert.pem','resolve'=>static function(){throw new RuntimeException('unexpected_dns');},
            'open'=>static function($endpoint,$context,$remaining)use($argv){
              $stream=stream_socket_client('tls://127.0.0.1:'.$argv[3],$errno,$error,$remaining,STREAM_CLIENT_CONNECT,$context);
              if(is_resource($stream))file_put_contents($argv[2].'/transport.json',json_encode(['endpoint'=>$endpoint,'options'=>stream_context_get_options($context),'crypto'=>stream_get_meta_data($stream)['crypto']??null]));
              return $stream;
            }];
          echo json_encode((new AsusDpiSiteCheckProbe($deps))->pinned($argv[4],json_decode($argv[5],true),$argv[6],(float)$argv[7]));''',
          port,host,values,mode,seconds)

    def test_explicit_versions_really_negotiate_the_requested_tls(self):
        for mode,want in [('tls12','TLSv1.2'),('tls13','TLSv1.3')]:
            with self.subTest(mode=mode),self.fixed.server(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK')as(port,seen):
                result=self.pinned(port,mode)
                self.assertEqual(result['outcome'],'response')
                self.assertEqual(result['http_status'],200)
                transport=json.loads((self.fixed.base/'transport.json').read_text())
                self.assertEqual(transport['crypto']['protocol'],want)
                self.assertEqual(transport['endpoint'],'tls://93.184.216.34:443')
                self.assertEqual(transport['options']['ssl']['peer_name'],'www.facebook.com')
                self.assertEqual(seen,[b'GET / HTTP/1.1\r\nHost: www.facebook.com\r\nUser-Agent: NFQWS2-Control/1\r\nAccept: */*\r\nAccept-Encoding: identity\r\nConnection: close\r\n\r\n'])

    def test_poisoned_answer_does_not_become_a_public_subset(self):
        result=self.fixed.php('''require $argv[1].'/dpi-site-check.php';try{
          $probe=new AsusDpiSiteCheckProbe(['open'=>static function(){throw new RuntimeException('transport_was_reached');}]);
          echo json_encode($probe->pinned('www.facebook.com',['93.184.216.34','127.0.0.1'],'tls12'));
        }catch(RuntimeException $e){echo json_encode(['error'=>$e->getMessage()]);}''')
        self.assertEqual(result,{'error':'custom_non_public_address'})

    def test_invalid_hosts_modes_and_deadlines_are_rejected_before_transport(self):
        result=self.fixed.php('''require $argv[1].'/dpi-site-check.php';$out=[];
          foreach([['https://www.facebook.com','tls12',8],['WWW.FACEBOOK.COM','tls12',8],['www.facebook.com.','tls12',8],
            ['127.0.0.1','tls12',8],['0x7f.0x1','tls12',8],['www.facebook.com','auto',8],['www.facebook.com','tls11',8],
            ['www.facebook.com','tls12',0],['www.facebook.com','tls13',9],['www.facebook.com','tls13',NAN]]as[$host,$mode,$seconds]){
            try{(new AsusDpiSiteCheckProbe(['open'=>static function(){throw new RuntimeException('transport_was_reached');}]))->pinned($host,['93.184.216.34'],$mode,$seconds);$out[]='accepted';}
            catch(RuntimeException $e){$out[]=$e->getMessage();}}
          echo json_encode($out);''')
        self.assertEqual(result,['invalid_request']*10)

    def test_tls_hostname_mismatch_stays_a_tls_error(self):
        with self.fixed.server(b'HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n')as(port,seen):
            result=self.pinned(port,host='discord.com')
            self.assertEqual(result['outcome'],'tls_error')
            self.assertEqual(result['error_code'],'tls_verification_failed')
            self.assertIsNone(result['http_status'])

    def test_http_denial_and_private_redirect_are_only_observations(self):
        for reply,status in [(b'HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n',403),
                             (b'HTTP/1.1 302 Found\r\nLocation: http://127.0.0.1/admin\r\nContent-Length: 0\r\n\r\n',302)]:
            with self.subTest(status=status),self.fixed.server(reply)as(port,seen):
                result=self.pinned(port)
                self.assertEqual(result['outcome'],'response')
                self.assertEqual(result['http_status'],status)
                self.assertEqual(len(seen),1)
                self.assertEqual(set(result),{'outcome','http_status','bytes_read','body_limited','redirect','elapsed_ms','error_code'})
                if status==302:self.assertEqual(result['redirect'],'http://127.0.0.1/admin')

    def test_custom_deadline_stops_a_slow_response(self):
        with self.fixed.server(b'HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n',delay=.3)as(port,seen):
            result=self.pinned(port,seconds=.05)
            self.assertEqual(result['outcome'],'timeout')
            self.assertEqual(result['error_code'],'deadline')

    def test_reusing_the_probe_does_not_accumulate_header_bytes(self):
        reply=b'HTTP/1.1 200 OK\r\n'+b''.join(b'X-'+str(i).encode()+b': '+b'x'*6000+b'\r\n'for i in range(4))+b'Content-Length: 0\r\n\r\n'
        with contextlib.ExitStack()as stack:
            ports=[stack.enter_context(self.fixed.server(reply))[0]for _ in range(2)]
            result=self.fixed.php('''require $argv[1].'/dpi-site-check.php';$ports=json_decode($argv[3],true);$index=0;
              $probe=new AsusDpiSiteCheckProbe(['ca'=>$argv[2].'/cert.pem','open'=>static function($endpoint,$context,$remaining)use($ports,&$index){
                return stream_socket_client('tls://127.0.0.1:'.$ports[$index++],$errno,$error,$remaining,STREAM_CLIENT_CONNECT,$context);
              }]);$out=[];for($i=0;$i<2;$i++)$out[]=$probe->pinned('www.facebook.com',['93.184.216.34'],'tls12');echo json_encode($out);''',json.dumps(ports))
            self.assertEqual([r['outcome']for r in result],['response','response'])
            self.assertEqual([r['http_status']for r in result],[200,200])


if __name__=='__main__':unittest.main()

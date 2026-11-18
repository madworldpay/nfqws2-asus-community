"""Internal v2 targets use literal pins and real, strictly IP-authenticated TLS."""
import contextlib
import json
import socket
import ssl
import subprocess
import threading
import unittest

import test_dpi_site_check as fixed_fixture
import test_picker_custom_worker as worker_fixture
DNS=worker_fixture.DNS

POLICY='custom-public-targets-v2'
FINGERPRINT='php-openssl-pinned-public-targets-v2'
IDNA='uts46-533d68c-nfc-ebd57cc-std3-bidi-contextj-nontransitional-v1'


class Ipv4WorkerTests(unittest.TestCase):
    def setUp(self):
        self.worker=worker_fixture.CustomWorkerTests('test_prepare_pins_the_complete_answer_and_keeps_only_canonical_targets')
        self.worker.setUp()

    def document(self):
        return dict(schema_version=2,hosts=['8.8.8.8','example.com'],dns_context=DNS,
            target_policy_version=POLICY,targets=[dict(kind='ipv4',host='8.8.8.8'),dict(kind='domain',host='example.com')])

    def manifest(self):
        return self.document()|dict(policy=IDNA,fingerprint=FINGERPRINT,pins=[
            dict(host='8.8.8.8',answer=['8.8.8.8'],address='8.8.8.8'),
            dict(host='example.com',answer=['8.8.4.4','8.8.8.8'],address='8.8.4.4')])

    def test_mixed_prepare_resolves_only_domains_and_pins_literal_to_itself(self):
        out=self.worker.observe(self.document(),resolver="if($host!=='example.com')throw new RuntimeException('literal_resolved');return ['8.8.8.8','8.8.4.4'];")
        self.assertNotIn('error',out);self.assertEqual(out['dns_calls'],1)
        self.assertEqual(out['result'],self.manifest())

    def test_literal_only_prepare_never_calls_any_resolver(self):
        v=self.document();v['hosts']=v['hosts'][:1];v['targets']=v['targets'][:1]
        out=self.worker.observe(v,resolver="throw new RuntimeException('resolver_was_reached');")
        self.assertNotIn('error',out);self.assertEqual(out['dns_calls'],0)
        self.assertEqual(out['result']['pins'],self.manifest()['pins'][:1])

    def test_v2_probe_preserves_typed_scope_versions_and_tls_rows_without_dns(self):
        out=self.worker.observe(self.manifest(),stage='probe')
        self.assertNotIn('error',out);self.assertEqual(out['dns_calls'],0)
        v=out['result'];self.assertEqual(v['schema_version'],2)
        for key in ['hosts','targets','target_policy_version','dns_context']:
            self.assertEqual(v[key],self.document()[key])
        self.assertEqual(v['fingerprint'],FINGERPRINT)
        self.assertEqual([(x['host'],x['tls'],x['response']['http_status'])for x in v['observations']],
            [(h,t,403)for h in v['hosts']for t in ['tls12','tls13']])

    def test_v2_typed_identity_and_literal_pin_tampering_refuse_before_network(self):
        cases=[]
        for answer in [['1.1.1.1'],['8.8.8.8','1.1.1.1'],['8.8.8.8','8.8.8.8'],['127.0.0.1']]:
            v=self.manifest();v['pins'][0]['answer']=answer;v['pins'][0]['address']=answer[0];cases.append(v)
        v=self.manifest();v['targets'][0]['kind']='domain';cases.append(v)
        v=self.manifest();v['targets'].reverse();cases.append(v)
        for key,value in [('target_policy_version','custom-public-targets-v1'),('fingerprint','php-openssl-pinned-https-v1'),('schema_version',1)]:
            v=self.manifest();v[key]=value;cases.append(v)
        v=self.manifest();v['targets'][0]['extra']=True;cases.append(v)
        for v in cases:
            with self.subTest(v=v):
                out=self.worker.observe(v,stage='probe');self.assertIn('error',out)
                self.assertEqual(out['dns_calls'],0);self.assertEqual(out['probe_calls'],[])

    def test_v1_cannot_be_widened_to_literal_and_domain_v2_cannot_downgrade(self):
        v=self.worker.prepare();v['hosts']=['8.8.8.8']
        out=self.worker.observe(v);self.assertIn('error',out);self.assertEqual(out['dns_calls'],0)
        v=self.document();v['hosts']=v['hosts'][1:];v['targets']=v['targets'][1:]
        out=self.worker.observe(v);self.assertIn('error',out);self.assertEqual(out['dns_calls'],0)


class Ipv4TlsTests(unittest.TestCase):
    def setUp(self):
        self.fixed=fixed_fixture.DpiSiteCheckTests('test_exact_fields_and_fixed_targets_reject_url_or_execution_input')
        self.fixed.setUp();self.addCleanup(self.fixed.doCleanups)

    def certificate(self,san='IP:8.8.8.8',cn='unrelated.example'):
        args=['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(self.fixed.key),
            '-out',str(self.fixed.cert),'-days','1','-subj','/CN='+cn]
        if san is not None:args+=['-addext','subjectAltName='+san]
        subprocess.run(args,capture_output=True,check=True)

    @contextlib.contextmanager
    def server(self,reply=b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK'):
        listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1);listener.settimeout(3)
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(self.fixed.cert,self.fixed.key)
        seen=[];sni=[];context.sni_callback=lambda sock,name,ctx:sni.append(name)
        def serve():
            try:
                conn,_=listener.accept()
                with conn,context.wrap_socket(conn,server_side=True)as tls:
                    request=b''
                    while b'\r\n\r\n'not in request:
                        part=tls.recv(4096)
                        if not part:return
                        request+=part
                    seen.append(request);tls.sendall(reply)
            except (ssl.SSLError,OSError):pass
        thread=threading.Thread(target=serve,daemon=True);thread.start()
        try:yield listener.getsockname()[1],seen,sni
        finally:listener.close();thread.join(4);self.assertFalse(thread.is_alive())

    def pinned(self,port,mode='tls12',host='8.8.8.8',kind='ipv4',answer=None,ca=None):
        return self.fixed.php('''require $argv[1].'/dpi-site-check.php';
          $deps=['ca'=>$argv[8],'resolve'=>static function(){throw new RuntimeException('unexpected_dns');},
            'open'=>static function($endpoint,$context,$remaining)use($argv){
              file_put_contents($argv[2].'/options.json',json_encode(['endpoint'=>$endpoint,'ssl'=>stream_context_get_options($context)['ssl']]));
              $stream=stream_socket_client('tls://127.0.0.1:'.$argv[3],$errno,$error,$remaining,STREAM_CLIENT_CONNECT,$context);
              if(is_resource($stream))file_put_contents($argv[2].'/crypto.json',json_encode(stream_get_meta_data($stream)['crypto']??null));
              return $stream;
            }];
          try{echo json_encode((new AsusDpiSiteCheckProbe($deps))->pinnedTarget(['kind'=>$argv[5],'host'=>$argv[4]],json_decode($argv[7],true),$argv[6]));}
          catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}''',port,host,kind,mode,
          json.dumps(answer if answer is not None else [host]),str(ca or self.fixed.cert))

    def test_literal_tls12_and_tls13_use_ip_san_no_sni_and_ip_host(self):
        self.certificate()
        for mode,protocol in [('tls12','TLSv1.2'),('tls13','TLSv1.3')]:
            with self.subTest(mode=mode),self.server()as(port,seen,sni):
                result=self.pinned(port,mode);self.assertEqual(result['outcome'],'response')
                self.assertEqual(result['http_status'],200);self.assertEqual(sni,[None])
                self.assertIn(b'\r\nHost: 8.8.8.8\r\n',seen[0])
                options=json.loads((self.fixed.base/'options.json').read_text())
                self.assertEqual(options['endpoint'],'tls://8.8.8.8:443')
                self.assertEqual(options['ssl']['peer_name'],'8.8.8.8');self.assertFalse(options['ssl']['SNI_enabled'])
                self.assertTrue(options['ssl']['verify_peer']);self.assertTrue(options['ssl']['verify_peer_name'])
                self.assertFalse(options['ssl']['allow_self_signed'])
                self.assertEqual(json.loads((self.fixed.base/'crypto.json').read_text())['protocol'],protocol)

    def test_numeric_dns_san_common_name_and_wrong_ip_san_never_authenticate_literal(self):
        for san,cn in [('DNS:8.8.8.8','unrelated.example'),(None,'8.8.8.8'),('IP:1.1.1.1','8.8.8.8'),
                       ('DNS:8.8.8.8,DNS:other.example','8.8.8.8')]:
            self.certificate(san,cn)
            with self.subTest(san=san),self.server()as(port,seen,sni):
                result=self.pinned(port);self.assertEqual(result['outcome'],'tls_error')
                self.assertEqual(result['error_code'],'tls_verification_failed');self.assertIsNone(result['http_status'])
                self.assertEqual(seen,[]);self.assertEqual(sni,[None])

    def test_matching_ip_san_does_not_bypass_certificate_chain(self):
        oldca=self.fixed.base/'old-ca.pem';oldca.write_bytes(self.fixed.cert.read_bytes());self.certificate()
        with self.server()as(port,seen,sni):
            result=self.pinned(port,ca=oldca);self.assertEqual(result['outcome'],'tls_error');self.assertEqual(seen,[])

    def test_san_display_text_cannot_impersonate_an_ip_address_san(self):
        # The real DER contains two dNSName values. Its OpenSSL display text
        # also contains "IP Address:8.8.8.8", which is not a tag [7] identity.
        names=[b'8.8.8.8',b'innocent.example, IP Address:8.8.8.8']
        value=b''.join(b'\x82'+bytes([len(x)])+x for x in names)
        self.certificate('DER:'+(b'\x30'+bytes([len(value)])+value).hex())
        with self.server()as(port,seen,sni):
            result=self.pinned(port);self.assertEqual(result['outcome'],'tls_error');self.assertEqual(seen,[])

    def test_literal_pin_mismatch_alternatives_and_typed_scope_are_refused_before_transport(self):
        for host,kind,answer in [('8.8.8.8','ipv4',['1.1.1.1']),('8.8.8.8','ipv4',['8.8.8.8','1.1.1.1']),
             ('8.8.8.8','ipv4',['8.8.8.8','8.8.8.8']),('8.8.8.8','domain',['8.8.8.8']),
             ('example.com','ipv4',['8.8.8.8']),('127.0.0.1','ipv4',['127.0.0.1']),('008.8.8.8','ipv4',['8.8.8.8'])]:
            with self.subTest(host=host,kind=kind,answer=answer):
                out=self.pinned(1,host=host,kind=kind,answer=answer);self.assertEqual(out,{'error':'invalid_request'})
                self.assertFalse((self.fixed.base/'options.json').exists())

    def test_v2_domain_keeps_sni_and_literal_http_denial_redirect_remain_observations(self):
        with self.server()as(port,seen,sni):
            result=self.pinned(port,host='www.facebook.com',kind='domain',answer=['8.8.8.8'])
            self.assertEqual(result['outcome'],'response');self.assertEqual(sni,['www.facebook.com'])
        self.certificate('IP:1.1.1.1,IP:8.8.8.8,DNS:unrelated.example')
        for reply,status in [(b'HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n',403),
            (b'HTTP/1.1 302 Found\r\nLocation: http://127.0.0.1/\r\nContent-Length: 0\r\n\r\n',302)]:
            with self.subTest(status=status),self.server(reply)as(port,seen,sni):
                result=self.pinned(port);self.assertEqual(result['outcome'],'response');self.assertEqual(result['http_status'],status)
                self.assertEqual(len(seen),1)


if __name__=='__main__':unittest.main()

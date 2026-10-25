"""Exercise native activation and real SmartDNS in an isolated native rootfs."""
import base64,hashlib,http.server,json,os,socket,ssl,struct,subprocess,sys,tempfile,threading,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CONTAINER=os.environ.get('NFQWS_TEST_DOCKER')
CACHE=os.environ.get('NFQWS_TEST_SMARTDNS_CACHE')
@unittest.skipUnless(CONTAINER and CACHE,'Requires isolated OpenWrt and verified native SmartDNS assets')
class NativeSmartDnsRuntime(unittest.TestCase):
    @classmethod
    def sh(cls,code,input=None):
        return subprocess.run(['docker','exec','-i',CONTAINER,'sh','-c',code],input=input,capture_output=True,text=True,check=True,timeout=30)
    @classmethod
    def setUpClass(cls):
        spec=json.loads(subprocess.check_output(['docker','inspect',CONTAINER]))[0]
        if not CONTAINER.startswith('nfqws-openwrt')or spec['HostConfig']['NetworkMode']=='host':raise RuntimeError('Refusing non-test container')
        cls.base='/tmp/nfqws-native-dns-fixture';cls.sh('rm -rf '+cls.base+'; mkdir -p '+cls.base+' /usr/share/nfqws2/optional; chmod 700 '+cls.base)
        for p in (ROOT/'webui/web/public').glob('*.php'):cls.sh('cat > '+cls.base+'/'+p.name,input=p.read_text())
        cls.sh('cat > '+cls.base+'/platform-profile.json',input='{"schema_version":1,"platform":"openwrt"}')
        raw=(Path(CACHE)/'smartdns-native/24.10-x86_64-smartdns').read_bytes();sha=hashlib.sha256(raw).hexdigest()
        cls.artifact={'source':'bundled-native','version':'1.2023.43','version_output':'smartdns 1.2023.43','sha256':sha,
                      'elf_class':2,'elf_data':1,'elf_machine':62,'files':{'smartdns':{'size':len(raw),'sha256':sha}},'links':[]}
        cls.sh('cat > /usr/share/nfqws2/smartdns-native-artifact.json',input=json.dumps({'schema_version':1,'series':'24.10','arch':'x86_64','artifact':cls.artifact}))
        subprocess.run(['docker','exec','-i',CONTAINER,'sh','-c','cat > /usr/share/nfqws2/optional/smartdns'],input=raw,check=True,capture_output=True)
        cls.sh('chmod 600 '+cls.base+'/*.php '+cls.base+'/platform-profile.json /usr/share/nfqws2/smartdns-native-artifact.json; chmod 644 /usr/share/nfqws2/optional/smartdns')
    def php(self,code):
        r=subprocess.run(['docker','exec',CONTAINER,'php-cli','-r','require '+json.dumps(self.base+'/smartdns-install.php')+';'+code],capture_output=True,text=True,timeout=30)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertEqual(r.stderr,'');return json.loads(r.stdout)
    def test_native_install_is_idempotent_and_does_not_modify_resolver_configuration(self):
        before=self.sh('sha256sum /etc/config/dhcp; pidof dnsmasq || true').stdout
        data=self.php('$i=new AsusSmartDnsInstaller("'+self.base+'/engine");$one=$i->install(str_repeat("a",32));$two=$i->install(str_repeat("b",32));echo json_encode([$one,$two,$i->binaryDirectory()]);')
        self.assertEqual(data[0],{'installed':True,'version':'1.2023.43'});self.assertEqual(data[0],data[1])
        self.assertEqual(before,self.sh('sha256sum /etc/config/dhcp; pidof dnsmasq || true').stdout)
        self.assertFalse(self.sh('test -e /opt && echo yes || true').stdout.strip())
    def test_native_backend_prepares_only_private_runtime_and_keeps_dns_inert(self):
        data=self.php('require "'+self.base+'/smartdns-native.php";$b=AsusSmartDnsNativeBackend::create(new AsusSmartDnsStore("'+self.base+'/journal"),new AsusSmartDnsInstaller("'+self.base+'/engine"));echo json_encode(["state"=>$b->state(),"dependencies"=>array_keys($b->dependencies())]);')
        self.assertIsNone(data['state']);self.assertIn('restore',data['dependencies']);self.assertIn('guard',data['dependencies'])

    def test_corrupt_runtime_journal_keeps_checkup_available_and_explicitly_blocks_connect(self):
        path='/tmp/nfqws2-native-state/smartdns-runtime'
        self.sh('mkdir -p '+path+'; chmod 700 '+path+'; cat > '+path+'/state.json; chmod 600 '+path+'/state.json',input='{"broken":true}')
        try:
            data=self.php('require "'+self.base+'/openwrt-web.php";echo json_encode(NfqwsOpenWrtWeb::checkup());')
            self.assertIn('invalid_state',data['readiness']['smartdns_connect']['codes'])
            self.assertFalse(data['readiness']['smartdns_connect']['ready'])
        finally:self.sh('rm -f '+path+'/state.json; rmdir '+path)

    def test_native_runtime_is_private_under_the_shared_native_parent(self):
        path='/tmp/nfqws2-native-state/smartdns-runtime'
        self.sh('mkdir -p /tmp/nfqws2-native-state; chmod 755 /tmp/nfqws2-native-state; test ! -e '+path)
        try:
            data=self.php('require "'+self.base+'/smartdns-native.php";$b=AsusSmartDnsNativeBackend::create(new AsusSmartDnsStore("'+self.base+'/journal"),new AsusSmartDnsInstaller("'+self.base+'/engine"));echo json_encode([$b->launchSpec(),fileperms("'+path+'")&0777]);')
            self.assertEqual(data,[None,0o700])
        finally:self.sh('rm -f '+path+'/state.lock; rmdir '+path+' 2>/dev/null || :; chmod 700 /tmp/nfqws2-native-state')

    def test_native_checkup_exposes_verified_component_availability(self):
        data=self.php('require "'+self.base+'/openwrt-web.php";echo json_encode(NfqwsOpenWrtWeb::checkup());')
        self.assertTrue(data['readiness']['smartdns_install']['ready'],data['readiness'])
        self.assertNotIn('unsupported_runtime',data['readiness']['smartdns_connect']['codes'])

    def test_native_doh_verifies_ca_and_hostname_before_sending_dns(self):
        spec=json.loads(subprocess.check_output(['docker','inspect',CONTAINER]))[0]
        gateway=next(iter(spec['NetworkSettings']['Networks'].values()))['Gateway']
        self.assertTrue(gateway and gateway!='0.0.0.0')
        with tempfile.TemporaryDirectory(prefix='nfqws-native-dns-tls-')as td:
            cert=Path(td)/'cert.pem';key=Path(td)/'key.pem'
            subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=dns-fixture.example',
                            '-addext','subjectAltName=DNS:dns-fixture.example','-keyout',str(key),'-out',str(cert)],check=True,capture_output=True,timeout=10)
            self.sh('cat > '+self.base+'/fixture-ca.pem; chmod 600 '+self.base+'/fixture-ca.pem',input=cert.read_text())
            for case,trusted,name in [('valid',True,'dns-fixture.example'),('untrusted_ca',False,'dns-fixture.example'),('wrong_name',True,'wrong-dns-fixture.example')]:
                requests=[]
                class Doh(http.server.BaseHTTPRequestHandler):
                    protocol_version='HTTP/1.1'
                    def log_message(self,*args):pass
                    def do_GET(self):
                        import urllib.parse
                        value=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get('dns',[''])[0]
                        self.answer(base64.urlsafe_b64decode(value+'='*(-len(value)%4)))
                    def do_POST(self):self.answer(self.rfile.read(int(self.headers.get('Content-Length','0'))))
                    def answer(self,q):
                        if self.headers.get('Host')!='dns-fixture.example':
                            self.send_response(421);self.send_header('Content-Length','0');self.end_headers();return
                        requests.append(q);end=12
                        while q[end]:end+=1+q[end]
                        end+=5;question=q[12:end];typ=struct.unpack('!H',question[-4:-2])[0]
                        answer=socket.inet_pton(socket.AF_INET6,'2001:db8::10')if typ==28 else socket.inet_aton('192.0.2.10')
                        data=q[:2]+struct.pack('!HHHHH',0x8180,1,1,0,0)+question+b'\xc0\x0c'+struct.pack('!HHIH',typ,1,60,len(answer))+answer
                        self.send_response(200);self.send_header('Content-Type','application/dns-message');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
                class TlsServer(http.server.ThreadingHTTPServer):
                    def handle_error(self,request,address):
                        if not isinstance(sys.exc_info()[1],ConnectionError):super().handle_error(request,address)
                server=TlsServer((gateway,0),Doh);server.daemon_threads=True
                context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(cert,key);server.socket=context.wrap_socket(server.socket,server_side=True)
                worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
                try:
                    profile={'schema_version':1,'upstreams':[{'id':'fixture','label':'TLS fixture','protocol':'doh','address':'dns-fixture.example','port':server.server_address[1],
                             'tls_name':name,'url':'https://dns-fixture.example:'+str(server.server_address[1])+'/dns-query','bootstrap':[gateway],'default':True,'domains':[]}],'records':[]}
                    code='require "'+self.base+'/smartdns-candidate.php";$i=new AsusSmartDnsInstaller("'+self.base+'/engine");$i->install(str_repeat("c",32));$p=json_decode('+json.dumps(json.dumps(profile))+',true);$config=AsusSmartDnsProfile::render($p,16053)["config"];'
                    if trusted:code+='$config=str_replace("/etc/ssl/certs/ca-certificates.crt","'+self.base+'/fixture-ca.pem",$config);'
                    code+='$id=bin2hex(random_bytes(16));$c=new AsusSmartDnsCandidate($i,$id,["root"=>"'+self.base+'/candidate","guard"=>fn()=>true]);echo json_encode($c->run(["request_id"=>$id,"profile_hash"=>AsusSmartDnsProfile::hash($p),"stage"=>"upstream","server_id"=>"fixture","bundle"=>$i->binaryDirectory(),"port"=>16053,"config"=>$config,"names"=>["example.com"],"query_timeout_ms"=>2500,"max_parallel_queries"=>2,"deadline_uptime"=>(float)explode(" ",file_get_contents("/proc/uptime"))[0]+15]));'
                    result=self.php(code);answers=[row['udp']['ok']for row in result['results']]
                    if case=='valid':self.assertEqual(answers,[True,True],result);self.assertGreater(len(requests),0)
                    else:self.assertEqual(answers,[False,False],result);self.assertEqual(requests,[],case+' exposed a DNS request before TLS verification')
                    if case=='valid':
                        # Exercise the EDNS query shape used by real dnsmasq,
                        # retaining the same trusted local TLS/HTTP endpoint.
                        code='require_once "'+self.base+'/smartdns-profile.php";$p=json_decode('+json.dumps(json.dumps(profile))+',true);$config=str_replace("/etc/ssl/certs/ca-certificates.crt","'+self.base+'/fixture-ca.pem",AsusSmartDnsProfile::render($p,16054)["config"]);'
                        code+='$file="'+self.base+'/edns.conf";file_put_contents($file,$config);chmod($file,0600);$i=new AsusSmartDnsInstaller("'+self.base+'/engine");$b=$i->binaryDirectory();$proc=proc_open([$b."/smartdns","-f","-c",$file],[0=>["file","/dev/null","r"],1=>["file","/dev/null","w"],2=>["file","/dev/null","w"]],$pipes,$b);$pid=proc_get_status($proc)["pid"];try{$end=microtime(true)+2;while(!AsusSmartDnsCandidate::ownsPorts($pid,16054)){if(microtime(true)>$end)throw new RuntimeException("startup");usleep(10000);}$out=[];foreach([0,1]as $edns){$q=pack("nnnnnn",12345,256,1,0,0,$edns)."\\7example\\3com\\0".pack("nn",1,1);if($edns)$q.="\\0".pack("nnNn",41,1232,0,0);$c=stream_socket_client("udp://127.0.0.1:16054");stream_set_timeout($c,3);fwrite($c,$q);$raw=fread($c,4096);fclose($c);$h=strlen($raw)>=12?unpack("nid/nflags/nqd/nan/nns/nar",substr($raw,0,12)):[];$out[]=["edns"=>$edns,"rcode"=>($h["flags"]??15)&15,"answers"=>$h["an"]??0];}echo json_encode($out);}finally{proc_terminate($proc);proc_close($proc);unlink($file);}'
                        # Candidate class is loaded by the same trusted test
                        # adapter; this standalone process must load it too.
                        code='require "'+self.base+'/smartdns-candidate.php";'+code
                        observed=self.php(code)
                        self.assertEqual(observed,[{'edns':0,'rcode':0,'answers':1},{'edns':1,'rcode':0,'answers':1}],observed)

                finally:server.shutdown();server.server_close();worker.join(2)

    def test_native_render_uses_native_ca_without_changing_profile_data(self):
        p={'schema_version':1,'upstreams':[{'id':'fixture','label':'Fixture','tls_name':'','url':'','protocol':'udp','address':'1.1.1.1','port':53,'bootstrap':[],'default':True,'domains':[]}],'records':[]}
        data=self.php('require "'+self.base+'/smartdns-profile.php";$p=json_decode('+json.dumps(json.dumps(p))+',true);echo json_encode(AsusSmartDnsProfile::render($p,16053));')
        self.assertIn('ca-file /etc/ssl/certs/ca-certificates.crt',data['config']);self.assertNotIn('/opt/',data['config'])

if __name__=='__main__':unittest.main()

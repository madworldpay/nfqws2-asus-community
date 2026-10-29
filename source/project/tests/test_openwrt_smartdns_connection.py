"""Real native SmartDNS, dnsmasq and shell owners in an isolated rootfs.
Only procd/ubus transport is emulated: no procd is booted in this container.
"""
import hashlib,json,os,shlex,subprocess,time,unittest
from pathlib import Path
from test_openwrt_builder import builder
ROOT=Path(__file__).resolve().parents[1];CONTAINER=os.environ.get('NFQWS_TEST_DOCKER');CACHE=os.environ.get('NFQWS_TEST_SMARTDNS_CACHE')
@unittest.skipUnless(CONTAINER and CACHE,'Requires isolated native rootfs and verified engine')
class NativeDnsConnection(unittest.TestCase):
    @classmethod
    def execute(cls,args,input=None,timeout=40,check=True):
        r=subprocess.run(['docker','exec','-i',CONTAINER,*args],input=input,text=True,capture_output=True,timeout=timeout)
        if check and r.returncode:raise AssertionError(r.stdout+r.stderr)
        return r
    @classmethod
    def sh(cls,code,input=None,**kw):return cls.execute(['sh','-c',code],input,**kw)
    @classmethod
    def put(cls,path,text,mode='600'):
        cls.sh('mkdir -p '+shlex.quote(str(Path(path).parent))+'; cat > '+shlex.quote(path)+'; chmod '+mode+' '+shlex.quote(path),text)
    def setUp(self):
        self.setup_fixture(self.addCleanup)

    @classmethod
    def setup_fixture(cls,register_cleanup):
        spec=json.loads(subprocess.check_output(['docker','inspect',CONTAINER]))[0]
        if not CONTAINER.startswith('nfqws-openwrt')or spec['HostConfig']['NetworkMode']=='host':raise RuntimeError('Refusing non-test container')
        cls.private_ip=next(iter(spec['NetworkSettings']['Networks'].values()))['IPAddress']
        cls.base='/tmp/nfqws-native-dns-connection';cls.lib='/usr/lib/nfqws2/smartdns'
        cls.sh('test -z "$(pidof dnsmasq)"; rm -rf '+cls.base+'; mkdir -p '+cls.base+' /var/etc /tmp/dnsmasq.nfqws_main.d /tmp/nfqws2-native-state/updates; chmod 700 '+cls.base+' /tmp/nfqws2-native-state /tmp/nfqws2-native-state/updates; touch /tmp/nfqws2-native-state/updates/apply.lock; chmod 600 /tmp/nfqws2-native-state/updates/apply.lock')
        for path in ['/bin/ubus','/etc/init.d/dnsmasq','/etc/init.d/nfqws2-native-dns']:
            cls.sh('if test -e '+path+'; then cp -p '+path+' '+shlex.quote(cls.base+'/'+Path(path).name+'.original')+'; fi')
        register_cleanup(cls.cleanup)
        for p in (ROOT/'webui/web/public').glob('*.php'):cls.put('/usr/share/nfqws2-web/'+p.name,p.read_text(),'644')
        cls.put('/usr/share/nfqws2-web/platform-profile.json','{"schema_version":1,"platform":"openwrt"}','644')
        files=builder.smartdns_payload(builder.native_metadata('24.10','x86_64'),CACHE,True)
        for name,(data,mode)in files.items():
            if name=='usr/share/nfqws2/optional/smartdns':
                cls.sh('mkdir -p /usr/share/nfqws2/optional')
                subprocess.run(['docker','exec','-i',CONTAINER,'sh','-c','cat > /usr/share/nfqws2/optional/smartdns; chmod 644 /usr/share/nfqws2/optional/smartdns'],input=data,capture_output=True,check=True)
            else:cls.put('/'+name,data.decode(),oct(mode)[2:])
        cls.put(cls.base+'/upstream.conf','port=11553\nlisten-address='+cls.private_ip+'\nbind-interfaces\nno-resolv\nno-hosts\naddress=/#/8.8.8.8\npid-file='+cls.base+'/upstream.pid\nuser=root\n')
        cls.put(cls.base+'/vpn.conf','port=11554\nlisten-address=127.0.0.2\nbind-interfaces\nno-resolv\nno-hosts\naddress=/#/8.8.4.4\npid-file='+cls.base+'/vpn.pid\nuser=root\n')
        cls.put('/tmp/dnsmasq.nfqws_main.d/vpn.conf','server=/vpn.example/127.0.0.2#11554\n')
        cls.put('/var/etc/dnsmasq.conf.nfqws_main','port=53\nlisten-address=127.0.0.1\nstop-dns-rebind\nbind-interfaces\nno-resolv\nno-hosts\nserver='+cls.private_ip+'#11553\nconf-dir=/tmp/dnsmasq.nfqws_main.d\nserver=/invalid/\nserver=/test/\npid-file='+cls.base+'/main.pid\nuser=root\n')
        cls.put('/var/etc/dnsmasq.conf.nfqws_guest','port=53\nlisten-address=127.0.0.3\nbind-interfaces\nno-resolv\nno-hosts\naddress=/#/198.51.100.3\npid-file='+cls.base+'/guest.pid\nuser=root\n')
        cls.sh('cp /var/etc/dnsmasq.conf.nfqws_main '+cls.base+'/main.source')
        cls.put('/bin/ubus','''#!/bin/sh
base=/tmp/nfqws-native-dns-connection
if [ "$1 $2 $3" = 'call service add' ]; then
 printf '%s' "$4" > "$base/commit.json"
 php-cli -r '$v=json_decode(file_get_contents("/tmp/nfqws-native-dns-connection/commit.json"),true);if(($v["name"]??null)!=="dnsmasq"||array_keys($v["instances"]??[])!==["nfqws_main"])exit(1);' || exit 1
 # A real procd does not restart an identical instance configuration.
 signature=$(php-cli -r '$v=file_get_contents("/tmp/nfqws-native-dns-connection/commit.json");echo hash("sha256",$v.file_get_contents("/var/etc/dnsmasq.conf.nfqws_main"));') || exit 1
 if [ "$(cat "$base/last-commit.sha" 2>/dev/null)" = "$signature" ]; then exit 0; fi
 printf '%s' "$signature" > "$base/last-commit.sha"
 pid=$(cat "$base/main.pid") || exit 1
 kill "$pid" || exit 1
 n=0
 while [ -d "/proc/$pid" ] && ! grep -q '^State:.*Z' "/proc/$pid/status"; do
  sleep 1;n=$((n+1));[ "$n" -lt 10 ] || exit 1
 done
 /bin/busybox start-stop-daemon -S -b -m -p "$base/main.pid" -x /usr/sbin/dnsmasq -- -C /var/etc/dnsmasq.conf.nfqws_main -k -x "$base/main.pid" 9>&- || exit 1
 n=0
 while ! php-cli -r '$p="/tmp/nfqws-native-dns-connection/main.pid";exit(is_file($p)&&file_exists("/proc/".trim(file_get_contents($p))."/stat")?0:1);'; do
  sleep 1;n=$((n+1));[ "$n" -lt 10 ] || exit 1
 done
 exit 0
fi
[ "$1 $2 $3" = 'call service list' ] || exit 1
if [ -f "$base/refresh-after-preview" ]; then
 phase=$(php-cli -r '$s=json_decode((string)@file_get_contents("/etc/nfqws2-web/smartdns/state.json"),true);echo $s["job"]["state"]??"";')
 if [ "$phase" = preview_ready ]; then
  rm "$base/refresh-after-preview"
  printf '# firmware DNS refresh before apply\\n' >> "$base/main.source"
  cp "$base/main.source" /var/etc/dnsmasq.conf.nfqws_main
 fi
fi
exec php-cli -r '$b="/tmp/nfqws-native-dns-connection";$v=[];foreach(["main","guest"]as $n){$v["nfqws_".$n]=["running"=>true,"pid"=>(int)file_get_contents($b."/".$n.".pid"),"command"=>["/usr/sbin/dnsmasq","-C","/var/etc/dnsmasq.conf.nfqws_".$n,"-k","-x",$b."/".$n.".pid"]];}echo json_encode(["dnsmasq"=>["instances"=>$v]]);'
''','755')
        # Real rc.common/procd serialization; only the final daemon RPC is
        # emulated. These fields intentionally are absent from service.list.
        cls.put('/etc/init.d/dnsmasq','''#!/bin/sh /etc/rc.common
USE_PROCD=1
start_service() {
 [ "$1" = nfqws_main ] || return 1
 if [ -f /tmp/nfqws-native-dns-connection/refresh-once ]; then
  rm /tmp/nfqws-native-dns-connection/refresh-once
  printf '# firmware DNS refresh\\n' >> /tmp/nfqws-native-dns-connection/main.source
 fi
 cp /tmp/nfqws-native-dns-connection/main.source /var/etc/dnsmasq.conf.nfqws_main || return 1
 procd_open_instance "$1"
 procd_set_param command /usr/sbin/dnsmasq -C /var/etc/dnsmasq.conf.nfqws_main -k -x /tmp/nfqws-native-dns-connection/main.pid
 procd_set_param respawn 3600 5 5
 procd_set_param file /var/etc/dnsmasq.conf.nfqws_main /etc/config/dhcp
 procd_set_param env KEEP_OPERATOR_VALUE=keep
 if [ -e /tmp/nfqws-native-dns-connection/reserved-env ]; then
  procd_append_param env NFQWS2_DNS_GENERATION=operator
 fi
 procd_add_jail dnsmasq ubus log requirejail
 procd_add_jail_mount /var/etc/dnsmasq.conf.nfqws_main
 _procd_call _nfqws_fixture_policy
 procd_close_instance
}
_nfqws_fixture_policy() {
 json_add_object opaque_future_policy
 json_add_object empty
 json_close_object
 json_add_int exact_integer 9007199254740993
 json_close_object
}
''','755')
        # Consume the real init's command and stop preflight, replacing only
        # its procd transport with a detached shell in the isolated rootfs.
        cls.put('/etc/init.d/nfqws2-native-dns','''#!/bin/sh
action=$1
. /usr/lib/nfqws2/smartdns/nfqws2-native-dns
procd_open_instance() { :; }
procd_close_instance() { :; }
procd_set_param() {
 [ "$1" = command ] || return 0
 shift
 /bin/busybox start-stop-daemon -S -b -m -p /tmp/nfqws-native-dns-connection/owner.pid -x "$1" -- "$2"
}
case "$action" in start) start_service;; stop)
 [ ! -e /tmp/nfqws-native-dns-connection/refuse-stop ] || exit 1
 pid=$(cat /tmp/nfqws-native-dns-connection/owner.pid 2>/dev/null) || exit 0
 # Native service.delete acknowledges before the supervised process exits.
 (sleep 1; kill "$pid" 2>/dev/null || :) </dev/null >/dev/null 2>&1 &
 rm -f /tmp/nfqws-native-dns-connection/owner.pid;; *) exit 1;; esac
''','755')
        cls.sh('for name in upstream vpn; do /usr/sbin/dnsmasq -C '+cls.base+'/$name.conf || exit; done; for name in main guest; do /bin/busybox start-stop-daemon -S -b -m -p '+cls.base+'/$name.pid -x /usr/sbin/dnsmasq -- -C /var/etc/dnsmasq.conf.nfqws_$name -k -x '+cls.base+'/$name.pid || exit; done')
        cls.php('require "/usr/share/nfqws2-web/smartdns-install.php";echo json_encode((new AsusSmartDnsInstaller())->install(str_repeat("e",32)));')
    @classmethod
    def php(cls,code):
        r=cls.execute(['php-cli','-r',code]);return json.loads(r.stdout)if r.stdout else None
    @classmethod
    def api(cls,cmd,**fields):
        p=json.dumps({'cmd':cmd,'csrf_token':'native-test'}|fields)
        code='require "/usr/share/nfqws2-web/smartdns-config-api.php";try{echo json_encode(AsusSmartDnsConfigApi::dispatch(json_decode('+json.dumps(p)+',true)));}catch(Throwable $e){echo json_encode(["error"=>$e->getMessage()]);}'
        return cls.php(code)
    def poll(self,expected,limit=20):
        end=time.monotonic()+limit;last=None
        while time.monotonic()<end:
            last=self.api('smartdnsconfigstatus')
            if last.get('status',{}).get('state')in expected:return last['status']
            time.sleep(.15)
        self.fail(str(last))
    def begin(self,id):
        profile={'schema_version':1,'upstreams':[{'id':'fixture','label':'Fixture','protocol':'udp','address':self.private_ip,'port':11553,'bootstrap':[],'tls_name':'','url':'','default':True,'domains':[]}],'records':[{'name':'native.example','include_subdomains':False,'addresses':['1.1.1.1'],'checked_at':None}]}
        saved=self.api('smartdnsdraft',profile=json.dumps(profile));self.assertIn('profile_hash',saved,saved)
        validation=self.api('smartdnsvalidate',request_id=id*32,profile_hash=saved['profile_hash']);self.assertNotIn('error',validation,validation)
        status=self.poll(['preview_ready','failed']);self.assertEqual(status['state'],'preview_ready',status)
        preview=self.api('smartdnspreview',preview_id=status['preview_id'])
        applied=self.api('smartdnsapply',request_id=(hex(int(id,16)+1)[2:])*32,preview_id=status['preview_id'],profile_hash=saved['profile_hash'],baseline_hash=preview['baseline_hash'])
        self.assertEqual(applied.get('state'),'awaiting_confirmation',applied);return applied
    def query(self,name):
        return self.php('require "/usr/share/nfqws2-web/openwrt-dns-probe.php";echo json_encode(NfqwsOpenWrtDnsProbe::query("127.0.0.1",53,'+json.dumps(name)+'));')
    def test_apply_confirm_rollback_preserves_other_instance_and_vpn_routes(self):
        guest=self.sh('cat '+self.base+'/guest.pid').stdout
        before=self.sh('cat /tmp/dnsmasq.nfqws_main.d/vpn.conf').stdout
        applied=self.begin('1');id=applied['request_id']
        self.assertEqual(self.query('native.example')['answers'],['1.1.1.1'])
        frame=json.loads(self.sh('cat '+self.base+'/commit.json').stdout)
        self.assertEqual(frame['instances']['nfqws_main']['env']['KEEP_OPERATOR_VALUE'],'keep')
        self.assertIn('/etc/config/dhcp',frame['instances']['nfqws_main']['file'])
        self.assertTrue(frame['instances']['nfqws_main']['jail']['requirejail'])
        self.assertIn('/var/etc/dnsmasq.conf.nfqws_main',frame['instances']['nfqws_main']['jail']['mount'])
        self.assertEqual(frame['instances']['nfqws_main']['opaque_future_policy'],{'empty':{},'exact_integer':9007199254740993})
        self.assertRegex(frame['instances']['nfqws_main']['env']['NFQWS2_DNS_GENERATION'],r'^[a-f0-9]{32}:forward:[a-f0-9]{16}$')
        self.assertEqual(self.query('vpn.example')['answers'],['8.8.4.4'])
        confirmed=self.api('smartdnsconfirm',request_id=id);self.assertEqual(confirmed.get('state'),'confirmed',confirmed)
        # Unknown concurrent edits to our file are retained, with a live engine.
        owned=self.sh('cat /var/etc/dnsmasq.conf.nfqws_main').stdout
        self.sh('printf "# operator edit\\n" >> /var/etc/dnsmasq.conf.nfqws_main')
        conflict=self.api('smartdnsrollback',request_id=id);self.assertEqual(conflict.get('state'),'conflict',conflict)
        self.assertIn('# operator edit',self.sh('cat /var/etc/dnsmasq.conf.nfqws_main').stdout)
        self.assertEqual(self.query('native.example')['answers'],['1.1.1.1'])
        self.put('/var/etc/dnsmasq.conf.nfqws_main',owned)
        self.put('/tmp/dnsmasq.nfqws_main.d/another.conf','address=/operator.example/9.9.9.9\n')
        restored=self.api('smartdnsrollback',request_id=id);self.assertEqual(restored.get('state'),'rolled_back',restored)
        self.assertEqual(self.query('operator.example')['answers'],['9.9.9.9'])
        self.assertEqual(self.query('native.example')['answers'],['8.8.8.8'])
        self.assertEqual(self.sh('cat /tmp/dnsmasq.nfqws_main.d/vpn.conf').stdout,before)
        self.assertEqual(self.sh('cat '+self.base+'/guest.pid').stdout,guest)
        self.assertEqual(self.sh('test -e /opt && echo yes || true').stdout,'')
    def test_unreachable_candidate_never_switches_the_working_native_resolver(self):
        profile={'schema_version':1,'upstreams':[{'id':'fixture','label':'Fixture','protocol':'udp','address':'127.0.0.2','port':11554,'bootstrap':[],'tls_name':'','url':'','default':True,'domains':[]}],'records':[]}
        saved=self.api('smartdnsdraft',profile=json.dumps(profile));self.assertIn('profile_hash',saved,saved)
        self.api('smartdnsvalidate',request_id='7'*32,profile_hash=saved['profile_hash'])
        status=self.poll(['preview_ready','failed']);self.assertEqual(status['state'],'preview_ready',status)
        preview=self.api('smartdnspreview',preview_id=status['preview_id'])
        main=self.sh('cat '+self.base+'/main.pid').stdout
        self.sh('kill "$(cat '+self.base+'/vpn.pid)"')
        applied=self.api('smartdnsapply',request_id='8'*32,preview_id=status['preview_id'],profile_hash=saved['profile_hash'],baseline_hash=preview['baseline_hash'])
        self.assertIn(applied.get('state'),['failed','rolled_back'],applied)
        self.assertEqual(applied.get('code'),'dns_validation_failed',applied)
        self.assertEqual(self.sh('cat '+self.base+'/main.pid').stdout,main,'Do not switch clients to an engine whose upstream is not ready')
        self.assertEqual(self.query('example.com')['answers'],['8.8.8.8'])

    def test_unverified_candidate_cleanup_retains_a_conflict(self):
        profile={'schema_version':1,'upstreams':[{'id':'fixture','label':'Fixture','protocol':'udp','address':'127.0.0.2','port':11554,'bootstrap':[],'tls_name':'','url':'','default':True,'domains':[]}],'records':[]}
        saved=self.api('smartdnsdraft',profile=json.dumps(profile));self.assertIn('profile_hash',saved,saved)
        self.api('smartdnsvalidate',request_id='d'*32,profile_hash=saved['profile_hash'])
        status=self.poll(['preview_ready','failed']);self.assertEqual(status['state'],'preview_ready',status)
        preview=self.api('smartdnspreview',preview_id=status['preview_id'])
        self.put(self.base+'/refuse-stop','1')
        main=self.sh('cat '+self.base+'/main.pid').stdout
        self.sh('kill "$(cat '+self.base+'/vpn.pid)"')
        applied=self.api('smartdnsapply',request_id='e'*32,preview_id=status['preview_id'],profile_hash=saved['profile_hash'],baseline_hash=preview['baseline_hash'])
        self.assertEqual(applied.get('state'),'conflict',applied)
        self.assertEqual(self.sh('cat '+self.base+'/main.pid').stdout,main,'Do not switch clients to an engine whose upstream is not ready')
        self.assertEqual(self.query('example.com')['answers'],['8.8.8.8'])

    def test_confirmation_waits_for_a_short_native_health_check_lease(self):
        applied=self.begin('d')
        self.sh('/bin/busybox start-stop-daemon -S -b -x /usr/bin/flock -- -x /tmp/nfqws2-native-state/smartdns-runtime/state.lock /bin/sh -c "touch '+self.base+'/lease-held; sleep 1"')
        end=time.monotonic()+3
        while time.monotonic()<end:
            if self.sh('test -f '+self.base+'/lease-held',check=False).returncode==0:break
            time.sleep(.02)
        else:self.fail('Lease fixture did not start')
        confirmed=self.api('smartdnsconfirm',request_id=applied['request_id'])
        self.assertEqual(confirmed.get('state'),'confirmed',confirmed)
        self.assertEqual(self.api('smartdnsrollback',request_id=applied['request_id'])['state'],'rolled_back')

    def test_unconfirmed_deadline_restores_native_dns_and_stops_only_owned_engine(self):
        applied=self.begin('3')
        self.php('$p="/tmp/nfqws2-native-state/smartdns-runtime/state.json";$s=json_decode(file_get_contents($p),true);$s["deadline"]=(string)((float)explode(" ",file_get_contents("/proc/uptime"))[0]-1);file_put_contents($p,json_encode($s));')
        status=self.poll(['rolled_back','conflict']);self.assertEqual(status['state'],'rolled_back',status);self.assertEqual(status['code'],'timed_out')
        self.assertEqual(self.query('native.example')['answers'],['8.8.8.8'])
        self.poll_engine_gone()
    def test_boot_resume_revalidates_after_a_native_dns_refresh(self):
        applied=self.begin('9');confirmed=self.api('smartdnsconfirm',request_id=applied['request_id']);self.assertEqual(confirmed['state'],'confirmed')
        self.php('require "/usr/share/nfqws2-web/smartdns-lifecycle.php";echo json_encode((new AsusSmartDnsLifecycle(new AsusSmartDnsStore()))->stop("upgrade"));')
        self.put(self.base+'/refresh-once','1')
        # Execute the actual boot command; only procd's final launch transport
        # is replaced because this isolated rootfs has no running procd.
        result=self.sh('. /usr/lib/nfqws2/smartdns/nfqws2-native-dns-resume; procd_open_instance() { :; }; procd_close_instance() { :; }; procd_set_param() { if [ "$1" = command ]; then shift; "$@"; fi; }; start_service',timeout=100)
        status=self.api('smartdnsconfigstatus')
        self.assertEqual(status['status']['state'],'confirmed',result.stdout+str(status))
        self.assertEqual(status['routing'],'managed',status)
        self.assertNotEqual(status['status']['request_id'],applied['request_id'])
        self.assertEqual(self.api('smartdnsrollback',request_id=status['status']['request_id'])['state'],'rolled_back')

    def test_boot_resume_revalidates_a_refresh_before_apply_begins(self):
        applied=self.begin('b');confirmed=self.api('smartdnsconfirm',request_id=applied['request_id']);self.assertEqual(confirmed['state'],'confirmed')
        self.php('require "/usr/share/nfqws2-web/smartdns-lifecycle.php";echo json_encode((new AsusSmartDnsLifecycle(new AsusSmartDnsStore()))->stop("upgrade"));')
        self.put(self.base+'/refresh-after-preview','1')
        result=self.sh('. /usr/lib/nfqws2/smartdns/nfqws2-native-dns-resume; procd_open_instance() { :; }; procd_close_instance() { :; }; procd_set_param() { if [ "$1" = command ]; then shift; "$@"; fi; }; start_service',timeout=100)
        status=self.api('smartdnsconfigstatus')
        self.assertEqual(status['status']['state'],'confirmed',result.stdout+str(status))
        self.assertEqual(status['routing'],'managed',status)
        self.assertEqual(self.api('smartdnsrollback',request_id=status['status']['request_id'])['state'],'rolled_back')

    def test_recovery_completes_when_ordinary_dns_was_already_regenerated(self):
        applied=self.begin('1');confirmed=self.api('smartdnsconfirm',request_id=applied['request_id']);self.assertEqual(confirmed['state'],'confirmed')
        owner=self.sh('cat '+self.base+'/owner.pid').stdout.strip();self.sh('kill -KILL '+owner)
        # Simulate loss of a recovery worker after native dnsmasq accepted the
        # ordinary config but before the recovery journal was finalized.
        self.sh('cp '+self.base+'/main.source /var/etc/dnsmasq.conf.nfqws_main; /bin/ubus call service add "$(cat '+self.base+'/commit.json)"')
        self.php('require "/usr/share/nfqws2-web/smartdns-native.php";$b=AsusSmartDnsNativeBackend::create(new AsusSmartDnsStore(),new AsusSmartDnsInstaller());$p="/tmp/nfqws2-native-state/smartdns-runtime/state.json";$s=json_decode(file_get_contents($p),true);$s["phase"]="rolling_back";$s["resolver"]=$b->baseline()["snapshot"];file_put_contents($p,json_encode($s));')
        self.sh('/etc/init.d/nfqws2-native-dns start')
        status=self.poll(['rolled_back','conflict'],35);self.assertEqual(status['state'],'rolled_back',status)
        self.assertEqual(self.query('example.com')['answers'],['8.8.8.8']);self.poll_engine_gone()
        self.api('smartdnsrollback',request_id=applied['request_id'])

    def test_reserved_operator_environment_refuses_switch_without_overwrite(self):
        self.put(self.base+'/reserved-env','1')
        main=self.sh('cat '+self.base+'/main.pid').stdout
        profile={'schema_version':1,'upstreams':[{'id':'fixture','label':'Fixture','protocol':'udp','address':self.private_ip,'port':11553,'bootstrap':[],'tls_name':'','url':'','default':True,'domains':[]}],'records':[]}
        saved=self.api('smartdnsdraft',profile=json.dumps(profile));self.assertIn('profile_hash',saved,saved)
        self.api('smartdnsvalidate',request_id='1'*32,profile_hash=saved['profile_hash'])
        status=self.poll(['preview_ready','failed']);self.assertEqual(status['state'],'preview_ready',status)
        preview=self.api('smartdnspreview',preview_id=status['preview_id'])
        applied=self.api('smartdnsapply',request_id='2'*32,preview_id=status['preview_id'],profile_hash=saved['profile_hash'],baseline_hash=preview['baseline_hash'])
        self.assertIn(applied.get('state'),['conflict','failed','rolled_back'],applied)
        self.assertEqual(self.sh('cat '+self.base+'/main.pid').stdout,main)
        self.assertEqual(self.query('example.com')['answers'],['8.8.8.8'])
        self.assertNotEqual(self.sh('test -f '+self.base+'/commit.json',check=False).returncode,0,'Do not send any altered operator frame')

    def test_owner_loss_restores_before_ending_the_orphan_engine(self):
        applied=self.begin('5');confirmed=self.api('smartdnsconfirm',request_id=applied['request_id']);self.assertEqual(confirmed['state'],'confirmed')
        owner=self.sh('cat '+self.base+'/owner.pid').stdout.strip();self.sh('kill -KILL '+owner)
        self.assertEqual(self.query('native.example')['answers'],['1.1.1.1'])
        self.sh('/etc/init.d/nfqws2-native-dns start')
        status=self.poll(['rolled_back','conflict']);self.assertEqual(status['state'],'rolled_back',status)
        self.assertEqual(self.query('native.example')['answers'],['8.8.8.8']);self.poll_engine_gone()
        self.api('smartdnsrollback',request_id=applied['request_id'])
    def poll_engine_gone(self):
        end=time.monotonic()+6
        while time.monotonic()<end:
            data=self.php('require "/usr/share/nfqws2-web/dpi-runtime.php";$s=json_decode(file_get_contents("/tmp/nfqws2-native-state/smartdns-runtime/state.json"),true);echo json_encode(AsusDpiRuntime::identity((int)$s["runtime_pid"]));')
            if data is None:return
            time.sleep(.1)
        self.fail('Owned native DNS engine was not stopped after rollback')
    @classmethod
    def cleanup(cls):
        # Confined fixture only. Restore every replaced command.
        cls.sh('if test -e /var/etc/dnsmasq.conf.nfqws_main; then rm /var/etc/dnsmasq.conf.nfqws_main; fi; for file in '+cls.base+'/*.pid /tmp/nfqws2-native-state/smartdns-runtime/runtime.pid; do test -f "$file" && kill -KILL "$(cat "$file")" 2>/dev/null || :; done',check=False)
        for path in ['/bin/ubus','/etc/init.d/dnsmasq','/etc/init.d/nfqws2-native-dns']:
            backup=cls.base+'/'+Path(path).name+'.original';cls.sh('if test -f '+shlex.quote(backup)+'; then cp -p '+shlex.quote(backup)+' '+path+'; else rm -f '+path+'; fi',check=False)
        cls.sh('rm -rf /tmp/dnsmasq.nfqws_main.d /var/etc/dnsmasq.conf.nfqws_main /var/etc/dnsmasq.conf.nfqws_guest /tmp/nfqws2-native-state/smartdns-runtime /etc/nfqws2-web/smartdns',check=False)

if __name__=='__main__':unittest.main()

"""Exercise the observer in the pinned engine, retaining its C packet/checksum APIs.

NFQWS_IP_HEALTH_TEST_ENGINE can select an unpacked 1.0.7 native binary.  The
workspace's cached x86_64 IPK is otherwise extracted into a temporary directory.
Only the external send, timer and wall-clock boundaries are replaced by Lua.
"""
import io
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parents[1]
WORKSPACE = PROJECT.parents[1]


class IpHealthLuaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cache = tempfile.TemporaryDirectory(prefix="ip-health-engine-")
        cls.addClassCleanup(cls.cache.cleanup)
        root = Path(cls.cache.name)
        engine = os.environ.get("NFQWS_IP_HEALTH_TEST_ENGINE")
        library = os.environ.get("NFQWS_IP_HEALTH_TEST_LIB")
        if not engine:
            candidates = sorted(WORKSPACE.parent.parent.glob("build*/release*/native/*_x86_64.ipk"))
            if candidates:
                with tarfile.open(candidates[-1]) as package:
                    data = package.extractfile("./data.tar.gz").read()
                with tarfile.open(fileobj=io.BytesIO(data)) as payload:
                    for name, destination in (("./usr/bin/nfqws2", root / "nfqws2"),
                                              ("./usr/share/nfqws2/defaults/lua/zapret-lib.lua", root / "zapret-lib.lua")):
                        destination.write_bytes(payload.extractfile(name).read())
                (root / "nfqws2").chmod(0o755)
                engine, library = str(root / "nfqws2"), str(root / "zapret-lib.lua")
            else:
                engine = shutil.which("nfqws2")
        if not library:
            candidates = list((WORKSPACE / "source/sources").glob("zapret2-038c97e5*.tar.gz"))
            if candidates:
                with tarfile.open(candidates[0]) as source:
                    name = next(n for n in source.getnames() if n.endswith("/lua/zapret-lib.lua"))
                    (root / "zapret-lib.lua").write_bytes(source.extractfile(name).read())
                library = str(root / "zapret-lib.lua")
        if not engine or not library:
            raise unittest.SkipTest("pinned native engine unavailable; set NFQWS_IP_HEALTH_TEST_ENGINE and NFQWS_IP_HEALTH_TEST_LIB")
        version = subprocess.check_output([engine, "--version"], text=True)
        if "v1.0.7 (038c97e5819df10f8e8c22a2f1fffe57f2f7379b)" not in version:
            raise AssertionError("Lua packet tests require the pinned NFQWS2 1.0.7 engine")
        cls.command = [engine]
        if os.geteuid() != 0:
            ready = subprocess.run(["sudo", "-n", "true"], capture_output=True)
            if ready.returncode:
                raise unittest.SkipTest("engine packet reconstruction needs root raw-socket initialization (--intercept=0)")
            cls.command = ["sudo", "-n", engine]
        cls.library = library

    def run_lua(self, body):
        with tempfile.TemporaryDirectory(prefix="ip-health-lua-") as folder:
            folder = Path(folder)
            manifest = folder / "active.txt"
            events = folder / "events"
            events.mkdir()
            script = folder / "case.lua"
            script.write_text((PROJECT / "tests/fixtures/ip_health_harness.lua").read_text() + "\n" + body + '\nprint("IPHEALTH_TEST_OK")\n')
            args = self.command + ["--intercept=0", f"--uid={os.getuid()}:{os.getgid()}",
                                   f"--lua-init=@{self.library}",
                                   f'--lua-init=IPHEALTH_MANIFEST="{manifest}";WRITABLE="{events}";IPHEALTH_SOURCE="{PROJECT / "ip-health"}"',
                                   f"--lua-init=@{script}"]
            result = subprocess.run(args, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("IPHEALTH_TEST_OK", result.stdout, result.stdout + result.stderr)

    def test_complete_hello_reports_once_without_retransmission_and_reply_cancels(self):
        self.run_lua('''
manifest(); load_health()
local d=tcp(true); d.dis.payload=hello; d.reasm_data=hello
assert(ip_health_tcp({},d)==VERDICT_PASS)
advance(2.999); assert(events()=="")
advance(.001); assert(events()=="silent|1800000003|8.8.8.8|45000|www.example.com\\n")
advance(1); ip_health_tcp({},d); advance(1); assert(lines(events())==1)
local incoming=tcp(false); incoming.dis.payload="alert"
ip_health_tcp({},incoming); assert(lines(events())==2)
advance(4); assert(lines(events())==2)
''')

    def test_partial_hello_private_endpoint_invalid_hostname_and_closed_flow_never_report(self):
        self.run_lua('''
manifest(); load_health()
local d=tcp(true); d.dis.payload=hello:sub(1,15); d.reasm_data=d.dis.payload
ip_health_tcp({},d)
local private=tcp(true,"192.168.1.4",45001); private.dis.payload=hello; ip_health_tcp({},private)
local bad=tcp(true,"8.8.4.4",45002); bad.dis.payload=hello; bad.track.hostname="x|injection"; ip_health_tcp({},bad)
local good=tcp(true,"9.9.9.9",45003); good.dis.payload=hello; ip_health_tcp({},good)
local closed=tcp(false,"9.9.9.9",45003); closed.dis.tcp.th_flags=TH_RST; ip_health_tcp({},closed)
advance(4); assert(events()=="reply|1800000000|9.9.9.9|0|\\n")
''')

    def test_local_transition_reserved_addresses_and_empty_hostname_labels_are_ignored(self):
        self.run_lua('''
manifest(); load_health()
local ips={"0.1.2.3","10.0.0.1","100.64.1.2","127.0.0.1","169.254.1.2","172.16.1.2",
 "192.0.2.1","198.18.0.1","198.51.100.1","203.0.113.1","224.0.0.1","255.255.255.255",
 "::1","::ffff:192.168.1.1","64:ff9b::c0a8:101","2001:db8::1","2002:c0a8:101::1","fc00::1","fe80::1","ff02::1"}
for n,ip in ipairs(ips) do local d=tcp(true,ip,45000+n); d.dis.payload=hello; ip_health_tcp({},d) end
local d=tcp(true); d.dis.payload=hello; d.track.hostname=".www.example.com"; ip_health_tcp({},d)
advance(3); assert(events()=="")
''')

    def test_manifest_is_read_at_most_once_a_second_and_disable_drops_pending_flow(self):
        self.run_lua('''
manifest(); local open=io.open; local reads=0
io.open=function(path,mode) if path==IPHEALTH_MANIFEST and mode=="rb" then reads=reads+1 end; return open(path,mode) end
load_health(); local d=tcp(true); d.dis.payload=hello
for _=1,100 do ip_health_tcp({},d) end
assert(reads==1); advance(1); assert(reads==2)
manifest({},false); advance(1); manifest(); advance(3)
assert(events()=="")
''')

    def test_manifest_expiry_disable_bad_time_and_corruption_fail_open_clear_tracking(self):
        self.run_lua('''
manifest({"8.8.8.8"}); load_health()
assert(ip_health_tcp({},tcp(true))==VERDICT_DROP); assert(#sent==1)
advance(16); assert(ip_health_tcp({},tcp(true))==VERDICT_PASS)
manifest({},false); advance(1); local d=tcp(true); d.dis.payload=hello; ip_health_tcp({},d)
advance(3); assert(events()=="")
manifest({"8.8.8.8"}); advance(1); assert(ip_health_tcp({},tcp(true))==VERDICT_DROP)
write_manifest("IPHEALTH1\\nexpires 1800000040\\nenabled 1\\nban 8.8.8.8 1800000200\\nbad\\n")
advance(1); assert(ip_health_tcp({},tcp(true))==VERDICT_PASS)
manifest({"8.8.8.8"}); advance(1); assert(ip_health_tcp({},tcp(true))==VERDICT_DROP)
now=100; assert(ip_health_tcp({},tcp(true))==VERDICT_PASS)
''')

    def test_tcp_resets_reverse_client_tuple_for_syn_and_ack_and_fail_open_on_send_error(self):
        self.run_lua('''
manifest({"8.8.8.8","2001:4860:4860::8888"}); load_health()
local syn=tcp(true); syn.dis.tcp.th_flags=TH_SYN; syn.dis.tcp.th_seq=4294967295
assert(ip_health_tcp({},syn)==VERDICT_DROP)
local r=sent[1].dis; assert(ntop(r.ip.ip_src)=="8.8.8.8" and ntop(r.ip.ip_dst)=="192.168.50.2")
assert(r.tcp.th_sport==443 and r.tcp.th_dport==45000)
assert(r.tcp.th_flags==TH_RST+TH_ACK and r.tcp.th_seq==0 and r.tcp.th_ack==0)
assert(r.payload=="" and #r.tcp.options==0 and sent[1].opts.fwmark==0x123)
assert(checksum(sent[1].raw:sub(1,20))==0)
local a=tcp(true,"2001:4860:4860::8888"); a.dis.tcp.th_ack=98765
assert(ip_health_tcp({},a)==VERDICT_DROP)
local r6=sent[2].dis; assert(ntop(r6.ip6.ip6_dst)=="fd00::2")
assert(r6.tcp.th_seq==98765 and r6.tcp.th_flags==TH_RST and r6.tcp.th_ack==0)
assert(l4_checksum(sent[2].raw)==0)
send_ok=false; assert(ip_health_tcp({},syn)==VERDICT_PASS)
''')

    def test_timer_can_reset_silent_flow_after_confirmation_without_client_packet(self):
        self.run_lua('''
manifest(); load_health()
local d=tcp(true); d.dis.payload=hello; ip_health_tcp({},d)
advance(3); assert(lines(events())==1 and #sent==0)
manifest({"8.8.8.8"}); advance(1)
assert(#sent==1 and sent[1].dis.tcp.th_dport==45000)
advance(2); assert(#sent==1)
''')

    def test_fast_open_retransmission_keeps_timer_and_reset_acknowledges_syn_payload(self):
        self.run_lua('''
manifest(); load_health()
local d=tcp(true); d.dis.tcp.th_flags=TH_SYN; d.dis.payload=hello
ip_health_tcp({},d); advance(1.5); ip_health_tcp({},d); advance(1.5)
assert(lines(events())==1)
manifest({"8.8.8.8"}); advance(1)
assert(#sent==1 and sent[1].dis.tcp.th_ack==101+#hello)
''')

    def test_flow_and_event_storage_are_bounded_and_expired_flow_does_not_report(self):
        self.run_lua('''
manifest(); load_health()
for port=45000,45600 do local d=tcp(true,"8.8.8.8",port); d.dis.payload=hello; ip_health_tcp({},d) end
advance(3); assert(lines(events())==512)
write_events(string.rep("x",262140)); local d=tcp(true,"8.8.4.4",45999); d.dis.payload=hello; ip_health_tcp({},d)
advance(3); assert(#events()==262140)
write_events(""); advance(20); assert(events()=="")
''')

    def test_same_conntrack_cannot_emit_a_second_incident_after_timeout_or_reply(self):
        self.run_lua('''
manifest(); load_health()
local d=tcp(true); d.dis.payload=hello
ip_health_tcp({},d); advance(3); assert(lines(events())==1)
advance(13); manifest(); ip_health_tcp({},d); advance(3)
assert(lines(events())==1)
local fresh=tcp(true,"8.8.4.4",45001); fresh.dis.payload=hello; ip_health_tcp({},fresh)
local incoming=tcp(false,"8.8.4.4",45001); incoming.dis.payload="alert"
ip_health_tcp({},incoming); ip_health_tcp({},fresh); advance(3)
assert(lines(events())==2)
''')

    def test_manifest_missing_oversized_future_private_and_excess_entries_fail_open(self):
        self.run_lua('''
manifest({"8.8.8.8"}); load_health()
assert(ip_health_tcp({},tcp(true))==VERDICT_DROP)
local initial="IPHEALTH1\\nexpires "..(math.floor(now)+15).."\\nenabled 1\\n"
local too_many=initial
for n=1,513 do too_many=too_many.."ban 8.8."..math.floor(n/256).."."..(n%256).." 1800086400\\n" end
local cases={initial..string.rep("x",65536).."\\n",initial.."ban 192.168.1.1 1800086400\\n",
 "IPHEALTH1\\nexpires 1800001000\\nenabled 1\\nban 8.8.8.8 1800086400\\n",too_many}
for _,value in ipairs(cases) do write_manifest(value); advance(1); assert(ip_health_tcp({},tcp(true))==VERDICT_PASS) end
os.remove(IPHEALTH_MANIFEST); advance(1); assert(ip_health_tcp({},tcp(true))==VERDICT_PASS)
''')

    def test_reset_strips_extension_headers_and_never_answers_an_existing_reset(self):
        self.run_lua('''
manifest({"2001:4860:4860::8888"}); load_health()
local d=tcp(true,"2001:4860:4860::8888")
d.dis.ip6.exthdr={{type=IPPROTO_DSTOPTS,next=6,data=string.rep("\\0",6)}}
assert(ip_health_tcp({},d)==VERDICT_DROP)
assert(not sent[1].dis.ip6.exthdr or #sent[1].dis.ip6.exthdr==0)
assert(l4_checksum(sent[1].raw)==0)
d.dis.tcp.th_flags=TH_RST
assert(ip_health_tcp({},d)==VERDICT_PASS and #sent==1)
''')

    def test_udp_refusal_ipv4_ipv6_quotes_original_and_checksums_and_ignores_inbound(self):
        self.run_lua('''
manifest({"8.8.8.8","2001:4860:4860::8888"}); load_health()
for _,ip in ipairs({"8.8.8.8","2001:4860:4860::8888"}) do
 local d=udp(true,ip); local original=reconstruct_dissect(d.dis)
 assert(ip_health_udp({raw=original},d)==VERDICT_DROP)
 local s=sent[#sent]; local r=s.dis
 assert(ntop(dis_ipdst(r))==(d.dis.ip and "192.168.50.2" or "fd00::2"))
 assert(r.icmp.icmp_type==(d.dis.ip and 3 or 1) and r.icmp.icmp_code==(d.dis.ip and 3 or 4))
 assert(r.payload==original:sub(1,d.dis.ip and 28 or #original))
 assert(l4_checksum(s.raw)==0)
 assert(ip_health_udp({raw=original},udp(false,ip))==VERDICT_PASS)
end
send_ok=false; local d=udp(true); assert(ip_health_udp({raw=reconstruct_dissect(d.dis)},d)==VERDICT_PASS)
''')

    def test_icmp_quotes_ipv4_options_and_limits_ipv6_to_minimum_mtu(self):
        self.run_lua('''
manifest({"8.8.8.8","2001:4860:4860::8888"}); load_health()
local v4=udp(true); v4.dis.ip.options="\\1\\1\\1\\1"; v4.dis.ip.ip_hl=6
local raw4=reconstruct_dissect(v4.dis); assert(ip_health_udp({raw=raw4},v4)==VERDICT_DROP)
assert(sent[1].dis.payload==raw4:sub(1,32) and l4_checksum(sent[1].raw)==0)
local v6=udp(true,"2001:4860:4860::8888"); v6.dis.payload=string.rep("q",2000)
local raw6=reconstruct_dissect(v6.dis); assert(ip_health_udp({raw=raw6},v6)==VERDICT_DROP)
assert(#sent[2].raw==1280 and sent[2].dis.payload==raw6:sub(1,1232) and l4_checksum(sent[2].raw)==0)
''')

    def test_dns_rebuilds_compressed_cname_and_keeps_usable_requested_family(self):
        self.run_lua('''
manifest({"8.8.8.8"}); load_health()
local payload=dns_answer({"8.8.8.8","8.8.4.4"},true)
local d=dns_packet(payload); assert(ip_health_dns({},d)==VERDICT_DROP)
local p=sent[1].dis.payload; assert(u16(p,7)==2)
assert(p:find(pton("8.8.4.4"),1,true) and not p:find(pton("8.8.8.8"),1,true))
assert(p:find("\\5alias\\7example\\3com\\0",1,true))
assert(ntop(sent[1].dis.ip.ip_src)=="192.168.50.1" and sent[1].dis.udp.uh_sport==53)
assert(l4_checksum(sent[1].raw)==0)
local q="\\3www\\7example\\3com\\0"; local alias="\\5alias\\7example\\3com\\0"
local expected=bu16(123)..bu16(0x8180)..bu16(1)..bu16(2)..bu16(0)..bu16(0)..q..bu16(1)..bu16(1)..
 q..bu16(5)..bu16(1)..bu32(60)..bu16(19)..alias..alias..bu16(1)..bu16(1)..bu32(60)..bu16(4).."\\8\\8\\4\\4"
assert(p==expected)
''')

    def test_dns_router_output_with_opt_keeps_reply_tuple_and_query_data_is_untouched(self):
        self.run_lua('''
manifest({"8.8.8.8"}); load_health()
local base=dns_answer({"8.8.8.8","8.8.4.4"})
local opt="\\0"..bu16(41)..bu16(1232)..bu32(0)..bu16(12)..bu16(10)..bu16(8).."01234567"
local response=base:sub(1,10)..bu16(1)..base:sub(13)..opt
local d=dns_packet(response); d.outgoing=true; d.ifout="br0"
assert(ip_health_dns({},d)==VERDICT_DROP)
assert(sent[1].opts.ifout=="br0" and sent[1].dis.payload:sub(-23)==opt)
local query=base:sub(1,2)..bu16(0x0100)..base:sub(5)
assert(ip_health_dns({},dns_packet(query))==VERDICT_PASS and #sent==1)
''')

    def test_dns_unrelated_address_and_unsupported_record_cannot_justify_rewrite(self):
        self.run_lua('''
manifest({"8.8.8.8"}); load_health()
local q="\\3www\\7example\\3com\\0"..bu16(1)..bu16(1)
local header=bu16(123)..bu16(0x8180)..bu16(1)..bu16(2)..bu16(0)..bu16(0)
local bad="\\192\\12"..bu16(1)..bu16(1)..bu32(60)..bu16(4).."\\8\\8\\8\\8"
local unrelated="\\5other\\7example\\3com\\0"..bu16(1)..bu16(1)..bu32(60)..bu16(4).."\\8\\8\\4\\4"
assert(ip_health_dns({},dns_packet(header..q..bad..unrelated))==VERDICT_PASS)
local mx="\\192\\12"..bu16(15)..bu16(1)..bu32(60)..bu16(4).."\\0\\0\\192\\12"
assert(ip_health_dns({},dns_packet(header..q..bad..mx))==VERDICT_PASS and #sent==0)
''')

    def test_dns_aaaa_filter_and_last_address_preservation_and_send_failure(self):
        self.run_lua('''
manifest({"8.8.8.8","2001:4860:4860::8888"}); load_health()
local d=dns_packet(dns_answer({"2001:4860:4860::8888","2606:4700:4700::1111"},false,28))
assert(ip_health_dns({},d)==VERDICT_DROP and u16(sent[1].dis.payload,7)==1)
assert(ip_health_dns({},dns_packet(dns_answer({"8.8.8.8"})))==VERDICT_PASS)
assert(ip_health_dns({},dns_packet(dns_answer({"8.8.8.8","192.168.1.8"})))==VERDICT_PASS)
send_ok=false; assert(ip_health_dns({},dns_packet(dns_answer({"8.8.8.8","8.8.4.4"})))==VERDICT_PASS)
''')

    def test_dns_unsupported_dnssec_truncated_loop_and_authority_are_unchanged(self):
        self.run_lua('''
manifest({"8.8.8.8"}); load_health()
local base=dns_answer({"8.8.8.8","8.8.4.4"})
local cases={base:sub(1,2)..bu16(0x8380)..base:sub(5),base:sub(1,2)..bu16(0x81a0)..base:sub(5),
 base:sub(1,8)..bu16(1)..base:sub(11),base:sub(1,12).."\\192\\12"..base:sub(26),
 base:sub(1,10)..bu16(1)..base:sub(13).."\\0"..bu16(41)..bu16(1232)..bu32(0x8000)..bu16(0),
 base:sub(1,12).."\\64bad"..base:sub(17),base:sub(1,#base-1),base.."extra"}
cases[#cases+1]=base:sub(1,2)..bu16(0x81c0)..base:sub(5)
cases[#cases+1]=base:sub(1,10)..bu16(1)..base:sub(13).."\\0"..bu16(41)..bu16(1232)..bu32(1)..bu16(0)
for _,p in ipairs(cases) do assert(ip_health_dns({},dns_packet(p))==VERDICT_PASS) end
assert(#sent==0)
''')


if __name__ == "__main__":
    unittest.main()

"""Run the real freestanding DNS client against bounded loopback fixtures."""
import contextlib
import json
import os
import socket
import struct
import subprocess
import threading
import unittest
from pathlib import Path
from test_dpi_normalize import ROOT


@contextlib.contextmanager
def server(kind='udp', mode='valid', ipv6=False):
    family=socket.AF_INET6 if ipv6 else socket.AF_INET
    sock=socket.socket(family,socket.SOCK_STREAM if kind=='tcp' else socket.SOCK_DGRAM)
    sock.bind(('::1' if ipv6 else '127.0.0.1',0));sock.settimeout(0.8)
    if kind=='tcp':sock.listen(1)
    def respond():
        conn=None
        try:
            if kind=='tcp':
                conn,_=sock.accept();conn.settimeout(0.8);n=conn.recv(2)
                if len(n)!=2:return
                query=conn.recv(struct.unpack('!H',n)[0])
            else:query,peer=sock.recvfrom(4096)
            if len(query)<17:return
            flags=0x8380 if mode=='truncated' else (0x8183 if mode=='nxdomain' else 0x8180)
            qtype=struct.unpack('!H',query[-4:-2])[0]
            rdata=socket.inet_pton(socket.AF_INET6,'2001:db8::10') if qtype==28 else b'\xc0\x00\x02\x01'
            answer=b'\xc0\x0c'+struct.pack('!HHIH',qtype,1,60,len(rdata))+rdata
            response=query[:2]+struct.pack('!HHHHH',flags,1,0 if mode in ['nxdomain','nodata'] else 1,0,0)+query[12:]
            if mode not in ['nxdomain','nodata']:response+=answer
            if mode=='wrong_id':response=bytes([response[0]^1])+response[1:]
            if mode=='wrong_question':response=response[:13]+b'X'+response[14:]
            if mode=='compression_loop':
                at=len(query);response=response[:at]+bytes([0xc0|(at>>8),at&255])+response[at+2:]
            if mode=='bad_length':response=response[:-2]
            if mode=='silent':return
            if kind=='tcp':
                payload=struct.pack('!H',len(response))+response
                # Deliberately split the length prefix and body across writes.
                for part in [payload[:1],payload[1:7],payload[7:]]:conn.sendall(part)
            elif mode=='wrong_source':
                with socket.socket(family,socket.SOCK_DGRAM) as other:other.sendto(response,peer)
            else:sock.sendto(response,peer)
        except (OSError,ValueError):pass
        finally:
            if conn:conn.close()
    thread=threading.Thread(target=respond,daemon=True);thread.start()
    try:yield sock.getsockname()[1]
    finally:sock.close();thread.join(1)


class SmartDnsDnsProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary=Path(os.environ['SMARTDNS_DNS_PROBE_TEST_BINARY']) if os.environ.get('SMARTDNS_DNS_PROBE_TEST_BINARY') else ROOT/'.superpowers/sdd/2026-10-19-router-checkup-smartdns/dns-probe-host'
        source=ROOT/'asus/smartdns/dns-probe.c'
        cls.available=source.is_file()
        if cls.available and not os.environ.get('SMARTDNS_DNS_PROBE_TEST_BINARY'):
            p=subprocess.run(['gcc','-Os','-nostdlib','-static','-fno-builtin','-fno-stack-protector','-fno-pie','-no-pie','-Wl,--build-id=none','-Wl,-z,noexecstack','-Wall','-Wextra',str(source),'-o',str(cls.binary)],capture_output=True,text=True)
            if p.returncode:raise AssertionError(p.stderr)

    def query(self, port, kind='udp', address='127.0.0.1', name='example.org', timeout=250, qtype='A'):
        if not self.available:return 2,{'ok':False,'reason':'missing_probe'}
        p=subprocess.run([str(self.binary),address,str(port),name,qtype,kind,str(timeout)],capture_output=True,text=True,timeout=2)
        self.assertEqual(p.stderr,'');return p.returncode,json.loads(p.stdout)

    def test_valid_reply_and_fragmented_tcp_are_accepted(self):
        for kind in ['udp','tcp']:
            with self.subTest(kind=kind),server(kind=kind) as port:
                rc,value=self.query(port,kind)
                self.assertEqual(rc,0);self.assertTrue(value['ok']);self.assertEqual(value['answers'],['192.0.2.1'])
                self.assertEqual(value['rcode'],0);self.assertFalse(value['truncated'])

    def test_valid_empty_answer_is_distinct_from_malformed_packet(self):
        with server(mode='nodata') as port:
            rc,value=self.query(port)
            self.assertNotEqual(rc,0);self.assertFalse(value['ok']);self.assertEqual(value['rcode'],0);self.assertEqual(value['answers'],[]);self.assertEqual(value['reason'],'no_address')

    def test_wrong_id_source_question_and_truncation_fail(self):
        for mode in ['wrong_id','wrong_source','wrong_question','truncated','compression_loop','bad_length','nxdomain','silent']:
            with self.subTest(mode=mode),server(mode=mode) as port:
                rc,value=self.query(port)
                self.assertNotEqual(rc,0);self.assertFalse(value['ok'])
                self.assertNotEqual(value.get('reason'),'missing_probe')
                if mode=='truncated':self.assertTrue(value['truncated'])

    def test_ipv6_transport_does_not_need_system_resolver(self):
        with server(ipv6=True) as port:
            rc,value=self.query(port,address='::1')
            self.assertEqual(rc,0);self.assertEqual(value['answers'],['192.0.2.1'])

    def test_aaaa_reply_is_preserved_over_both_transports(self):
        for kind in ['udp','tcp']:
            with self.subTest(kind=kind),server(kind=kind) as port:
                rc,value=self.query(port,kind,qtype='AAAA')
                self.assertEqual(rc,0);self.assertTrue(value['ok'])
                self.assertEqual([socket.inet_pton(socket.AF_INET6,a).hex() for a in value['answers']],
                                 ['20010db8000000000000000000000010'])

    def test_invalid_arguments_never_become_options_or_queries(self):
        for address,port,name in [('not-an-ip',53,'example.org'),('127.0.0.1',0,'example.org'),
                                  ('127.0.0.1',53,'-host-ip'),('127.0.0.1',53,'a..example'),
                                  ('127.0.0.1',53,'a\nserver.example')]:
            with self.subTest(address=address,port=port,name=name):
                rc,value=self.query(port,address=address,name=name)
                self.assertNotEqual(rc,0);self.assertEqual(value.get('reason'),'invalid_arguments')


if __name__=='__main__':unittest.main()

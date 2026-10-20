"""Exercise large report transport through the shipped lighttpd/PHP CGI stack."""
import ctypes
import hashlib
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.parse

ROOT=Path(__file__).resolve().parents[1]


class RouterBodyTests(unittest.TestCase):
    def test_upgrade_replaces_cached_html_even_with_unchanged_package_mtime_and_size(self):
        wrapper=Path(os.environ.get('PHP_CGI_TEST_BINARY',ROOT/'.work/packaging-audit-20261012/aarch64-cgi-wrapper'))
        abi=wrapper.name.removesuffix('-cgi-wrapper')
        runtime=wrapper.parent/(abi+'-sysroot')
        qemu=wrapper.parent/('qemu-aarch64' if abi=='aarch64' else 'qemu-arm')
        with tempfile.TemporaryDirectory() as directory:
            directory=Path(directory); doc=directory/'www'; doc.mkdir()
            run=directory/'run'; run.mkdir()
            index=doc/'index.html'; index.write_bytes(b'<html>old</html>'); os.utime(index,(0,0))
            asset=doc/'assets/app.123456.js'; asset.parent.mkdir(); asset.write_bytes(b'const ready=true;')
            with socket.socket() as s: s.bind(('127.0.0.1',0)); port=s.getsockname()[1]
            env=os.environ|{'WEB_BIND':'127.0.0.1','WEB_RUN':str(run)}
            config=subprocess.check_output(['bash','-c','. "$1"; web_config','sh',str(ROOT/'asus/web-lib.sh')],env=env,text=True)
            config=config.replace('server.port = 90',f'server.port = {port}').replace('/opt/share/nfqws-asus-web',str(doc))
            conf=directory/'lighttpd.conf'; conf.write_text(config)
            process=subprocess.Popen([str(qemu),'-L',str(runtime),str(runtime/'opt/sbin/lighttpd'),'-D','-m',str(runtime/'opt/lib/lighttpd'),'-f',str(conf)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            def request(path,headers=None):
                connection=http.client.HTTPConnection('127.0.0.1',port,timeout=5)
                try:
                    connection.request('GET',path,headers=headers or {})
                    response=connection.getresponse()
                    return response.status,dict(response.getheaders()),response.read()
                finally: connection.close()
            try:
                for _ in range(100):
                    try:
                        status,headers,body=request('/'); break
                    except ConnectionRefusedError:
                        if process.poll() is not None: self.fail(process.stderr.read().decode())
                        time.sleep(.02)
                else: self.fail('isolated lighttpd not ready')
                self.assertEqual((status,body),(200,b'<html>old</html>'))
                stale={'If-None-Match':headers.get('ETag','"stale-from-previous-build"'),
                       'If-Modified-Since':headers.get('Last-Modified','Thu, 01 Jan 1970 00:00:00 GMT')}
                index.write_bytes(b'<html>new</html>'); os.utime(index,(0,0))
                for path in ['/','/index.html','/settings']:
                    with self.subTest(path=path):
                        status,headers,body=request(path,stale)
                        self.assertEqual((status,body),(200,b'<html>new</html>'),
                                         'old browser validators must not preserve the previous frontend')
                        self.assertEqual(headers.get('Cache-Control'),'no-store')
                status,headers,body=request('/assets/app.123456.js')
                self.assertEqual(status,200)
                self.assertIn('ETag',headers)
                self.assertEqual(request('/assets/app.123456.js',{'If-None-Match':headers['ETag']})[0],304)
            finally:
                process.terminate(); process.wait(timeout=5); process.stderr.close()

    def test_large_report_uses_only_private_ram_buffers_and_preserves_bytes(self):
        wrapper=Path(os.environ.get('PHP_CGI_TEST_BINARY',ROOT/'.work/packaging-audit-20261012/aarch64-cgi-wrapper'))
        abi=wrapper.name.removesuffix('-cgi-wrapper')
        runtime=wrapper.parent/(abi+'-sysroot')
        qemu=wrapper.parent/('qemu-aarch64' if abi=='aarch64' else 'qemu-arm')
        self.assertTrue((runtime/'opt/sbin/lighttpd').is_file())
        with tempfile.TemporaryDirectory() as disk, tempfile.TemporaryDirectory(dir='/dev/shm') as ram:
            disk=Path(disk); ram=Path(ram)
            fallback=disk/'fallback'; fallback.mkdir()
            (ram/'sessions').mkdir()
            doc=disk/'www'; doc.mkdir(); (doc/'index.html').write_text('ready')
            (doc/'echo.php').write_text("<?php $v=$_POST['report']??''; echo json_encode(['bytes'=>strlen($v),'sha256'=>hash('sha256',$v)]);")
            cgi=disk/'cgi.sh'
            cgi.write_text((ROOT/'asus/php-cgi.sh').read_text().replace('/opt/bin/php-cgi',str(wrapper)+' -n -d cgi.force_redirect=0').replace('/tmp/nfqws-asus-web',str(ram)).replace('/opt/share/nfqws-asus-web',str(doc)))
            cgi.chmod(0o700)
            with socket.socket() as s: s.bind(('127.0.0.1',0)); port=s.getsockname()[1]
            env=os.environ|{'WEB_BIND':'127.0.0.1','WEB_RUN':str(ram),'TMPDIR':str(fallback)}
            cfg=subprocess.check_output(['bash','-c','. "$1"; web_config','sh',str(ROOT/'asus/web-lib.sh')],env=env,text=True)
            cfg=cfg.replace('server.port = 90',f'server.port = {port}').replace('/opt/share/nfqws-asus-web',str(doc)).replace('/opt/lib/nfqws-asus-web/php-cgi.sh',str(cgi))
            conf=disk/'lighttpd.conf'; conf.write_text(cfg)
            command=[str(qemu),'-L',str(runtime),str(runtime/'opt/sbin/lighttpd'),'-D','-m',str(runtime/'opt/lib/lighttpd'),'-f',str(conf)]
            libc=ctypes.CDLL(None,use_errno=True)
            watch=libc.inotify_init1(os.O_NONBLOCK|os.O_CLOEXEC)
            self.assertGreaterEqual(watch,0)
            self.assertGreaterEqual(libc.inotify_add_watch(watch,str(fallback).encode(),0x100),0)
            process=subprocess.Popen(command,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            try:
                for _ in range(100):
                    try:
                        conn=http.client.HTTPConnection('127.0.0.1',port,timeout=5)
                        conn.request('GET','/index.html'); response=conn.getresponse(); response.read(); conn.close(); break
                    except ConnectionRefusedError:
                        if process.poll() is not None: self.fail(process.stderr.read().decode())
                        time.sleep(.02)
                else: self.fail('isolated lighttpd not ready')
                raw=b'{"anonymous":"report"}'+b' '*(1048576-22)
                body=urllib.parse.urlencode({'report':raw.decode()}).encode()
                conn=http.client.HTTPConnection('127.0.0.1',port,timeout=10)
                conn.request('POST','/echo.php',body,{'Content-Type':'application/x-www-form-urlencoded'})
                response=conn.getresponse(); payload=response.read(); conn.close()
                self.assertEqual(response.status,200,payload)
                self.assertEqual(json.loads(payload),{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
                try: events=os.read(watch,65536)
                except BlockingIOError: events=b''
                self.assertEqual(events,b'','report body reached the default disk temporary directory')
            finally:
                process.terminate(); process.wait(timeout=5); process.stderr.close(); os.close(watch)

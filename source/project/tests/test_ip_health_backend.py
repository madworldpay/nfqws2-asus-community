"""Execute the real PHP journal/controller and preserve state on short writes."""
import base64
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import ssl
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "webui/web/public"
NATIVE = Path.home() / ".local/state/nfqws2-asus/development/package-updates-20261016/native-php/root/usr/bin/php8.5"
PHP = os.environ.get("PHP_TEST_BINARY") or shutil.which("php") or str(NATIVE)


def command():
    args = [PHP, "-n"]
    extension = os.environ.get("PHP_TEST_SOCKET_EXTENSION")
    if extension:
        args += ["-d", "extension=" + extension]
    return args


class IpHealthBackendTests(unittest.TestCase):
    def test_real_php_backend_behaviors(self):
        result = subprocess.run(command() + [str(ROOT / "tests/test_ip_health_backend.php")],
                                capture_output=True, text=True, timeout=25)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertIn("PASS simultaneous clear transactions", result.stdout)

    @unittest.skipUnless((ROOT / ".work/packaging-audit-20261012/armv7-cli-wrapper").exists(),
                         "32-bit PHP fixture unavailable")
    def test_32_bit_monotonic_deadline_can_classify_a_connected_silent_socket(self):
        # The native PHP sockets module is absent from this ARM fixture. Only
        # its I/O boundary is controlled; real 32-bit hrtime arithmetic and the
        # full production connect/write/deadline path run unchanged.
        script = r"""define('AF_INET',2);define('AF_INET6',10);define('SOCK_STREAM',1);define('SOL_TCP',6);
        function socket_create(...$args){return 1;}
        function socket_set_nonblock($socket){return true;}
        function socket_connect(...$args){return true;}
        function socket_select(&$r,&$w,&$e,$seconds,$micros){static $calls=0;return ++$calls===1?1:0;}
        function socket_write($socket,$data){return strlen($data);}
        function socket_close($socket){}
        require $argv[1].'/ip-health-probe.php';
        class DeadlineProbe extends NfqwsIpHealthProbe {
          protected function prepareSocket(mixed $socket,string $interface):bool{return true;}
          public function run():string{return $this->exchange('93.184.216.34','example.com','eth0',443);}
        }
        echo json_encode(['integer_size'=>PHP_INT_SIZE,'answer'=>(new DeadlineProbe())->run()]);"""
        result = subprocess.run([str(ROOT / ".work/packaging-audit-20261012/armv7-cli-wrapper"),
                                 "-n", "-r", script, str(PUBLIC)],
                                capture_output=True, text=True, timeout=4)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout), {"integer_size": 4, "answer": "silent"})

    @unittest.skipUnless(shutil.which("openssl"), "OpenSSL CLI needed for local TLS fixture")
    def test_generated_client_hello_is_accepted_by_real_tls_server(self):
        # A malformed extension or length must produce a TLS alert, rather
        # than the real server's TLS1.2 handshake and the expected SNI.
        script = "require $argv[1].'/ip-health-probe.php';echo base64_encode(NfqwsIpHealthProbe::clientHello('example.com'));"
        result = subprocess.run(command() + ["-r", script, str(PUBLIC)],
                                capture_output=True, text=True, timeout=3)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        with tempfile.TemporaryDirectory() as directory:
            cert, key = Path(directory) / "cert.pem", Path(directory) / "key.pem"
            made = subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                                   "-keyout", str(key), "-out", str(cert), "-days", "1",
                                   "-subj", "/CN=example.com"], capture_output=True, timeout=5)
            self.assertEqual(made.returncode, 0, made.stderr.decode())
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = context.maximum_version = ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(cert, key)
            seen = []
            context.set_servername_callback(lambda connection, name, ctx: seen.append(name))
            incoming, outgoing = ssl.MemoryBIO(), ssl.MemoryBIO()
            server = context.wrap_bio(incoming, outgoing, server_side=True)
            incoming.write(base64.b64decode(result.stdout))
            with self.assertRaises(ssl.SSLWantReadError):
                server.do_handshake()
            self.assertEqual(seen, ["example.com"])
            self.assertEqual(outgoing.read()[0], 22, "server responds with handshake, not an alert")

    def test_short_write_preserves_previous_atomic_journal(self):
        script = """require $argv[1].'/ip-health-store.php';
        $store=new NfqwsIpHealthStore($argv[2],$argv[3]);
        try{$store->configure($argv[4]==='1',$store->status()['revision']);echo 'ok';}
        catch(Throwable $error){echo $error->getMessage();}"""
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state"
            run = Path(directory) / "run"
            args = command() + ["-r", script, str(PUBLIC), str(state), str(run)]
            first = subprocess.run(args + ["0"], capture_output=True, text=True, timeout=3)
            self.assertEqual(first.stdout, "ok", first.stdout + first.stderr)
            original = (state / "bans.json").read_bytes()

            def limit_file():
                signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
                resource.setrlimit(resource.RLIMIT_FSIZE, (16, 16))

            failed = subprocess.run(args + ["1"], capture_output=True, text=True,
                                    timeout=3, preexec_fn=limit_file)
            self.assertEqual(failed.returncode, 0, failed.stdout + failed.stderr)
            self.assertEqual(failed.stdout, "insufficient_space")
            self.assertEqual(failed.stderr, "")
            self.assertEqual((state / "bans.json").read_bytes(), original)
            self.assertEqual(list(state.glob(".write-*")), [])
            self.assertFalse(json.loads(original)["enabled"])


if __name__ == "__main__":
    unittest.main()

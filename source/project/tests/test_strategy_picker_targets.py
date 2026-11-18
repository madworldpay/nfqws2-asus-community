"""Custom goals must have one unambiguous host set before any network work."""
import base64
import json
import subprocess
import unittest
from test_dpi_normalize import PHP, PUBLIC


class CustomTargetBoundaryTests(unittest.TestCase):
    def php(self, body):
        result = subprocess.run([PHP, '-n', '-r', "require $argv[1].'/strategy-picker-targets.php';" + body,
                                 str(PUBLIC)], capture_output=True, text=True, timeout=8)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, '')
        return json.loads(result.stdout)

    def inspect(self, text):
        raw = text.encode() if isinstance(text, str) else text
        value = base64.b64encode(raw).decode()
        return self.php("echo json_encode(NfqwsStrategyPickerTargets::inspect(base64_decode('" + value + "')),JSON_THROW_ON_ERROR);")

    def test_unicode_names_work_without_intl_or_mbstring(self):
        r = self.inspect('пример.рф\nbücher.de\nfaß.de\nｅｘａｍｐｌｅ。ｃｏｍ')
        self.assertTrue(r['valid'])
        self.assertEqual(r['hosts'], ['xn--e1afmkfd.xn--p1ai', 'xn--bcher-kva.de', 'xn--fa-hia.de', 'example.com'])
        self.assertEqual(r['errors'], [])

    def test_urls_are_reduced_to_deduplicated_hostnames(self):
        r = self.inspect(' EXAMPLE.COM. \nhttps://example.com/a?q=1#x\nhttp://www.youtube.com/watch?v=x\nhttps://bücher.de/путь\nXN--BCHER-KVA.DE')
        self.assertTrue(r['valid'])
        self.assertEqual(r['hosts'], ['example.com', 'www.youtube.com', 'xn--bcher-kva.de'])

    def test_invalid_authorities_and_local_names_never_return_a_host_set(self):
        values = ['https://name:password@example.com/', 'https://example.com:443/', 'file://example.com/',
                  '//example.com', 'https://example.com\\@evil.com', 'user@example.com', '127.0.0.1',
                  '[::1]', '0x7f.1', '0177.0.0.1', '2130706433', 'example..com', '*.example.com',
                  'under_score.com', 'xn--a.com', 'xn--.com', 'a' * 64 + '.com', '.example.com',
                  'example.local', 'foo.home.arpa', 'foo.localhost', 'foo.invalid', 'foo.example',
                  'foo.test', 'foo.onion', 'foo.internal', 'https://exa%6dple.com/', 'example.com\x00']
        encoded = [base64.b64encode(v.encode()).decode() for v in values]
        r = self.php('$out=[];foreach(json_decode(\'' + json.dumps(encoded) + '\')as $v)$out[]=NfqwsStrategyPickerTargets::inspect(base64_decode($v));echo json_encode($out);')
        for value, result in zip(values, r):
            with self.subTest(value=value):
                self.assertFalse(result['valid'])
                self.assertEqual(result['hosts'], [])
                self.assertEqual(result['errors'][0]['line'], 1)
                self.assertIsNone(result['sha256'])

    def test_one_invalid_line_does_not_expose_partially_accepted_targets(self):
        r = self.inspect('example.com\nexample.local\nother.com')
        self.assertFalse(r['valid'])
        self.assertEqual(r['hosts'], [])
        self.assertEqual([x['line'] for x in r['errors']], [2])
        self.assertEqual(set(r['errors'][0]), {'line', 'code'})

    def test_legacy_hexadecimal_ipv4_forms_are_not_hostname_targets(self):
        for host in ['0x7f.0x1', '0x7f.0x0.0x0.0x1', '0xa9.0xfe.0xa9.0xfe', '127.0x1', '０ｘ７ｆ。０ｘ１']:
            with self.subTest(host=host):
                r=self.inspect(host)
                self.assertFalse(r['valid'])
                self.assertEqual(r['hosts'], [])
        mixed=self.inspect('example.com\n0x7f.0x1\nother.com')
        self.assertEqual(mixed['hosts'], [])
        self.assertEqual(mixed['errors'], [{'line': 2, 'code': 'invalid_hostname'}])

    def test_an_explicit_empty_port_is_not_silently_discarded(self):
        for url in ['https://example.com:', 'https://example.com:/path', 'example.com:',
                    'https://example.com:?query', 'https://example.com:#fragment']:
            with self.subTest(url=url):
                r=self.inspect(url)
                self.assertFalse(r['valid'])
                self.assertEqual(r['hosts'], [])
        self.assertTrue(self.inspect('https://example.com/path?q=:443#fragment:443')['valid'])

    def test_ten_unique_hosts_are_allowed_but_the_eleventh_is_reported(self):
        first = '\n'.join([f'host{i}.example.com' for i in range(10)])
        self.assertTrue(self.inspect(first)['valid'])
        extra = self.inspect(first + '\neleventh.example.com')
        self.assertFalse(extra['valid'])
        self.assertEqual(extra['hosts'], [])
        self.assertEqual(extra['errors'], [{'line': 11, 'code': 'too_many_hosts'}])
        self.assertTrue(self.inspect(first + '\nHOST0.EXAMPLE.COM')['valid'])

    def test_identity_is_for_the_canonical_set_and_not_input_order(self):
        a = self.inspect('example.com\nbücher.de')
        b = self.inspect('XN--BCHER-KVA.DE\nhttps://example.com/path')
        c = self.inspect('example.com\nother.com')
        self.assertEqual(a['sha256'], b['sha256'])
        self.assertNotEqual(a['sha256'], c['sha256'])
        self.assertRegex(a['sha256'], r'^[a-f0-9]{64}$')

    def test_malformed_utf8_and_unicode_context_fail_at_the_actual_line(self):
        bad = self.inspect(b'example.com\n\xff.com')
        self.assertEqual(bad['errors'], [{'line': 2, 'code': 'invalid_hostname'}])
        for host in ['ab\u200dcd.com', 'ab\u200ccd.com', 'abcא.com', '\u0301example.com']:
            with self.subTest(host=host):
                self.assertFalse(self.inspect(host)['valid'])

    def test_size_and_line_limits_fail_closed(self):
        for value in [' ', 'x' * 4097, '\n'.join(['example.com'] * 33), 'ü' * 513 + '.com']:
            with self.subTest(bytes=len(value.encode())):
                r = self.inspect(value)
                self.assertFalse(r['valid'])
                self.assertEqual(r['hosts'], [])
                self.assertTrue(r['errors'])

    def test_public_address_set_is_strict_and_rejects_the_entire_poisoned_answer(self):
        r = self.php("echo json_encode(NfqwsStrategyPickerTargets::addresses(['8.8.8.8','1.1.1.1','8.8.8.8']));")
        self.assertEqual(r, ['1.1.1.1', '8.8.8.8'])
        blocked = ['0.1.2.3', '10.0.0.1', '100.64.0.1', '127.0.0.1', '169.254.169.254', '172.16.0.1',
                   '192.0.0.9', '192.0.2.1', '192.168.1.1', '198.18.0.1', '198.51.100.1', '203.0.113.1',
                   '224.0.0.1', '255.255.255.255', '8.8.8.08', '::1', 2130706433, ['1.1.1.1']]
        raw = json.dumps(blocked)
        r = self.php('$out=[];foreach(json_decode(\'' + raw + '\',true)as $ip){try{NfqwsStrategyPickerTargets::addresses(["1.1.1.1",$ip]);$out[]="accepted";}catch(RuntimeException $e){$out[]=$e->getMessage();}}echo json_encode($out);')
        self.assertEqual(r, ['custom_non_public_address'] * len(blocked))

    def test_empty_and_oversized_dns_answers_are_not_validated_as_success(self):
        r = self.php('$out=[];foreach([[],array_fill(0,17,"1.1.1.1")]as $a){try{NfqwsStrategyPickerTargets::addresses($a);$out[]="accepted";}catch(RuntimeException $e){$out[]=$e->getMessage();}}echo json_encode($out);')
        self.assertEqual(r, ['custom_dns_failed', 'custom_dns_answer_too_large'])


if __name__ == '__main__':
    unittest.main()

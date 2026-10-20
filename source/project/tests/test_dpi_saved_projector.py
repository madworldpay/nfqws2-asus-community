"""Only recognized measurements from original text may cross the mail boundary."""
import hashlib,json,subprocess,unittest
from test_dpi_normalize import PHP,PUBLIC,ROOT

SAMPLE_EN='''DPI Detector v5.0.0-alpha.21
Network & System Information
IPv4: 203.0.113.91  Subnet 203.0.113.0/24  TTLB 45 ms
Organization: PRIVATE_CANARY_ISP
Location: PRIVATE_CANARY_CITY
DNS availability: 2/3 DoH 1/2 DoT 4/5 UDP
TLS / SNI Domain Inspection Results:
│ www.youtube.com │ OK │ TLS RST │ TIMEOUT │ DROP │ PRIVATE_CANARY_ERROR │
TCP 16–20 KB Block Check
│ HE-01 │ 24940 │ PRIVATE_CANARY_PROVIDER │ DETECTED │ private detail │
Found white SNI: in 1 of 3 blocked AS
Telegram Availability Check
│ DC1 │ 149.154.175.50 │ PRIVATE_CANARY_REGION │ OK │ 28 ms │
  Download: OK  Peak 4 MB/s Avg 2 MB/s (16 MB / 8s)
│ Fingerprint │ example.com │ www.google.com │ www.cloudflare.com │ Detail │
│ Chrome 133 │ 10/10 │ 5/10 │ 0/10 │ TLS RST ×15 │
SOCKS5 user:PRIVATE_CANARY_PASSWORD@192.168.5.9:1080
'''
SAMPLE_RU=SAMPLE_EN.replace('Network & System Information','Информация о сети и системе').replace('DNS availability','DNS доступность').replace('TLS / SNI Domain Inspection Results:','Результаты проверки доменов (TLS / SNI):').replace('TCP 16–20 KB Block Check','Проверка TCP 16-20KB блокировки').replace('Found white SNI: in 1 of 3 blocked AS','Найдено белых SNI: у 1 из 3 заблокированных AS').replace('Telegram Availability Check','Проверка доступности Telegram').replace('Download:','Скачивание:')

class DpiSavedProjectorTests(unittest.TestCase):
    def call(self,raw):
        code='''require $argv[1].'/dpi-saved-projector.php';try {echo json_encode(AsusDpiSavedProjector::project(stream_get_contents(STDIN),$argv[2]));}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),hashlib.sha256(raw.encode()).hexdigest()],input=raw,capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'')
        return json.loads(p.stdout)

    def test_seven_groups_preserve_measurements_without_identity(self):
        for text,language in [(SAMPLE_EN,'en'),(SAMPLE_RU,'ru')]:
            with self.subTest(language=language):
                v=self.call(text)
                self.assertEqual(v['type'],'nfqws2_dpi_saved')
                self.assertEqual(v['language'],language)
                self.assertEqual([g['group'] for g in v['groups']],list(range(7)))
                self.assertEqual(v['groups'][0]['metrics']['ipv4_latency_ms'],45)
                self.assertEqual(v['groups'][1]['metrics']['udp_total'],5)
                self.assertEqual(v['groups'][2]['rows'][0]['values']['tls12']['status'],'tls_rst')
                self.assertEqual(v['groups'][3]['rows'][0]['status'],'detected')
                self.assertEqual(v['groups'][4]['metrics']['found_as'],1)
                self.assertEqual(v['groups'][6]['rows'][1]['metrics'],{'answered':5,'attempts':10})
                self.assertNotIn('PRIVATE_CANARY',json.dumps(v))
                self.assertNotIn('203.0.113',json.dumps(v))
                self.assertNotIn('149.154',json.dumps(v))
                self.assertTrue(v['coverage']['partial'])
                self.assertGreater(v['coverage']['omitted_lines'],0)

    def test_unknown_text_or_no_measurements_cannot_be_sent(self):
        for raw in ['PRIVATE_CANARY','Network & System Information\nProvider: PRIVATE_CANARY','x'*1048577]:
            self.assertIn('error',self.call(raw))

    def test_padded_native_telegram_labels_preserve_download_and_upload(self):
        for heading,download,upload in [
            ('Telegram Availability Check','Download','Upload'),
            ('Информация о сети\nПроверка доступности Telegram','Скачивание','Загрузка'),
        ]:
            with self.subTest(upload=upload):
                raw=f'{heading}\n  {download}: BLOCKED  (0 B / 0s)\n  {upload}  : OK  PRIVATE_CANARY  (256 KB / 1s)\n'
                value=self.call(raw)
                rows=value['groups'][0]['rows']
                self.assertEqual([(r['direction'],r['status']) for r in rows],[('download','blocked'),('upload','ok')])
                self.assertEqual(rows[1]['metrics'],{'duration_ms':1000})
                self.assertNotIn('PRIVATE_CANARY',json.dumps(value))

    def test_unknown_target_and_raw_error_are_not_copied(self):
        text=SAMPLE_EN.replace('www.youtube.com','PRIVATE_CANARY.example')
        v=self.call(text)
        self.assertNotIn('PRIVATE_CANARY',json.dumps(v))
        self.assertNotIn(2,[g['group'] for g in v['groups']])

    def test_truncated_valid_report_remains_explicitly_partial(self):
        v=self.call('DNS availability: 2/3 DoH 1/2 DoT 4/5 UDP\nunfinished PRIVATE_CANARY')
        self.assertEqual([g['group'] for g in v['groups']],[1])
        self.assertEqual(v['groups'][0]['metrics']['doh_ok'],2)
        self.assertTrue(v['coverage']['partial'])

    def test_php_and_python_validate_same_closed_schema(self):
        from jsonschema import Draft202012Validator
        v=self.call(SAMPLE_EN)
        schema=json.loads((ROOT/'support/dpi-saved.schema.json').read_text())
        self.assertTrue(Draft202012Validator(schema).is_valid(v))
        v['raw']='PRIVATE_CANARY'
        self.assertFalse(Draft202012Validator(schema).is_valid(v))

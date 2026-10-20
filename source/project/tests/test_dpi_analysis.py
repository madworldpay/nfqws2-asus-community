import json,subprocess,unittest
from test_dpi_normalize import PHP,PUBLIC

class DpiAnalysisTests(unittest.TestCase):
    def test_projection_preserves_measurable_details_and_excludes_native_identifiers(self):
        raw={'schema_version':1,'results':{'domain_inspection':[{'domain':'PRIVATE_TARGET','resolved':'10.99.88.77','http':'ok','http_detail':'http_200','tls12':'ok','tls12_detail':'elapsed_1124ms','tls13':'timeout','tls13_detail':'read_timeout_word_at_24kb','quic':'timeout','quic_detail':'quic_timeout','unknown':'SECRET'}]}}
        code="if(!is_file($argv[1].'/dpi-analysis.php')){echo '{\"error\":\"missing\"}';exit;}require $argv[1].'/dpi-analysis.php';$g=AsusDpiNative::group($argv[2],2);$n=AsusDpiNative::document(['started_at'=>1760000000,'finished_at'=>1760000001,'state'=>'completed','tests'=>[2]],[$g],['before'=>['nfqws'=>'running','ark'=>'absent','tun_observed'=>false],'after'=>['nfqws'=>'running','ark'=>'absent','tun_observed'=>false],'changed'=>false],[],['domains'=>1],[]);echo AsusDpiAnalysis::report(json_decode($n,true));"
        p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),json.dumps(raw)],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr);r=json.loads(p.stdout);self.assertNotIn('error',r);self.assertEqual(r['schema_version'],2)
        for s in ['PRIVATE_TARGET','10.99.88.77','SECRET']:self.assertNotIn(s,p.stdout)
        text=json.dumps(r);self.assertIn('"http_status": 200',text);self.assertIn('"elapsed_ms": 1124',text);self.assertIn('"at_kib": 24',text);self.assertIn('quic_timeout',text)
    def test_all_seven_native_groups_have_identifier_free_analysis(self):
        from pathlib import Path
        root=Path(__file__).resolve().parents[1]
        code="require $argv[1].'/dpi-analysis.php';$g=AsusDpiNative::group($argv[2],(int)$argv[3]);$ctx=['nfqws'=>'running','ark'=>'absent','tun_observed'=>false];$n=AsusDpiNative::document(['started_at'=>1760000000,'finished_at'=>1760000001,'state'=>'completed','tests'=>[(int)$argv[3]]],[$g],['before'=>$ctx,'after'=>$ctx,'changed'=>false],[],[],[]);echo AsusDpiAnalysis::report(json_decode($n,true));"
        for group in range(7):
            with self.subTest(group=group):
                fixture=json.loads((root/f'tests/fixtures/dpi/group{group}.json').read_text())['raw']
                p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),json.dumps(fixture),str(group)],capture_output=True,text=True)
                self.assertEqual(p.returncode,0,p.stdout+p.stderr);r=json.loads(p.stdout);self.assertEqual(r['groups'][0]['group'],group);self.assertNotIn('PRIVATE_CANARY',p.stdout)

    def test_detail_empty_and_unknown_are_distinct(self):
        code="if(!is_file($argv[1].'/dpi-analysis.php')){echo '[]';exit;}require $argv[1].'/dpi-analysis.php';echo json_encode([AsusDpiAnalysis::detail(''),AsusDpiAnalysis::detail('PRIVATE_OS_ERROR')]);"
        p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC)],capture_output=True,text=True);self.assertEqual(json.loads(p.stdout),[{'code':'none'},{'code':'unclassified'}])

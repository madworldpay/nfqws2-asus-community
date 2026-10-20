"""Exercise projection, not a scrubber: raw identity must never be exported."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PHP = os.environ.get('PHP_TEST_BINARY', str(ROOT/'.work/packaging-audit-20261012/aarch64-cli-wrapper'))
PUBLIC = ROOT/'webui/web/public'


class DpiNormalizeTests(unittest.TestCase):
    def call(self, raw, group):
        code = '''require $argv[1].'/dpi-normalize.php';try {
        echo json_encode(AsusDpiNormalizer::group(file_get_contents($argv[2]),(int)$argv[3],AsusDpiCatalog::load()));
        } catch(Throwable $e) {echo json_encode(['error'=>$e->getMessage()]);}'''
        with tempfile.NamedTemporaryFile() as f:
            f.write(raw.encode());f.flush()
            p = subprocess.run([PHP,'-n','-r',code,str(PUBLIC),f.name,str(group)],text=True,capture_output=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stderr, '')
        return json.loads(p.stdout)

    def test_all_seven_groups_have_closed_projection(self):
        for group in range(7):
            with self.subTest(group=group):
                fixture=json.loads((ROOT/f'tests/fixtures/dpi/group{group}.json').read_text())
                value=self.call(json.dumps(fixture['raw']),group)
                self.assertEqual(value,fixture['expected'])
                self.assertNotIn('PRIVATE_CANARY',json.dumps(value))

    def test_unknown_schema_group_mismatch_duplicate_and_nonfinite_rejected(self):
        for raw,group in [('{"schema_version":2,"results":{}}',0),
                          ('{"schema_version":1,"schema_version":1,"results":{}}',0),
                          ('{"schema_version":1,"results":{"network_info":{}}}',1),
                          ('{"schema_version":1,"results":{"network_info":{"ipv4":{"latency_ms":1e999}}}}',0),
                          ('['*33+'0'+']'*33,0),('x'*524289,0)]:
            self.assertEqual(self.call(raw,group),{'error':'invalid_dpi'})

    def test_unknown_status_and_detail_are_fixed_unknown(self):
        raw={'schema_version':1,'results':{'tcp16':[{'id':'HE-01','asn':'PRIVATE_CANARY','provider':'PRIVATE_CANARY','status':'PRIVATE_CANARY','detail':'PRIVATE_CANARY'}]}}
        self.assertEqual(self.call(json.dumps(raw),3),{'group':3,'rows':[{'target':'HE-01','status':'unknown','detail':'unknown'}]})

    def test_negative_or_nonfinite_metric_is_an_error_not_success(self):
        raw={'schema_version':1,'results':{'whitelist_sni':{'detected_as':-1,'found_as':1}}}
        self.assertEqual(self.call(json.dumps(raw),4),{'error':'invalid_dpi'})

    def test_incomplete_sections_are_not_negative_measurements(self):
        for group in range(7):
            fixture=json.loads((ROOT/f'tests/fixtures/dpi/group{group}.json').read_text())['raw']
            key=next(iter(fixture['results']))
            for section in [None,{},'unavailable']:
                with self.subTest(group=group,section=section):
                    fixture['results'][key]=section
                    self.assertEqual(self.call(json.dumps(fixture),group),{'error':'invalid_dpi'})
        fixture=json.loads((ROOT/'tests/fixtures/dpi/group0.json').read_text())['raw']
        for key in ['ipv4','ipv6','tun','bypass_tools']:
            raw=json.loads(json.dumps(fixture));del raw['results']['network_info'][key]
            self.assertEqual(self.call(json.dumps(raw),0),{'error':'invalid_dpi'})
        fixture['results']['network_info']['ipv4']=None
        self.assertEqual(self.call(json.dumps(fixture),0)['ipv4'],False)


if __name__=='__main__':unittest.main()

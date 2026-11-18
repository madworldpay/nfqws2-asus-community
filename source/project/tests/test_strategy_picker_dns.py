"""A matching unknown DNS value must never certify comparable measurements."""
import copy
import json
import subprocess
import unittest
from test_dpi_normalize import PHP, PUBLIC
from test_strategy_picker_quic import native_fixture


class PickerDnsContextTests(unittest.TestCase):
    def score(self, fixtures):
        script = r'''require $argv[1].'/strategy-picker-core.php';
$docs=json_decode(stream_get_contents(STDIN),true);$scores=[];$out=[];
foreach($docs as $doc){try{$s=NfqwsStrategyPickerScore::measure($doc);$scores[]=$s;$out[]=['score'=>$s];}
catch(Throwable $e){$out[]=['error'=>$e->getMessage()];}}
if(count($scores)===4)$out[]=NfqwsStrategyPickerScore::compare(array_slice($scores,0,2),array_slice($scores,2));
echo json_encode($out);'''
        r = subprocess.run([PHP, '-n', '-r', script, str(PUBLIC)],
                           input=json.dumps(fixtures), text=True, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stderr, '')
        return json.loads(r.stdout)

    def with_dns(self, value):
        f = native_fixture()
        for side in ['before', 'after']:
            f['context'][side]['dns'] = copy.deepcopy(value)
        return f

    def test_unknown_or_malformed_matching_dns_is_not_comparable(self):
        for dns in [None, {'schema_version': 1, 'state': 'unknown', 'sha256': None},
                    {'schema_version': 1, 'state': 'known', 'sha256': None},
                    {'schema_version': 1, 'state': 'known', 'sha256': 'x' * 64},
                    {'schema_version': 2, 'state': 'known', 'sha256': 'a' * 64}]:
            with self.subTest(dns=dns):
                self.assertEqual(self.score([self.with_dns(dns)]), [{'error': 'incomparable_result'}])

    def test_known_dns_changes_between_runs_invalidate_ranking(self):
        a = self.with_dns({'schema_version': 1, 'state': 'known', 'sha256': 'a' * 64})
        b = self.with_dns({'schema_version': 1, 'state': 'known', 'sha256': 'b' * 64})
        got = self.score([a, a, b, b])
        self.assertFalse(got[-1]['eligible'])
        self.assertEqual(got[-1]['reason'], 'incomparable_result')
        self.assertNotEqual(got[0]['score']['context_sha256'], got[2]['score']['context_sha256'])

    def test_missing_dns_on_only_one_side_or_run_does_not_match(self):
        old = native_fixture()
        new = self.with_dns({'schema_version': 1, 'state': 'known', 'sha256': 'a' * 64})
        half = copy.deepcopy(new);del half['context']['after']['dns']
        self.assertEqual(self.score([half]), [{'error': 'incomparable_result'}])
        got = self.score([old, old, new, new])
        self.assertEqual(got[-1]['reason'], 'incomparable_result')

    def test_legacy_reports_without_dns_remain_readable(self):
        self.assertIn('score', self.score([native_fixture()])[0])

    def test_worker_context_contains_only_the_public_dns_identity(self):
        script = "require $argv[1].'/dpi-jobs.php';echo json_encode([AsusDpiWorker::unknownContext(),AsusDpiWorker::context()]);"
        r = subprocess.run([PHP, '-n', '-r', script, str(PUBLIC)], text=True, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stderr, '')
        values = json.loads(r.stdout)
        self.assertEqual(values[0].get('dns'), {'schema_version': 1, 'state': 'unknown', 'sha256': None})
        self.assertEqual(set(values[1]['dns']), {'schema_version', 'state', 'sha256'})
        self.assertIn(values[1]['dns']['state'], ['known', 'unknown'])


if __name__ == '__main__':
    unittest.main()

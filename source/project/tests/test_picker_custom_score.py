"""Per-host HTTPS floors must survive repeated custom-target comparison."""
import copy
import json
import subprocess
import unittest
from test_dpi_normalize import PHP, PUBLIC


class CustomScoreTests(unittest.TestCase):
    def envelope(self, hosts=None):
        hosts = hosts or ['nnmclub.to', 'rutor.info']
        return {'schema_version': 1, 'hosts': hosts, 'dns_context': 'd'*64,
                'fingerprint': 'php-openssl-pinned-https-v1', 'manifest_sha256': 'a'*64,
                'observations': [{'host': h, 'tls': tls, 'response': {
                    'outcome': 'connection_error', 'http_status': None, 'bytes_read': 0,
                    'body_limited': False, 'redirect': None, 'elapsed_ms': None,
                    'error_code': 'connection_failed'}}
                    for h in hosts for tls in ['tls12', 'tls13']]}

    def status(self, doc, cell, status=200, outcome='response'):
        row = doc['observations'][cell]['response']
        row.update(outcome=outcome, http_status=status, body_limited=outcome == 'read_limited',
                   bytes_read=262144 if outcome == 'read_limited' else 0,
                   error_code='body_limit' if outcome == 'read_limited' else None)
        return doc

    def run_php(self, payload):
        code = '''$p=$argv[1].'/strategy-picker-custom-score.php';
if(!is_file($p)){echo json_encode(['error'=>'not_implemented']);exit;}
require $p;$v=json_decode(stream_get_contents(STDIN),true,32,JSON_THROW_ON_ERROR);
try{$scores=[];foreach($v['samples'] as $i=>$sample)$scores[]=NfqwsStrategyPickerCustomScore::measure(
 $sample,$v['contexts'][$i]??str_repeat('c',64),$v['ids'][$i]??str_pad(dechex($i+1),32,'0',STR_PAD_LEFT));
if(isset($v['patch']))foreach($v['patch']as $p){$scores[$p[0]][$p[1]]=$p[2];}
echo json_encode(($v['compare']??false)?NfqwsStrategyPickerCustomScore::compare(
 array_slice($scores,0,2),array_slice($scores,2)):$scores,JSON_THROW_ON_ERROR);
}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        result = subprocess.run([PHP, '-n', '-r', code, str(PUBLIC)],
                                input=json.dumps(payload), capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(result.stderr, '')
        return json.loads(result.stdout)

    def compare(self, docs, **kw):
        return self.run_php({'samples': docs, 'compare': True, **kw})

    def test_http_refusals_redirects_and_incomplete_reads_are_not_access_success(self):
        doc = self.envelope(['nnmclub.to', 'rutor.info', 'rutracker.org', 'tapochek.net', 'example.com'])
        for i, (status, outcome) in enumerate([(200,'response'), (204,'response'),
                (302,'response'), (403,'response'), (404,'response'), (500,'response'),
                (200,'read_limited'), (200,'timeout'), (None,'tls_error'), (304,'response')]):
            self.status(doc, i, status, outcome)
        doc['observations'][2]['response']['redirect'] = 'https://example.com/private?token=secret'
        out = self.run_php({'samples': [doc]})
        self.assertIsInstance(out, list, out)
        self.assertEqual([r['root_ok'] for r in out[0]['cells']],
                         [True, True, False, False, False, False, True, False, False, False])
        self.assertEqual([r['responded'] for r in out[0]['cells']],
                         [True, True, True, True, True, True, True, False, False, True])
        self.assertNotIn('secret', json.dumps(out))
        self.assertNotIn('redirect', json.dumps(out))
        self.assertEqual(out[0]['probe_fingerprint'], 'php-openssl-pinned-https-v1')

    def test_only_the_worst_complete_repeat_counts_toward_gain(self):
        a, b, c, d = [self.envelope() for _ in range(4)]
        for i in [0, 1]: self.status(c, i)
        self.status(d, 0)
        out = self.compare([a, b, c, d])
        self.assertTrue(out.get('eligible'), out)
        self.assertEqual((out['reason'], out['gain']), ('improved', 1))
        self.assertEqual(out['minimum']['root_ok'], {'ok': 1, 'total': 4})
        self.assertEqual(out['minimum']['responded'], {'ok': 1, 'total': 4})
        self.assertEqual([r['root_ok'] for r in out['minimum']['cells']], [True, False, False, False])

    def test_another_host_or_tls_mode_cannot_pay_for_a_regression(self):
        for lost, gained in [(0, [2, 3]), (0, [1])]:
            with self.subTest(lost=lost, gained=gained):
                a, b, c, d = [self.envelope() for _ in range(4)]
                self.status(a, lost); self.status(b, lost)
                for i in gained: self.status(c, i); self.status(d, i)
                out = self.compare([a, b, c, d])
                self.assertEqual(out, {'eligible': False, 'reason': 'custom_regression', 'gain': 0})

    def test_refusal_is_not_a_gain_but_losing_a_response_is_a_regression(self):
        for code in [301, 302, 403, 404, 429, 500]:
            with self.subTest(code=code):
                docs = [self.envelope() for _ in range(4)]
                self.status(docs[2], 0, code); self.status(docs[3], 0, code)
                out = self.compare(docs)
                self.assertFalse(out.get('eligible'), out)
                self.assertEqual((out.get('reason'), out.get('gain')), ('no_improvement', 0))
        docs = [self.envelope() for _ in range(4)]
        self.status(docs[0], 0, 403); self.status(docs[1], 0, 403)
        self.status(docs[2], 2); self.status(docs[3], 2)
        self.assertEqual(self.compare(docs).get('reason'), 'custom_regression')

    def test_changed_dns_pins_context_or_target_coverage_cannot_be_compared(self):
        for field in ['dns_context', 'manifest_sha256', 'hosts', 'context']:
            with self.subTest(field=field):
                docs = [self.envelope() for _ in range(4)]
                kw = {}
                if field == 'hosts': docs[3] = self.envelope(['rutor.info', 'nnmclub.to'])
                elif field == 'context': kw['contexts'] = ['c'*64]*3+['f'*64]
                else: docs[3][field] = 'f'*64
                self.assertEqual(self.compare(docs, **kw),
                                 {'eligible': False, 'reason': 'incomparable_result', 'gain': 0})

    def test_complete_schema_and_order_are_required_before_scoring(self):
        invalid = []
        d = self.envelope(); d['observations'].pop(); invalid.append(d)
        d = self.envelope(); d['observations'].reverse(); invalid.append(d)
        d = self.envelope(); d['observations'][1] = copy.deepcopy(d['observations'][0]); invalid.append(d)
        d = self.envelope(); d['fingerprint'] = 'rustls'; invalid.append(d)
        d = self.envelope(); d['schema_version'] = True; invalid.append(d)
        d = self.envelope(); d['extra'] = 'ignored'; invalid.append(d)
        d = self.envelope(); d['hosts'] = ['NNMCLUB.TO', 'rutor.info']; invalid.append(d)
        d = self.envelope(); d['observations'][0]['response']['bytes_read'] = '0'; invalid.append(d)
        d = self.envelope(); self.status(d, 0, 200, 'read_limited'); d['observations'][0]['response']['body_limited'] = False; invalid.append(d)
        invalid.append(self.envelope([f'site{i}.example.com' for i in range(11)]))
        for i, doc in enumerate(invalid):
            with self.subTest(i=i):
                self.assertEqual(self.run_php({'samples': [doc]}), {'error': 'incomparable_result'})

    def test_reusing_a_sample_or_malformed_compact_scores_cannot_rank(self):
        docs = [self.envelope() for _ in range(4)]
        self.assertEqual(self.compare(docs, ids=['1'*32]*4),
                         {'eligible': False, 'reason': 'incomparable_result', 'gain': 0})
        for field, value in [('cells', []), ('targets', 'a'*64), ('sample_sha256', None),
                             ('fingerprint', 'native-score'), ('unknown', True)]:
            with self.subTest(field=field):
                self.assertEqual(self.compare(docs, patch=[[3, field, value]]),
                                 {'eligible': False, 'reason': 'incomparable_result', 'gain': 0})
        scores = self.run_php({'samples': [self.status(self.envelope(), 0, 403)]})
        self.assertIsInstance(scores, list, scores)
        cells = scores[0]['cells']; cells[0]['root_ok'] = True
        self.assertEqual(self.compare(docs, patch=[[3, 'cells', cells]]),
                         {'eligible': False, 'reason': 'incomparable_result', 'gain': 0})

    def test_identical_observations_are_allowed_for_distinct_real_sample_ids(self):
        out = self.compare([self.envelope() for _ in range(4)])
        self.assertEqual(out.get('reason'), 'no_improvement', out)
        self.assertEqual(out['minimum']['root_ok'], {'ok': 0, 'total': 4})
        self.assertEqual(self.compare([self.envelope() for _ in range(3)])['reason'], 'incomparable_result')

    def test_bad_parent_binding_is_rejected_even_with_valid_observations(self):
        for extra in [{'contexts': ['unknown']}, {'ids': ['not-a-trusted-sample-id']}]:
            self.assertEqual(self.run_php({'samples': [self.envelope()], **extra}),
                             {'error': 'incomparable_result'})

    def test_inconsistent_success_details_cannot_be_discarded_before_scoring(self):
        for outcome, patch in [('read_limited', {'bytes_read': 0}),
                ('read_limited', {'bytes_read': 262143}), ('read_limited', {'error_code': None}),
                ('response', {'error_code': 'incomplete_body'}),
                ('response', {'error_code': 'body_limit'})]:
            with self.subTest(outcome=outcome, patch=patch):
                doc = self.status(self.envelope(), 0, 200, outcome)
                doc['observations'][0]['response'].update(patch)
                self.assertEqual(self.run_php({'samples': [doc]}), {'error': 'incomparable_result'})


if __name__ == '__main__': unittest.main()

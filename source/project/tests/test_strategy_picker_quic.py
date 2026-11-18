"""Score the pinned Detector's native QUIC statuses, without network probes."""
import copy
import json
import subprocess
import unittest

from test_dpi_normalize import PHP, PUBLIC


# Native alpha.21 DomainRow/Report fields and status/detail pairs, not display
# badges. Public fixture addresses are documentation-only; no probe is run.
# Upstream a09d03b: crates/dpi-core/src/probe/quic.rs and
# crates/dpi-detector/src/json.rs. QUIC success describes an Initial response,
# not a completed HTTP/3 request or an application's media/P2P traffic.
DOMAIN_ROWS = [
    {
        'domain': host,
        'resolved': '203.0.113.1',
        'http': 'ok',
        'http_detail': 'http_200',
        'tls12': 'ok',
        'tls12_detail': '',
        'tls13': 'ok',
        'tls13_detail': '',
        'quic': status,
        'quic_detail': detail,
    }
    for host, status, detail in [
        ('www.youtube.com', 'quic_ok', 'quic_server_hello'),
        ('nnmclub.to', 'quic_ok', 'quic_server_hello'),
        ('rutracker.org', 'quic_ok', 'quic_server_hello'),
        ('rutor.info', 'quic_unsupported', ''),
        ('tapochek.net', 'quic_unsupported', ''),
    ]
]


def native_fixture():
    def report(key, rows):
        return {
            'schema_version': 1,
            'version': '5.0.0-alpha.21',
            'profile': 'ru',
            'tls_fingerprint': 'chrome146',
            'results': {key: rows},
        }

    context = {'nfqws': 'running', 'ark': 'absent', 'tun_observed': False}
    return {
        'state': 'completed',
        'coverage': {'domains': 5, 'tcp': 1},
        'context': {'before': context, 'after': copy.deepcopy(context), 'changed': False},
        'groups': [
            {'group': 2, 'document': report('domain_inspection', copy.deepcopy(DOMAIN_ROWS))},
            {'group': 3, 'document': report('tcp16', [
                {'id': 'TEST-01', 'asn': '0', 'provider': 'Fixture',
                 'status': 'timeout', 'detail': 'tcp_syn_timeout'},
            ])},
        ],
    }


def domain(fixture, host):
    return next(row for row in fixture['groups'][0]['document']['results']['domain_inspection']
                if row['domain'] == host)


class PickerNativeQuicTests(unittest.TestCase):
    def evaluate(self, *fixtures, goal=None):
        code = r'''
require $argv[1].'/strategy-picker-core.php';
require $argv[1].'/dpi-native.php';
$input=json_decode(stream_get_contents(STDIN),true,32,JSON_THROW_ON_ERROR);
$scores=[];
foreach($input['fixtures'] as $native){
    $groups=[];
    foreach($native['groups'] as $group){
        $groups[]=AsusDpiNative::group(json_encode($group['document']),$group['group']);
    }
    $native['groups']=$groups;
    $scores[]=NfqwsStrategyPickerScore::measure($native);
}
$out=['scores'=>$scores];
if($input['goal']!==null){
    $out['comparison']=NfqwsStrategyPickerScore::compare(
        array_slice($scores,0,2),array_slice($scores,2,2),$input['goal']);
}
echo json_encode($out,JSON_THROW_ON_ERROR);
'''
        run = subprocess.run(
            [PHP, '-n', '-r', code, str(PUBLIC)],
            input=json.dumps({'fixtures': fixtures, 'goal': goal}),
            capture_output=True, text=True,
        )
        self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
        self.assertEqual(run.stderr, '')
        return json.loads(run.stdout)

    def test_native_quic_success_reaches_counts_domains_services_and_youtube(self):
        score = self.evaluate(native_fixture())['scores'][0]
        self.assertEqual(score['metrics']['quic'], {'ok': 3, 'total': 3})
        self.assertEqual(score['services']['torrents']['quic'], {'ok': 2, 'total': 2})
        self.assertTrue(score['youtube']['quic'])
        self.assertTrue(score['domains']['nnmclub.to']['quic'])
        self.assertTrue(score['domains']['rutracker.org']['quic'])

    def test_repeated_quic_only_improvement_is_ranked(self):
        baseline, candidate = native_fixture(), native_fixture()
        domain(baseline, 'nnmclub.to').update(quic='quic_drop', quic_detail='quic_timeout')
        result = self.evaluate(baseline, baseline, candidate, candidate, goal='torrents')['comparison']
        self.assertTrue(result['eligible'])
        self.assertEqual(result['gain'], 1)

    def test_youtube_quic_regression_cannot_win_by_tcp_gain(self):
        baseline, candidate = native_fixture(), native_fixture()
        domain(candidate, 'www.youtube.com').update(quic='quic_drop', quic_detail='quic_timeout')
        candidate['groups'][1]['document']['results']['tcp16'][0].update(status='ok', detail='')
        result = self.evaluate(baseline, baseline, candidate, candidate, goal='all')['comparison']
        self.assertEqual(result['reason'], 'youtube_regression')
        self.assertFalse(result['eligible'])

    def test_one_failed_repeat_of_selected_tracker_quic_cannot_win_by_http_gain(self):
        baseline, candidate = native_fixture(), native_fixture()
        domain(baseline, 'nnmclub.to').update(http='timeout', http_detail='tcp_syn_timeout')
        regressed = copy.deepcopy(candidate)
        domain(regressed, 'nnmclub.to').update(quic='quic_drop', quic_detail='quic_timeout')
        result = self.evaluate(baseline, baseline, candidate, regressed, goal='torrents')['comparison']
        self.assertEqual(result['reason'], 'goal_regression')
        self.assertFalse(result['eligible'])

    def test_authenticated_retry_and_existing_literal_ok_remain_successful(self):
        for status, detail in [('quic_ok', 'quic_retry'), ('ok', '')]:
            with self.subTest(status=status, detail=detail):
                fixture = native_fixture()
                domain(fixture, 'nnmclub.to').update(quic=status, quic_detail=detail)
                domain(fixture, 'rutracker.org').update(quic='quic_unsupported', quic_detail='')
                score = self.evaluate(fixture)['scores'][0]
                self.assertTrue(score['domains']['nnmclub.to']['quic'])
                self.assertEqual(score['services']['torrents']['quic'], {'ok': 1, 'total': 1})

    def test_other_quic_statuses_and_success_like_details_do_not_pass(self):
        cases = [
            ('quic_closed', 'quic_close_296'),
            ('quic_closed', 'quic_stateless_reset'),
            ('quic_vn', 'quic_version_negotiation'),
            ('quic_spoof', 'quic_forged_retry'),
            ('quic_drop', 'quic_timeout'),
            ('refused', 'quic_port_unreachable'),
            ('timeout', 'quic_timeout'),
            ('unknown', ''),
            ('quic_closed', 'quic_server_hello'),
            ('unknown', 'quic_retry'),
        ]
        for status, detail in cases:
            with self.subTest(status=status, detail=detail):
                fixture = native_fixture()
                domain(fixture, 'nnmclub.to').update(quic=status, quic_detail=detail)
                domain(fixture, 'rutracker.org').update(quic='quic_unsupported', quic_detail='')
                score = self.evaluate(fixture)['scores'][0]
                self.assertFalse(score['domains']['nnmclub.to']['quic'])
                self.assertEqual(score['services']['torrents']['quic'], {'ok': 0, 'total': 1})

    def test_quic_ok_token_does_not_spoof_http_or_tls_success(self):
        for protocol in ['http', 'tls12', 'tls13']:
            with self.subTest(protocol=protocol):
                fixture = native_fixture()
                row = domain(fixture, 'www.youtube.com')
                row[protocol] = 'quic_ok'
                row[protocol + '_detail'] = 'quic_server_hello'
                score = self.evaluate(fixture)['scores'][0]
                self.assertFalse(score['youtube'][protocol])
                self.assertFalse(score['domains']['www.youtube.com'][protocol])
                self.assertEqual(score['services']['youtube'][protocol], {'ok': 0, 'total': 1})

    def test_unsupported_keeps_null_domain_and_original_denominator_policy(self):
        for status in ['quic_unsupported', 'unsupported', 'not_supported', 'skipped']:
            with self.subTest(status=status):
                fixture = native_fixture()
                domain(fixture, 'nnmclub.to').update(quic=status, quic_detail='')
                score = self.evaluate(fixture)['scores'][0]
                self.assertIsNone(score['domains']['nnmclub.to']['quic'])
                self.assertEqual(score['metrics']['quic']['total'], 2)
                self.assertEqual(score['services']['torrents']['quic']['total'], 1)


if __name__ == '__main__':
    unittest.main()

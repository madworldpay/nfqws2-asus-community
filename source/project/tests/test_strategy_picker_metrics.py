import json
import subprocess
import unittest
from pathlib import Path
from test_dpi_normalize import PHP


PUBLIC = Path(__file__).resolve().parents[1] / 'webui/web/public'


class StrategyPickerMetricsTests(unittest.TestCase):
    def sample(self, stat='cpu  100 20 30 400 50 6 7 8 90 10\n',
               memory='MemTotal: 131072 kB\nMemAvailable: 70000 kB\n',
               uptime='123.45 0.0\n', boot='12345678-1234-1234-1234-123456789abc\n', sensors=None):
        data = dict(stat=stat, memory=memory, uptime=uptime, boot=boot, sensors=sensors or [])
        code = '''require $argv[1].'/strategy-picker-metrics.php';
        $v=json_decode(stream_get_contents(STDIN),true,512,JSON_THROW_ON_ERROR);
        echo json_encode(NfqwsStrategyPickerMetrics::decode($v['stat'],$v['memory'],$v['uptime'],$v['boot'],$v['sensors']),JSON_THROW_ON_ERROR);'''
        result = subprocess.run([PHP, '-n', '-r', code, str(PUBLIC)], input=json.dumps(data),
                                text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        return json.loads(result.stdout)

    def test_cpu_snapshot_excludes_guest_fields_without_32_bit_overflow(self):
        value = self.sample(stat='cpu  4294967297 20 30 400 50 6 7 8 90 10\ncpu0 1 1 1 1\n')
        self.assertEqual(value['cpu_counters'], [4294967297, 20, 30, 400, 50, 6, 7, 8])
        self.assertEqual(value['uptime_seconds'], 123.45)
        self.assertRegex(value['boot'], r'^[a-f0-9]{64}$')

    def test_memavailable_is_actual_not_memfree_or_load_average(self):
        value = self.sample(memory='MemTotal: 131072 kB\nMemFree: 1000 kB\nBuffers: 2000 kB\nCached: 3000 kB\nMemAvailable: 70000 kB\n')
        self.assertEqual(value['memory'], dict(total_kib=131072, available_kib=70000, used_kib=61072, estimated=False))

    def test_legacy_estimate_is_explicit_and_does_not_invent_missing_counters(self):
        value = self.sample(memory='MemTotal: 131072 kB\nMemFree: 1000 kB\nBuffers: 2000 kB\nCached: 3000 kB\n')
        self.assertEqual(value['memory'], dict(total_kib=131072, available_kib=6000, used_kib=125072, estimated=True))
        self.assertIsNone(self.sample(memory='MemTotal: 131072 kB\nMemFree: 1000 kB\n')['memory'])

    def test_invalid_memory_does_not_hide_valid_cpu_and_zero_available_is_valid(self):
        for raw in ['MemTotal: 131072 kB\nMemAvailable: 131073 kB\n', '',
                    'MemTotal: 0 kB\nMemAvailable: 0 kB\n',
                    'MemTotal: 131072 kB\nMemAvailable: -1 kB\n',
                    'MemTotal: 131072 kB\nMemAvailable: 123 kB\nMemAvailable: 124 kB\n']:
            with self.subTest(raw=raw):
                value = self.sample(memory=raw)
                self.assertIsNone(value['memory'])
                self.assertIsNotNone(value['cpu_counters'])
        self.assertEqual(self.sample(memory='MemTotal: 131072 kB\nMemAvailable: 0 kB\n')['memory']['available_kib'], 0)

    def test_missing_or_malformed_cpu_is_unknown_not_zero(self):
        for raw in ['', 'cpu0 1 2 3 4\n', 'cpu 1 2 3\n', 'cpu 1 -2 3 4\n',
                    'cpu 9007199254740992 2 3 4\n', 'cpu 1 2 nan 4\n']:
            with self.subTest(raw=raw):
                self.assertIsNone(self.sample(stat=raw)['cpu_counters'])
        self.assertEqual(self.sample(stat='cpu 1 2 3 4\n')['cpu_counters'], [1, 2, 3, 4, 0, 0, 0, 0])

    def test_temperature_keeps_actual_sensor_identity_and_rejects_radio_or_unknown(self):
        value = self.sample(sensors=[dict(type='wifi', temp='80000'), dict(type='cpu-thermal', temp='62500'),
                                    dict(type='soc_thermal', temp='44000'), dict(type='mystery', temp='12000'),
                                    dict(type='cpu', temp='999999999')])
        self.assertEqual(value['temperatures'], [dict(sensor='cpu-thermal', kind='cpu', celsius=62.5),
                                                dict(sensor='soc_thermal', kind='soc', celsius=44)])
        self.assertEqual(self.sample(sensors=[dict(type='x86_pkg_temp', temp='-5000')])['temperatures'],
                         [dict(sensor='x86_pkg_temp', kind='cpu', celsius=-5)])

    def test_missing_boot_or_uptime_prevents_ambiguous_cpu_comparisons(self):
        self.assertIsNone(self.sample(boot='')['boot'])
        self.assertIsNone(self.sample(boot='not-a-boot-id')['boot'])
        for uptime in ['', '-1 0', 'NaN 0', '123x 0']:
            self.assertIsNone(self.sample(uptime=uptime)['uptime_seconds'])

    def test_real_sampler_exposes_only_bounded_numeric_telemetry(self):
        result = subprocess.run([PHP, '-n', '-r', "require $argv[1].'/strategy-picker-metrics.php';echo json_encode(NfqwsStrategyPickerMetrics::sample(),JSON_THROW_ON_ERROR);", str(PUBLIC)],
                                text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        value = json.loads(result.stdout)
        self.assertEqual(set(value), {'boot', 'uptime_seconds', 'cpu_counters', 'memory', 'temperatures'})
        self.assertLess(len(result.stdout), 4096)
        self.assertGreater(value['uptime_seconds'], 0)
        self.assertGreater(value['memory']['total_kib'], 0)
        self.assertEqual(len(value['cpu_counters']), 8)
        self.assertLessEqual(len(value['temperatures']), 16)


if __name__ == '__main__':
    unittest.main()

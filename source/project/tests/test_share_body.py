"""Mail previews describe only metadata present in validated selected exports."""
import base64
import json
import unittest

from test_share_relay import SOURCE, encode, fixture as fixture_v3
from test_share_v4 import file, fixture as fixture_v4
from nfqws_support.share import share_body, validate_share


def document(envelope, kind):
    entry = next(entry for entry in envelope['files'] if entry['type'] == kind)
    return json.loads(base64.b64decode(entry['data_base64']))


def replace_document(envelope, kind, value):
    index = next(index for index, entry in enumerate(envelope['files']) if entry['type'] == kind)
    envelope['files'][index] = file(kind, value)


class ShareBodyTests(unittest.TestCase):
    def body(self, envelope):
        bundle = validate_share(encode(envelope), envelope['submission_id'])
        return share_body(bundle)

    def preview_and_metadata(self, envelope):
        body = self.body(envelope)
        self.assertIn('\n\n', body, 'A readable preview must precede the original JSON metadata')
        return body.split('\n\n', 1)

    def test_v3_preview_uses_export_purpose_without_inventing_services(self):
        envelope = fixture_v3(('strategy',), source=SOURCE)
        strategy = document(envelope, 'strategy')
        strategy.update(operator='Билайн', purpose='Билайн МСК01', comment='Только название профиля')
        replace_document(envelope, 'strategy', strategy)

        preview, metadata = self.preview_and_metadata(envelope)

        self.assertEqual(preview.splitlines(), [
            'Модель: GT-BE19000AI',
            'Оператор: Билайн',
            'Сервисы / назначение: Билайн МСК01',
        ])
        self.assertEqual(json.loads(metadata), {
            'type': 'nfqws2_submission', 'schema_version': 1,
            'submission_id': envelope['submission_id'],
            'categories': ['strategies'], 'source': SOURCE,
        })
        self.assertNotIn('Только название профиля', preview)

    def test_v4_uses_each_selected_context_without_requiring_strategy(self):
        for kinds in [('strategy',), ('resources',), ('dns',), ('strategy', 'resources', 'dns')]:
            with self.subTest(kinds=kinds):
                envelope = fixture_v4(kinds)
                envelope['source'] = SOURCE
                for kind in kinds:
                    value = document(envelope, kind)
                    context = value if kind == 'strategy' else value['context']
                    context.update(operator='Example ISP', purpose='YouTube, Discord')
                    if kind == 'strategy' and 'resources' not in kinds:
                        value['dependencies'][0]['included'] = False
                    replace_document(envelope, kind, value)
                preview, metadata = self.preview_and_metadata(envelope)
                self.assertEqual(preview.splitlines(), [
                    'Модель: GT-BE19000AI',
                    'Оператор: Example ISP',
                    'Сервисы / назначение: YouTube, Discord',
                ])
                self.assertEqual(json.loads(metadata)['categories'], ['strategies'])

    def test_diagnostics_only_uses_report_model_and_marks_missing_context(self):
        for kinds, source, model in [
            (('report',), None, 'GT-BE19000AI'),
            (('dpi',), SOURCE, 'GT-BE19000AI'),
            (('dpi',), None, 'нет данных в экспорте'),
            (('strategy',), None, 'нет данных в экспорте'),
        ]:
            with self.subTest(kinds=kinds, source=source):
                lines = self.body(fixture_v3(kinds, source=source)).splitlines()
                self.assertEqual(lines[0], 'Модель: ' + model)
                if kinds != ('strategy',):
                    self.assertEqual(lines[1:3], [
                        'Оператор: нет данных в экспорте',
                        'Сервисы / назначение: нет данных в экспорте',
                    ])

    def test_conflicting_contexts_are_labelled_instead_of_silently_choosing_one(self):
        envelope = fixture_v4()
        contexts = {
            'strategy': ('ISP A', 'YouTube'),
            'resources': ('ISP B', 'Discord'),
            'dns': ('ISP C', 'DNS profile'),
        }
        for kind, (operator, purpose) in contexts.items():
            value = document(envelope, kind)
            context = value if kind == 'strategy' else value['context']
            context.update(operator=operator, purpose=purpose)
            replace_document(envelope, kind, value)

        lines = self.body(envelope).splitlines()

        self.assertEqual(lines[1], 'Оператор: различаются: стратегия: ISP A; ресурсы: ISP B; DNS: ISP C')
        self.assertEqual(lines[2], 'Сервисы / назначение: различаются: стратегия: YouTube; ресурсы: Discord; DNS: DNS profile')

    def test_conflicting_source_and_report_models_are_both_visible(self):
        envelope = fixture_v3(('report',), source=SOURCE | {'model': 'RT-AX88U'})
        self.assertEqual(self.body(envelope).splitlines()[0],
                         'Модель: различаются: источник: RT-AX88U; диагностика: GT-BE19000AI')

    def test_header_whitespace_and_controls_cannot_forge_extra_preview_lines(self):
        envelope = fixture_v3(('strategy',), source=SOURCE)
        strategy = document(envelope, 'strategy')
        strategy.update(operator='  Билайн\r\n\tМСК\x00\x7f\u202e  ',
                        purpose='YouTube\u2028 Discord\u200b\x85')
        replace_document(envelope, 'strategy', strategy)

        preview, metadata = self.preview_and_metadata(envelope)

        self.assertEqual(preview.splitlines(), [
            'Модель: GT-BE19000AI', 'Оператор: Билайн МСК',
            'Сервисы / назначение: YouTube Discord',
        ])
        self.assertEqual(json.loads(metadata)['source'], SOURCE)

    def test_control_only_headers_use_missing_data_fallback(self):
        envelope = fixture_v3(('strategy',))
        strategy = document(envelope, 'strategy')
        strategy.update(operator='\x00\u202e', purpose='\x7f\u200b')
        replace_document(envelope, 'strategy', strategy)
        self.assertEqual(self.body(envelope).splitlines()[1:3], [
            'Оператор: нет данных в экспорте',
            'Сервисы / назначение: нет данных в экспорте',
        ])

    def test_maximum_distinct_contexts_keep_each_preview_line_bounded(self):
        envelope = fixture_v4()
        for index, kind in enumerate(('strategy', 'resources', 'dns')):
            value = document(envelope, kind)
            context = value if kind == 'strategy' else value['context']
            context.update(operator=str(index) * 120, purpose=str(index) * 120)
            replace_document(envelope, kind, value)
        lines = self.body(envelope).splitlines()
        for line in lines[:3]:
            self.assertLessEqual(len(line), 440)
        self.assertIn('стратегия:', lines[1])
        self.assertIn('ресурсы:', lines[1])
        self.assertIn('DNS:', lines[1])


if __name__ == '__main__':
    unittest.main()

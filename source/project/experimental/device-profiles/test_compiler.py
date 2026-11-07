import unittest
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path

HERE=Path(__file__).resolve().parent


class CompilerTests(unittest.TestCase):
    def load(self):
        path=HERE/'compile_probe.py'
        self.assertTrue(path.is_file(), 'native profile compiler is missing')
        spec=spec_from_file_location('compile_probe',path);module=module_from_spec(spec);spec.loader.exec_module(module)
        return module

    def test_every_internal_block_gets_own_nonzero_mark_and_fallback_is_last(self):
        m=self.load();a={'NFQWS_BASE_ARGS':'--lua-init=@/base.lua --blob=tls:@/tls.bin',
          'NFQWS_ARGS':'--filter-tcp=443 --lua-desync=a --new=inside --filter-tcp=80 --lua-desync=b'}
        b={'NFQWS_BASE_ARGS':'--lua-init=@/base.lua --blob=tls:@/tls.bin','NFQWS_ARGS':'--filter-tcp=443 --lua-desync=c'}
        result=m.compile_probe([('first',a),('second',b)],a)
        self.assertEqual(result.count('--lua-init=@/base.lua'),1)
        self.assertEqual(result.count('--blob=tls:@/tls.bin'),1)
        self.assertIn('--name=first-1',result, 'first profile must not leave a catch-all empty profile before it')
        blocks=m.blocks(result[result.index('--name=first-1'):])
        self.assertIn('--filter-mark=0x00010000/0x00010000',blocks[0])
        self.assertIn('--filter-mark=0x00010000/0x00010000',blocks[1])
        self.assertIn('--filter-mark=0x00020000/0x00020000',blocks[2])
        self.assertFalse(any(x.startswith('--filter-mark') for x in blocks[-1]))
        self.assertTrue(blocks[-1][0].startswith('--new=fallback-'))

    def test_conflicting_blob_definitions_and_existing_marks_are_rejected(self):
        m=self.load();a={'NFQWS_BASE_ARGS':'--blob=tls:@/a.bin','NFQWS_ARGS':'--filter-tcp=443'}
        b={'NFQWS_BASE_ARGS':'--blob=tls:@/b.bin','NFQWS_ARGS':'--filter-tcp=443'}
        with self.assertRaisesRegex(ValueError,'conflicting_global'):m.compile_probe([('a',a)],b)
        a['NFQWS_ARGS']='--filter-mark=1 --filter-tcp=443'
        with self.assertRaisesRegex(ValueError,'existing_mark'):m.compile_probe([('a',a)],a)

    def test_structural_abbreviations_cannot_reset_profile_boundaries_or_marks(self):
        m=self.load()
        for flag in ['--filter-mar=0/0','--ne=escape','--na=escape','--bl=tls:@/b.bin','--lua-ini=@/b.lua']:
            with self.subTest(flag=flag),self.assertRaises(ValueError):
                a={'NFQWS_ARGS':'--filter-tcp=443 '+flag};m.compile_probe([('a',a)],a)

    def test_packaged_comment_lines_are_not_engine_arguments(self):
        m=self.load();a={'NFQWS_ARGS':'# HTTPS\n--filter-tcp=443\n# Strategy 2 --new=not-a-profile\n--lua-desync=a'}
        result=m.compile_probe([('a',a)],a)
        self.assertNotIn('#',result)
        self.assertEqual(sum(x.startswith('--filter-mark=') for x in result),1)

    def test_reserved_process_flags_cannot_be_hidden_in_strategy(self):
        m=self.load()
        for flag in ['--qnum=300','--daemon','--pidfile=/tmp/a','@/evil','--lua-init=execute()']:
            with self.subTest(flag=flag),self.assertRaises(ValueError):
                a={'NFQWS_ARGS':'--filter-tcp=443 '+flag};m.compile_probe([('a',a)],a)


if __name__=='__main__':unittest.main()

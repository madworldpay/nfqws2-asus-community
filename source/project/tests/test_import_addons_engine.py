"""Use the actual init assembly and pinned C matcher to prove safe scope unions."""
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
import test_import_addons as fixtures

ROOT=Path(__file__).resolve().parents[1]
SOURCES=ROOT.parent/'sources'
CACHED=all((SOURCES/name).is_file() for name in ['zapret2-038c97e5.tar.gz','lua-5.5.1.tar.gz','zlib-1.3.2.tar.gz'])


@unittest.skipUnless(shutil.which('gcc') and CACHED,'requires compiler and pinned cached source headers')
class ImportAddonCoreScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='addon-hostlist-core-');cls.addClassCleanup(cls.tmp.cleanup)
        cls.root=Path(cls.tmp.name)
        for name in ['zapret2-038c97e5.tar.gz','lua-5.5.1.tar.gz','zlib-1.3.2.tar.gz']:
            with tarfile.open(SOURCES/name) as archive:
                members=[m for m in archive.getmembers() if m.isfile() and (m.name.endswith('.h') or m.name.endswith('/hostlist.c') or m.name.endswith('/pools.c'))]
                archive.extractall(cls.root,members=members,filter='data')
        nfq=next(cls.root.glob('zapret2-*/nfq2'));lua=next(cls.root.glob('lua-*/src'));zlib=next(cls.root.glob('zlib-*'))
        cap=cls.root/'include/sys';cap.mkdir(parents=True);(cap/'capability.h').write_text('#include <linux/capability.h>\n')
        cls.binary=cls.root/'hostlist-probe'
        result=subprocess.run(['gcc','-O2','-ffunction-sections','-fdata-sections','-Wl,--gc-sections','-iquote',str(nfq),'-I'+str(lua),'-I'+str(zlib),'-I'+str(cls.root/'include'),str(ROOT/'tests/fixtures/import_addons_hostlist.c'),str(nfq/'hostlist.c'),str(nfq/'pools.c'),'-o',str(cls.binary)],capture_output=True,text=True)
        if result.returncode:raise AssertionError(result.stdout+result.stderr)

    def startup(self, plan):
        with tempfile.NamedTemporaryFile(mode='w') as config:
            config.write(plan['config']);config.flush()
            # Source only the generated literal config and fixed core functions.
            script='CONFFILE=$2; . "$1"; set -- $(_startup_args); printf \'%s\\0\' "$@"'
            result=subprocess.run(['sh','-c',script,'fixture',str(ROOT/'core/etc/init.d/common'),config.name],env=os.environ|{'USER':'nobody','NFQUEUE_NUM':'200','LOG_LEVEL':'0','ISP_INTERFACE':'eth0'},capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            return result.stdout.rstrip('\0').split('\0')

    def matches(self, args, host):
        result=subprocess.run([str(self.binary),host,*args],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        return [line.split(':')[1]=='1' for line in result.stdout.splitlines()]

    def test_current_inner_quotes_are_literal_core_bytes_and_cannot_prove_coverage(self):
        current=fixtures.CURRENT.replace('NFQWS_EXTRA_ARGS=""',"NFQWS_EXTRA_ARGS=\"--hostlist-domains='riotgames.com,riotcdn.net'\"")
        before=fixtures.ImportAddonTests().plan(current=current,options=[],omit_shared=True)
        self.assertTrue(before.get('ready'),before)
        self.assertEqual(self.matches(self.startup(before),'riotgames.com'),[False])
        after=fixtures.ImportAddonTests().plan(current=current,omit_shared=True)
        self.assertFalse(after.get('ready'),after)

    def test_real_union_keeps_old_domain_accepts_new_and_honors_exclusions(self):
        plan=fixtures.ImportAddonTests().plan(extra='--hostlist-exclude-domains=riotcdn.net')
        self.assertTrue(plan.get('ready'),plan);args=self.startup(plan)
        self.assertEqual(self.matches(args,'base.example.org'),[True])
        self.assertEqual(self.matches(args,'riotgames.com'),[True])
        self.assertEqual(self.matches(args,'riotcdn.net'),[False])
        self.assertEqual(self.matches(args,'unrelated.example.net'),[False])

    def test_actual_custom_main_and_ipset_profiles_keep_every_former_acceptance(self):
        cases=[({'NFQWS_ARGS_QUIC':'--filter-udp=443 --hostlist-domains=quic.example.org'},fixtures.CURRENT.replace('NFQWS_ARGS="--filter-tcp=80"','NFQWS_ARGS=""')),
               ({'NFQWS_ARGS_CUSTOM':'--filter-tcp=443 --hostlist-domains=base.example.org --new --filter-tcp=80'},fixtures.CURRENT),
               ({'NFQWS_ARGS':fixtures.SCOPED},fixtures.CURRENT+'NFQWS_ARGS_IPSET="--ipset-ip=192.0.2.0/24"\n')]
        for blocks,current in cases:
            with self.subTest(blocks=blocks):
                before=fixtures.ImportAddonTests().plan(blocks=blocks,current=current,options=[])
                after=fixtures.ImportAddonTests().plan(blocks=blocks,current=current)
                self.assertTrue(before.get('ready'),before);self.assertTrue(after.get('ready'),after)
                old=self.startup(before);new=self.startup(after)
                for host in ['base.example.org','quic.example.org','unrelated.example.net','riotgames.com']:
                    old_matches=self.matches(old,host);new_matches=self.matches(new,host)
                    self.assertEqual(len(old_matches),len(new_matches))
                    for was,now in zip(old_matches,new_matches):
                        self.assertFalse(was and not now,(blocks,host,old_matches,new_matches))

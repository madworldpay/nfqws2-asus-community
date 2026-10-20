"""Saved originals must not expose arbitrary files or change reviewed bytes."""
import json, os, subprocess, tempfile, unittest
import resource,signal
from pathlib import Path
from test_dpi_normalize import PHP, PUBLIC

NAME = 'dpi_detector_results-20261016-130000.txt'

class DpiSavedStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.source = self.base/'native'; self.source.mkdir()
        self.root = self.base/'private'

    def call(self, body, limited=False):
        code = '''require $argv[1].'/dpi-saved-store.php';
        try {$s=new AsusDpiSavedStore($argv[2],$argv[3],(int)$argv[4]);
        '''+body+''' }catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        def limit():
            signal.signal(signal.SIGXFSZ,signal.SIG_IGN);resource.setrlimit(resource.RLIMIT_FSIZE,(100,100))
        p = subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(self.root),str(self.source),str(os.getuid())],capture_output=True,text=True,preexec_fn=limit if limited else None)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        self.assertEqual(p.stderr,'')
        return json.loads(p.stdout)

    def saved(self, name=NAME, text='Original <report>\n'):
        p=self.source/name; p.write_text(text); p.chmod(0o600); return p

    def test_index_failure_rolls_back_import_and_does_not_destroy_existing_report(self):
        self.call('echo json_encode($s->list());');p=self.saved(text='small original\n')
        for _ in range(2):
            self.assertIn('error',self.call('echo json_encode($s->refresh());',limited=True))
            self.assertEqual(list(self.root.glob('*.txt')),[])
        report=self.call('echo json_encode($s->refresh());')['reports'][0]
        self.assertIn('error',self.call(f'$s->delete("{report["id"]}");echo "null";',limited=True))
        self.assertEqual(p.read_text(),'small original\n')
        self.assertEqual(self.call(f'echo json_encode($s->read("{report["id"]}"));')['raw'],'small original\n')

    def test_interrupted_delete_recovers_from_committed_index_and_import_orphans(self):
        p=self.saved();report=self.call('echo json_encode($s->refresh());')['reports'][0];rid=report['id']
        index=json.loads((self.root/'index.json').read_text());record=index['reports'][rid]
        for committed in [False,True]:
            journal=self.root/'delete.json';journal.write_text(json.dumps({'version':1,'id':rid,'report':record,'source_present':True}));journal.chmod(0o600)
            p.rename(self.source/('.nfqws2-deleted-'+rid))
            (self.root/(rid+'.txt')).rename(self.root/('.deleted-'+rid+'.txt'))
            if committed:
                index['reports'].pop(rid);(self.root/'index.json').write_text(json.dumps(index))
            listed=self.call('echo json_encode($s->list());')
            self.assertEqual(len(listed['reports']),0 if committed else 1)
            self.assertEqual(p.exists(),not committed);self.assertFalse(journal.exists())
        orphan=self.root/('a'*32+'.txt');orphan.write_text('uncommitted original');orphan.chmod(0o600)
        self.call('echo json_encode($s->list());');self.assertFalse(orphan.exists())


    def test_native_saved_txt_is_discovered_once_and_preserved(self):
        self.saved(); self.saved('unrelated.txt','not a report')
        out=self.call('$a=$s->refresh();$b=$s->refresh();$id=$a["reports"][0]["id"];echo json_encode([$a,$b,$s->read($id)]);')
        a,b,r=out
        self.assertEqual(len(a['reports']),1)
        self.assertEqual(a['reports'],b['reports'])
        self.assertEqual(r['raw'],'Original <report>\n')
        self.assertEqual(r['filename'],NAME)
        self.assertRegex(a['reports'][0]['id'],r'^[a-f0-9]{32}$')
        self.assertNotIn(str(self.source),json.dumps(a))
        self.assertEqual(self.root.stat().st_mode & 0o777,0o700)
        for p in self.root.iterdir(): self.assertEqual(p.stat().st_mode & 0o777,0o600)

    def test_source_change_does_not_replace_imported_snapshot(self):
        p=self.saved()
        first=self.call('echo json_encode($s->refresh());')['reports'][0]
        p.write_text('Changed report\n')
        self.assertEqual(self.call(f'echo json_encode($s->read("{first["id"]}"));')['raw'],'Original <report>\n')
        updated=self.call('echo json_encode($s->refresh());')
        self.assertEqual(len(updated['reports']),2)
        self.assertEqual(self.call(f'$s->delete("{first["id"]}");echo "null";'),{'error':'source_changed'})
        self.assertEqual(p.read_text(),'Changed report\n')

    def test_links_oversize_and_unknown_names_are_not_imported(self):
        original=self.base/'secret';original.write_text('PRIVATE_CANARY')
        (self.source/NAME).symlink_to(original)
        os.link(original,self.source/'dpi_detector_results-20261016-130001.txt')
        self.saved('dpi_detector_results-20261016-130002.txt','x'*1048577)
        self.saved('dpi_detector_results-INVALID.txt')
        out=self.call('echo json_encode($s->refresh());')
        self.assertEqual(out['reports'],[])
        self.assertEqual(out['skipped'],3)
        self.assertNotIn('PRIVATE_CANARY',json.dumps(out))
        self.assertEqual(original.read_text(),'PRIVATE_CANARY')

    def test_twenty_report_limit_does_not_delete_any_original(self):
        for i in range(21):self.saved(f'dpi_detector_results-20261016-1300{i:02d}.txt',str(i))
        out=self.call('echo json_encode($s->refresh());')
        self.assertEqual(len(out['reports']),20)
        self.assertEqual(out['code'],'limit_reached')
        self.assertEqual(len(list(self.source.iterdir())),21)

    def test_delete_removes_only_matching_snapshot_and_source(self):
        self.saved();other=self.saved('keep.txt')
        out=self.call('$a=$s->refresh();$s->delete($a["reports"][0]["id"]);echo json_encode($s->list());')
        self.assertEqual(out['reports'],[])
        self.assertFalse((self.source/NAME).exists())
        self.assertTrue(other.exists())
        self.assertEqual(self.call('$s->read("../../secret");echo "null";'),{'error':'invalid_request'})

    def test_unsafe_private_root_is_rejected_without_chmod(self):
        self.root.mkdir(mode=0o755)
        self.assertEqual(self.call('echo json_encode($s->list());'),{'error':'invalid_state'})
        self.assertEqual(self.root.stat().st_mode & 0o777,0o755)

    def test_import_index_and_payload_survive_new_instance(self):
        self.saved()
        first=self.call('echo json_encode($s->refresh());')['reports'][0]
        (self.source/NAME).unlink()
        self.assertEqual(self.call('echo json_encode($s->list());')['reports'][0],first)
        self.assertEqual(self.call(f'echo json_encode($s->read("{first["id"]}"));')['raw'],'Original <report>\n')

import json,os,shlex,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class DiagnosticsTests(unittest.TestCase):
 def test_omitted_queue_uses_same_default_as_service(self):
  config=self.w/'minimal-config';config.write_text('NFQWS_ARGS="--filter-tcp=443"\n')
  command=f'. {shlex.quote(str(ROOT/"asus/diagnostics.sh"))}; asus_diagnostic_queue {shlex.quote(str(config))}'
  result=subprocess.run(shlex.split(os.environ.get('TEST_SHELL','sh'))+['-c',command],capture_output=True,text=True)
  self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout.strip(),'300')
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.w=Path(self.tmp.name)
  for name in ['proc/net/netfilter','sys/module','ark']: (self.w/name).mkdir(parents=True)
  (self.w/'proc/modules').write_text('nfnetlink_queue 100 1 - Live 0\n')
  (self.w/'proc/net/netfilter/nfnetlink_queue').write_text('')
 def diag(self,q='300'):
  lib=ROOT/'asus/diagnostics.sh';self.assertTrue(lib.exists(),'read-only diagnostic module missing')
  helpers = ''
  if os.environ.get('BUSYBOX_TEST_BINARY'):
   bb=shlex.quote(os.environ['BUSYBOX_TEST_BINARY']); helpers=f'awk() {{ {bb} awk "$@"; }}; cat() {{ {bb} cat "$@"; }}; readlink() {{ {bb} readlink "$@"; }}; '
  cmd=helpers+f'. {shlex.quote(str(lib))}; ASUS_DIAGNOSTIC_PROCESS=false; asus_diagnostics_json {shlex.quote(str(q))} "$WORK/proc" "$WORK/sys" "$WORK/ark"'
  r=subprocess.run(shlex.split(os.environ.get('TEST_SHELL','sh'))+['-c',cmd],env={**os.environ,'WORK':str(self.w)},text=True,capture_output=True)
  self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stderr,'');return json.loads(r.stdout)
 def test_ark_file_and_exact_module_are_distinct(self):
  (self.w/'ark/ark.ko').write_bytes(b'elf');self.assertEqual(self.diag()['ark'],{'present':'present','loaded':'unloaded'})
  (self.w/'proc/modules').write_text('ark_sig 10 0 - Live 0\n');self.assertEqual(self.diag()['ark']['loaded'],'unloaded')
  (self.w/'proc/modules').write_text('ark 10 0 - Live 0\n');self.assertEqual(self.diag()['ark']['loaded'],'loaded')
  (self.w/'proc/modules').write_text('');(self.w/'sys/module/ark').mkdir();self.assertEqual(self.diag()['ark']['loaded'],'loaded')
 def test_missing_sources_are_unknown(self):
  (self.w/'proc/modules').unlink();(self.w/'sys/module').rmdir();(self.w/'ark').rmdir()
  d=self.diag();self.assertEqual(d['ark'],{'present':'unknown','loaded':'unknown'})
  (self.w/'proc/net/netfilter/nfnetlink_queue').unlink();self.assertEqual(self.diag()['nfqueue']['state'],'unknown')
 def test_queue_sequence_uint32_and_neighbour_ignored(self):
  for q in [0,300,65535]:
   for seq in [0,123,2147483648,4294967295]:
    (self.w/'proc/net/netfilter/nfnetlink_queue').write_text(f'1 777 0 2 65535 0 0 55 1\n{q} 1234 0 2 65535 0 0 {seq} 1\n')
    d=self.diag(q)['nfqueue'];self.assertEqual(d,{'queue_number':q,'state':'bound','sequence':seq})
 def test_invalid_input_and_malformed_queue_never_report_zero(self):
  self.assertEqual(self.diag()['nfqueue']['state'],'unbound')
  for value in ['',-1,65536,'$(touch bad)']:
   self.assertEqual(self.diag(value)['nfqueue'],{'queue_number':None,'state':'unknown','sequence':None})
  for row in ['300 1 2','300 1 0 2 65535 0 0 4294967296 1','300 1 0 2 65535 0 0 nope 1']:
   (self.w/'proc/net/netfilter/nfnetlink_queue').write_text(row+'\n');self.assertEqual(self.diag()['nfqueue']['state'],'unknown')
 def test_safe_literal_queue_parser_does_not_execute_shell(self):
  lib=ROOT/'asus/diagnostics.sh';self.assertTrue(lib.exists(),'read-only diagnostic module missing')
  f=self.w/'config';sentinel=self.w/'executed'
  for line,want in [('NFQUEUE_NUM=300',300),('NFQUEUE_NUM="65535" # comment',65535),('NFQUEUE_NUM=2147483648',None),(f'NFQUEUE_NUM=$(touch {sentinel})',None),('NFQUEUE_NUM=300; echo hi',None),('NFQUEUE_NUM=300\nNFQUEUE_NUM=301',None)]:
   f.write_text(line+'\n');r=subprocess.run(['sh','-c',f'. {shlex.quote(str(lib))}; asus_diagnostic_queue {shlex.quote(str(f))}'],capture_output=True,text=True)
   self.assertEqual(r.stdout.strip(),str(want) if want is not None else 'null');self.assertFalse(sentinel.exists())

class DiagnosticCliTests(unittest.TestCase):
 def test_cli_uses_runtime_queue_without_config_execution_or_mutations(self):
  with tempfile.TemporaryDirectory() as tmp:
   w=Path(tmp);lib=w/'opt/lib/nfqws2-asus';lib.mkdir(parents=True)
   for name in ['platform.sh','lifecycle.sh','diagnostics.sh']:(lib/name).write_text((ROOT/'asus'/name).read_text())
   conf=w/'opt/etc/nfqws2/nfqws2.conf';conf.parent.mkdir(parents=True)
   bad=w/'executed';conf.write_text(f'NFQUEUE_NUM=123\ntouch {bad}\n')
   run=w/'run';run.mkdir();(run/'pid').write_text(str(os.getpid()))
   (run/'runtime.conf').write_text(f'NFQUEUE_NUM=321\ntouch {bad}\n')
   init=(ROOT/'asus/S51nfqws2').read_text().replace('/opt/',tmp+'/opt/').replace('RUN_DIR=/tmp/nfqws2-asus',f'RUN_DIR={run}')
   init=init.replace(f'NFQWS_BIN={tmp}/opt/usr/bin/nfqws2',f'NFQWS_BIN=/proc/{os.getpid()}/exe')
   f=w/'init';f.write_text(init)
   before=set(w.rglob('*'));r=subprocess.run(['sh',str(f),'diagnostics'],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(json.loads(r.stdout)['nfqueue']['queue_number'],321)
   self.assertFalse(bad.exists());self.assertEqual(set(w.rglob('*')),before)
   (run/'pid').unlink();r=subprocess.run(['sh',str(f),'diagnostics'],capture_output=True,text=True)
   self.assertEqual(json.loads(r.stdout)['nfqueue']['queue_number'],123)
   r=subprocess.run(['sh',str(f),'diagnostics','/etc/passwd'],capture_output=True,text=True)
   self.assertEqual(r.returncode,2)

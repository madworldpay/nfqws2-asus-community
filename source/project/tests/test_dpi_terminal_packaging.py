"""The actual payload must contain a verified helper for every package family."""
import importlib.util
from pathlib import Path
import os
import unittest

ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
class TerminalPackagingTests(unittest.TestCase):
 def test_asus_builder_emits_helper_next_to_update_launcher(self):
  builder=load('dpi_asus_builder',ROOT/'asus/build.py')
  for family in builder.TARGETS:
   with self.subTest(family=family):
    self.assertTrue(callable(getattr(builder,'dpi_terminal_payload',None)),'ASUS builder must include the verified terminal helper')
    payload=builder.dpi_terminal_payload(family)
    self.assertEqual(set(payload),{'opt/libexec/nfqws2-asus/dpi-terminal'})
    data,mode=payload['opt/libexec/nfqws2-asus/dpi-terminal'];self.assertEqual(mode,0o755)
    builder.validate_elf(data,builder.TARGETS[family],'DPI terminal')
 def test_native_builder_emits_verified_helper_for_all_ten_architectures(self):
  import json
  builder=load('dpi_native_builder',ROOT/'openwrt/build.py')
  arches=json.loads((ROOT/'openwrt/release-targets.json').read_text())['architectures']
  for arch in arches:
   with self.subTest(arch=arch):
    self.assertTrue(callable(getattr(builder,'dpi_terminal_payload',None)),'Native builder must include the verified terminal helper')
    target=builder.native_metadata('24.10',arch)
    payload=builder.dpi_terminal_payload(target['engine'])
    self.assertEqual(set(payload),{'usr/lib/nfqws2/dpi-terminal'})
    data,mode=payload['usr/lib/nfqws2/dpi-terminal'];self.assertEqual(mode,0o755)
    builder.platform.validate_engine(data,target)

class TerminalTransitionTests(unittest.TestCase):
 def test_preinstall_stop_works_before_the_new_public_controller_exists(self):
  import subprocess,tempfile
  php=os.environ.get('PHP_TEST_BINARY')
  if not php:self.skipTest('PHP runtime required')
  hook=load('dpi_preinstall_hook',ROOT/'asus/dpi/package_hook.py')
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);run=root/'runtime'; run.mkdir(mode=0o700)
   script=root/'preinst';script.write_bytes(b'#!/bin/sh\n'+hook.shutdown_hook(php,runtime=str(run),temporary_parent=str(root)))
   # Root-owned runtime, no installed public controller/helper at all: this is
   # the first upgrade from a private prototype/older package.
   subprocess.run(['sudo','-n','chown','root:root',str(run)],check=True)
   try:
    result=subprocess.run(['sudo','-n','sh',str(script)],capture_output=True,text=True,timeout=10)
    self.assertEqual(result.returncode,0,result.stdout+result.stderr)
    self.assertFalse(list(root.glob('.nfqws-dpi-stop.*')))
   finally:subprocess.run(['sudo','-n','rm','-rf',str(run)],check=True)
 def test_first_install_without_a_terminal_does_not_require_php_yet(self):
  import subprocess,tempfile
  hook=load('dpi_first_install_hook',ROOT/'asus/dpi/package_hook.py')
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);s=root/'preinst';s.write_bytes(hook.shutdown_hook('/missing/php',runtime=str(root/'absent')))
   self.assertEqual(subprocess.run(['sh',str(s)],capture_output=True).returncode,0)

class InlineHookTests(unittest.TestCase):
 def test_native_preinstall_embeds_shutdown_before_the_old_payload_is_replaced(self):
  builder=load('dpi_native_transition_builder',ROOT/'openwrt/build.py')
  for series in ['24.10','25.12']:
   script=builder.package_hook(builder.native_metadata(series,'arm_cortex-a9'), 'preinstall')
   self.assertIn(b'NFQWS_DPI_STOP_PHP',script)
   self.assertIn(b'nfqws_package_inline_stop_detector && nfqws_package_snapshot',script)

class InlineWriterFailureTests(unittest.TestCase):
 def test_partial_php_write_cannot_report_success_without_stopping_terminal(self):
  import subprocess,tempfile
  hook=load('dpi_inline_writer',ROOT/'asus/dpi/package_hook.py');php=os.environ.get('PHP_TEST_BINARY')
  if not php:self.skipTest('PHP runtime required')
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);(root/'runtime').mkdir(mode=0o700)
   script=b'''#!/bin/sh
cat() { printf '<?php\n'; return 1; }
'''+hook.shutdown_hook(php,runtime=str(root/'runtime'),temporary_parent=str(root))
   result=subprocess.run(['sh'],input=script,capture_output=True,timeout=5)
   self.assertNotEqual(result.returncode,0,'Failed writer must abort before any payload replacement')
   self.assertFalse(list(root.glob('.nfqws-dpi-stop.*')))


class ActiveInlineTransitionTests(unittest.TestCase):
 def test_inline_hook_stops_old_broker_and_term_ignoring_descendant(self):
  import subprocess,tempfile,time
  php=os.environ.get('PHP_TEST_BINARY')
  if not php:self.skipTest('PHP runtime required')
  hook=load('dpi_active_inline_hook',ROOT/'asus/dpi/package_hook.py')
  with tempfile.TemporaryDirectory() as td:
   base=Path(td);run=base/'runtime';run.mkdir(mode=0o700)
   helper=base/'broker';helper.write_bytes((ROOT/'asus/dpi/bin/dpi-terminal-x86_64').read_bytes());helper.chmod(0o755)
   source=base/'detector.c';source.write_text(r'''#include <stdio.h>
#include <unistd.h>
#include <signal.h>
int main(void){signal(SIGTERM,SIG_IGN);signal(SIGHUP,SIG_IGN);pid_t p=fork();if(!p){for(;;)sleep(1);}printf("PARENT=%d CHILD=%d\n",getpid(),p);fflush(stdout);for(;;)sleep(1);}
''')
   detector=base/'detector';subprocess.run(['gcc','-O2',str(source),'-o',str(detector)],check=True);detector.chmod(0o755)
   script=base/'preinst';script.write_bytes(b'#!/bin/sh\n'+hook.shutdown_hook(php,runtime=str(run),temporary_parent=str(base)))
   subprocess.run(['sudo','-n','chown','-R','root:root',str(base)],check=True)
   try:
    started=subprocess.run(['sudo','-n',str(helper),str(run),str(detector),str(base),'100','30','en'],capture_output=True,timeout=6)
    self.assertEqual(started.returncode,0,started.stderr)
    raw=b'';until=time.monotonic()+3
    while b'CHILD=' not in raw and time.monotonic()<until:
     time.sleep(.03);raw=subprocess.check_output(['sudo','-n','cat',str(run/'output')])
    import re
    match=re.search(rb'PARENT=(\d+) CHILD=(\d+)',raw);self.assertIsNotNone(match,raw)
    pids=[int(x) for x in match.groups()]
    stopped=subprocess.run(['sudo','-n','sh',str(script)],capture_output=True,timeout=10)
    self.assertEqual(stopped.returncode,0,stopped.stderr)
    self.assertTrue(subprocess.check_output(['sudo','-n','cat',str(run/'status')]).startswith(b'stopped '))
    for pid in pids:
     state=subprocess.run(['sudo','-n','cat',f'/proc/{pid}/stat'],capture_output=True)
     if state.returncode==0:self.assertEqual(state.stdout.split(b') ')[1][:1],b'Z')
    self.assertEqual(subprocess.run(['sudo','-n','test','-S',str(run/'control.sock')]).returncode,1)
   finally:
    # Fixed operator-owned runtime only; always stop our broker on assertion failure.
    subprocess.run(['sudo','-n','sh',str(script)],capture_output=True,timeout=10)
    subprocess.run(['sudo','-n','chown','-R',f'{os.getuid()}:{os.getgid()}',str(base)],check=True)

if __name__=='__main__':unittest.main()

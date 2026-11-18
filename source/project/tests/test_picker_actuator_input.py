"""Real owned PHP leaves exercise the picker's bounded stdin actuator."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import signal
import time
import unittest
from test_dpi_normalize import PHP, PUBLIC


class PickerActuatorInputTests(unittest.TestCase):
    def owned_identity_alive(self, proof, leaf):
        """Tests signal only their exact recorded leaf, never an arbitrary PID."""
        pid = proof['pid']
        try:
            fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
            argv = Path(f'/proc/{pid}/cmdline').read_bytes().rstrip(b'\0').decode().split('\0')
            # After our SIGKILL the kernel can clear argv between the stat and
            # cmdline reads, just before publishing Z. Never signal that state.
            if fields[0] == 'Z' or argv == ['']:
                return False
            self.assertEqual(fields[19], proof['ticks'])
            self.assertEqual(Path('/proc/sys/kernel/random/boot_id').read_text().strip(), proof['boot'])
            self.assertEqual(argv, proof['argv'])
            self.assertIn(str(leaf), argv)
            self.assertEqual(Path(f'/proc/{pid}').stat().st_uid, os.getuid())
            return True
        except FileNotFoundError:
            return False

    def parent_death(self, after_input):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            leaf = root / 'leaf.php'
            leaf.write_text('''<?php $input=stream_get_contents(STDIN);if($input!=="complete")exit(9);
              $j=json_decode(file_get_contents($argv[1].'/picker/state.json'),true);
              if(($j['actuator']['pid']??null)!==getmypid())exit(8);
              file_put_contents($argv[1].'/activated','yes');usleep(5000000);''')
            parent = root / 'parent.php'
            parent.write_text('''<?php umask(0077);require $argv[1].'/strategy-picker-runtime.php';$root=$argv[2];
              $s=new NfqwsStrategyPickerState($root.'/picker',(int)$argv[3]);
              $s->write(['id'=>str_repeat('a',32),'phase'=>'discovering','state'=>'running','actuator'=>null]);
              $r=new NfqwsStrategyPickerRuntime($s,new NfqwsStrategyPickerConfig($s,$root.'/nfqws2.conf',(int)$argv[3]));
              $check=static function()use($root,$s,$argv){
                $ready=$argv[5]==='after'?file_exists($root.'/activated'):($s->read()['actuator']??null)!==null;
                if($ready){$p=proc_open(['/bin/kill','-KILL',(string)getmypid()],
                  [0=>['file','/dev/null','r'],1=>['file','/dev/null','w'],2=>['file','/dev/null','w']],$pipes);
                  if(is_resource($p))proc_close($p);throw new RuntimeException('self_kill_failed');}};
              (new ReflectionMethod($r,'actuator'))->invoke($r,[$argv[4],'-n','-f',$root.'/leaf.php',$root],
                3,'complete',$check);''')
            process = subprocess.Popen([PHP, '-n', '-f', str(parent), str(PUBLIC), directory,
                                        str(os.getuid()), PHP, 'after' if after_input else 'before'],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            proof = None
            try:
                out, error = process.communicate(timeout=7)
                self.assertEqual(process.returncode, -signal.SIGKILL, error + out)
                self.assertEqual(error + out, b'')
                proof = json.loads((root / 'picker/state.json').read_text())['actuator']
                self.assertIsNotNone(proof)
                if after_input:
                    self.assertTrue((root / 'activated').exists())
                    self.assertTrue(self.owned_identity_alive(proof, leaf))
                else:
                    end = time.monotonic() + 1
                    while self.owned_identity_alive(proof, leaf) and time.monotonic() < end:
                        time.sleep(.01)
                    self.assertFalse(self.owned_identity_alive(proof, leaf))
                    self.assertFalse((root / 'activated').exists())
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
                if proof is not None and self.owned_identity_alive(proof, leaf):
                    os.kill(proof['pid'], signal.SIGKILL)
                    end = time.monotonic() + 1
                    while self.owned_identity_alive(proof, leaf) and time.monotonic() < end:
                        time.sleep(.01)
                    self.assertFalse(self.owned_identity_alive(proof, leaf))

    def php(self, body):
        with tempfile.TemporaryDirectory() as directory:
            code = '''umask(0077);require $argv[1].'/strategy-picker-runtime.php';
            $root=$argv[2];$s=new NfqwsStrategyPickerState($root.'/picker',(int)$argv[3]);
            $s->write(['id'=>str_repeat('a',32),'phase'=>'discovering','state'=>'running','actuator'=>null]);
            $c=new NfqwsStrategyPickerConfig($s,$root.'/nfqws2.conf',(int)$argv[3]);
            $r=new NfqwsStrategyPickerRuntime($s,$c);$m=new ReflectionMethod($r,'actuator');
            $php=$argv[4];$noop=static function(){};''' + body
            result = subprocess.run([PHP, '-n', '-r', code, str(PUBLIC), directory,
                                     str(os.getuid()), PHP], capture_output=True, text=True, timeout=12)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(result.stderr, '')
        return json.loads(result.stdout)

    def test_complete_input_is_sent_only_after_actor_registration(self):
        value = self.php('''$leaf=$root.'/leaf.php';file_put_contents($leaf, '<?php
          $input=stream_get_contents(STDIN);$j=json_decode(file_get_contents($argv[1]),true);
          echo json_encode(["input"=>$input,"registered"=>($j["actuator"]["pid"]??null)===getmypid()]);');
          $calls=0;$check=static function()use(&$calls){$calls++;};
          $v=$m->invoke($r,[$php,'-n','-f',$leaf,$s->path('state.json')],2,'PRIVATE-HOST-PAYLOAD',$check);
          echo json_encode(['result'=>$v,'calls'=>$calls,'actor'=>$s->read()['actuator']]);''')
        self.assertEqual(value['result']['status'], 0)
        self.assertEqual(json.loads(value['result']['output']),
                         {'input': 'PRIVATE-HOST-PAYLOAD', 'registered': True})
        self.assertGreater(value['calls'], 0)
        self.assertIsNone(value['actor'])

    def test_invalid_input_budget_or_missing_checkpoint_never_launches(self):
        value = self.php('''$out=[];foreach([[str_repeat('x',8193),1,$noop],['x',0,$noop],
          ['x',91,$noop],['x',1,null]]as[$input,$seconds,$check]){
          try{$m->invoke($r,[$php,'-n','-r','file_put_contents($argv[1],"started");',$root.'/started'],
            $seconds,$input,$check);$out[]='accepted';}catch(RuntimeException $e){$out[]=$e->getMessage();}}
          echo json_encode(['codes'=>$out,'started'=>file_exists($root.'/started')]);''')
        self.assertEqual(value, {'codes': ['invalid_request'] * 4, 'started': False})

    def test_cancel_kills_only_owned_leaf_and_reaps_before_clearing(self):
        value = self.php('''$leaf=$root.'/leaf.php';file_put_contents($leaf,'<?php
          stream_get_contents(STDIN);file_put_contents($argv[1],(string)getmypid());usleep(4000000);');
          $other=proc_open([$php,'-n','-r','usleep(4000000);'],[0=>['file','/dev/null','r'],
            1=>['file','/dev/null','w'],2=>['file','/dev/null','w']],$pipes);$code=null;$t=microtime(true);
          try{$check=static function()use($root){if(file_exists($root.'/leaf.pid'))throw new RuntimeException('cancelled');};
            $m->invoke($r,[$php,'-n','-f',$leaf,$root.'/leaf.pid'],3,'payload',$check);
          }catch(RuntimeException $e){$code=$e->getMessage();}
          $pid=(int)file_get_contents($root.'/leaf.pid');
          $out=['code'=>$code,'elapsed'=>microtime(true)-$t,'leaf_alive'=>NfqwsStrategyPickerRuntime::identity($pid)!==null,
            'other_alive'=>proc_get_status($other)['running'],'actor'=>$s->read()['actuator']];
          proc_terminate($other,9);proc_close($other);echo json_encode($out);''')
        self.assertEqual(value['code'], 'cancelled')
        self.assertLess(value['elapsed'], 2)
        self.assertFalse(value['leaf_alive'])
        self.assertTrue(value['other_alive'])
        self.assertIsNone(value['actor'])

    def test_deadline_stops_a_leaf_that_does_not_read_stdin(self):
        value = self.php('''$leaf=$root.'/leaf.php';file_put_contents($leaf,'<?php
          file_put_contents($argv[1],(string)getmypid());usleep(4000000);');
          $t=microtime(true);$code=null;try{$m->invoke($r,[$php,'-n','-f',$leaf,$root.'/leaf.pid'],
            1,str_repeat('x',8192),$noop);}catch(RuntimeException $e){$code=$e->getMessage();}
          echo json_encode(['code'=>$code,'elapsed'=>microtime(true)-$t,
            'alive'=>NfqwsStrategyPickerRuntime::identity((int)file_get_contents($root.'/leaf.pid'))!==null,
            'actor'=>$s->read()['actuator']]);''')
        self.assertEqual(value['code'], 'timed_out')
        self.assertLess(value['elapsed'], 2.5)
        self.assertFalse(value['alive'])
        self.assertIsNone(value['actor'])

    def test_output_flood_is_bounded_and_does_not_leave_a_leaf(self):
        value = self.php('''$leaf=$root.'/leaf.php';file_put_contents($leaf,'<?php
          stream_get_contents(STDIN);file_put_contents($argv[1],(string)getmypid());
          while(true)echo str_repeat("x",8192);');$code=null;
          try{$m->invoke($r,[$php,'-n','-f',$leaf,$root.'/leaf.pid'],2,'payload',$noop);}
          catch(RuntimeException $e){$code=$e->getMessage();}
          echo json_encode(['code'=>$code,'alive'=>NfqwsStrategyPickerRuntime::identity((int)file_get_contents($root.'/leaf.pid'))!==null,
            'actor'=>$s->read()['actuator']]);''')
        self.assertEqual(value, {'code': 'output_limit', 'alive': False, 'actor': None})

    def test_fast_exit_preserves_original_failure_code(self):
        value = self.php('''$v=$m->invoke($r,[$php,'-n','-r','exit(7);'],1,'payload',$noop);
          echo json_encode(['status'=>$v['status'],'output'=>$v['output'],'actor'=>$s->read()['actuator']]);''')
        self.assertEqual(value, {'status': 7, 'output': '', 'actor': None})

    def test_prelaunch_cancel_starts_no_child(self):
        value = self.php('''$code=null;try{$m->invoke($r,[$php,'-n','-r',
          'file_put_contents($argv[1],"started");',$root.'/started'],1,'payload',
          static function(){throw new RuntimeException('cancelled');});}
          catch(RuntimeException $e){$code=$e->getMessage();}
          echo json_encode(['code'=>$code,'started'=>file_exists($root.'/started'),'actor'=>$s->read()['actuator']]);''')
        self.assertEqual(value, {'code': 'cancelled', 'started': False, 'actor': None})

    def test_cleanup_does_not_clear_another_job_or_actor(self):
        value = self.php('''$leaf=$root.'/leaf.php';file_put_contents($leaf,'<?php
          stream_get_contents(STDIN);file_put_contents($argv[1],(string)getmypid());usleep(4000000);');
          $foreign=['pid'=>999999,'ticks'=>'other','boot'=>'other','argv'=>[]];$code=null;
          $check=static function()use($root,$s,$foreign){if(file_exists($root.'/leaf.pid')){
            $s->write(['id'=>str_repeat('b',32),'phase'=>'other','actuator'=>$foreign]);throw new RuntimeException('cancelled');}};
          try{$m->invoke($r,[$php,'-n','-f',$leaf,$root.'/leaf.pid'],3,'payload',$check);}
          catch(RuntimeException $e){$code=$e->getMessage();}echo json_encode(['code'=>$code,'state'=>$s->read()]);''')
        self.assertEqual(value['code'], 'cancelled')
        self.assertEqual(value['state'], {'id': 'b' * 32, 'phase': 'other',
                         'actuator': {'pid': 999999, 'ticks': 'other', 'boot': 'other', 'argv': []}})

    def test_parent_death_before_input_cannot_activate_a_leaf(self):
        self.parent_death(False)

    def test_parent_death_after_input_retains_exact_cleanup_identity(self):
        self.parent_death(True)


if __name__ == '__main__':
    unittest.main()

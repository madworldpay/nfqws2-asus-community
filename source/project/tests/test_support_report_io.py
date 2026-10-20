import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
PHP = os.environ.get('PHP_TEST_BINARY', str(ROOT / '.work/packaging-audit-20261012/aarch64-cli-wrapper'))


class ReportIOTests(unittest.TestCase):
    def test_firmware_save_uses_supported_no_module_loader_option(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);binary=p/'iptables-save';binary.write_text('#!/bin/sh\n[ "$1" = --modprobe ] && [ "$2" = /bin/false ] || exit 1\nprintf "*mangle\\nCOMMIT\\n"\n');binary.chmod(0o755)
            (p/'ip6tables-save').write_bytes(binary.read_bytes());(p/'ip6tables-save').chmod(0o755)
            src=ROOT/'webui/web/public/support-report-io.php';copy=p/'io.php'
            copy.write_text(src.read_text().replace("['/usr/sbin','/sbin','/usr/bin','/bin','/opt/sbin','/opt/bin']", "["+json.dumps(str(p))+"]"))
            code="require $argv[1];$io=new AsusReportIO();echo json_encode([$io->streamCommand('rules4-mangle',static function($l){}),$io->streamCommand('rules6-mangle',static function($l){})]);"
            r=subprocess.run([PHP,'-n','-r',code,str(copy)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
            self.assertEqual([v['state'] for v in json.loads(r.stdout)],['available','available'])
    def test_completed_exit_is_retained_until_inherited_pipes_close(self):
        for exit_code in [0, 7]:
            with self.subTest(exit_code=exit_code), tempfile.TemporaryDirectory() as tmp:
                f=Path(tmp)/'probe'
                f.write_text(f'#!/bin/sh\nprintf "rule\\n"\nsleep 0.08 &\nexit {exit_code}\n')
                f.chmod(0o700)
                result=self.run_php('''$io=new AsusReportIO(['commands'=>['probe'=>[$argv[2]]]]);
                    echo json_encode($io->streamCommand('probe',static function($l){}));''',f)
                self.assertEqual(result,{'state':'available' if exit_code==0 else 'unsupported','exit_code':exit_code})

    def test_kernel_proc_net_link_is_allowed_but_escape_is_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            proc = p / 'proc'
            (proc / '123/net/netfilter').mkdir(parents=True)
            (proc / 'self').symlink_to('123', target_is_directory=True)
            (proc / 'net').symlink_to('self/net', target_is_directory=True)
            (proc / '123/net/netfilter/nfnetlink_queue').write_text('300 345 0 2 65535 0 0 1 1\n')
            result = self.run_php('''$io=new AsusReportIO(['proc'=>$argv[2]]);echo json_encode($io->read('queue'));''', proc)
            self.assertEqual(result['state'], 'available')
            (proc / 'net').unlink()
            (proc / 'net').symlink_to(p, target_is_directory=True)
            result = self.run_php('''$io=new AsusReportIO(['proc'=>$argv[2]]);echo json_encode($io->read('queue'));''', proc)
            self.assertEqual(result['state'], 'denied')

    def run_php(self, code, *args, timeout=8):
        lib = str(ROOT / 'webui/web/public/support-report-io.php')
        run = subprocess.run([PHP, '-r', 'require $argv[1]; ' + code, lib, *map(str, args)],
                             capture_output=True, text=True, timeout=timeout)
        self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
        return json.loads(run.stdout)

    def test_canonical_opt_allowed_but_nested_symlinks_and_fifo_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / 'real/etc/nfqws2/lists').mkdir(parents=True)
            (p / 'opt').symlink_to(p / 'real', target_is_directory=True)
            (p / 'real/etc/nfqws2/nfqws2.conf').write_text('NFQUEUE_NUM=300\n')
            (p / 'real/etc/nfqws2/lists/good.list').write_text('canary.invalid\n')
            (p / 'outside').write_text('SECRET')
            (p / 'real/etc/nfqws2/lists/escape.list').symlink_to(p / 'outside')
            os.mkfifo(p / 'real/etc/nfqws2/lists/pipe.list')
            result = self.run_php('''$io=new AsusReportIO(['opt'=>$argv[2]]);
                echo json_encode([$io->read('config',262144),
                  $io->readResource('list','escape.list',100),
                  $io->readResource('list','pipe.list',100),
                  $io->readResource('list','../outside',100)]);''', p / 'opt')
            self.assertEqual(result[0]['state'], 'available')
            self.assertTrue(all(x['state'] == 'denied' for x in result[1:]))
            self.assertNotIn('SECRET', json.dumps(result))

    def test_hung_and_continuously_writing_children_are_bounded(self):
        for script in ['#!/bin/sh\nsleep 10\n', '#!/bin/sh\nwhile :; do echo output; done\n']:
            with tempfile.TemporaryDirectory() as tmp:
                f = Path(tmp) / 'probe'
                f.write_text(script)
                f.chmod(0o700)
                before = time.monotonic()
                result = self.run_php('''$io=new AsusReportIO(['commands'=>['probe'=>[$argv[2]]]]);
                    echo json_encode($io->streamCommand('probe',static function($l){},0.15));''', f)
                self.assertIn(result['state'], ['timeout', 'truncated'])
                self.assertLess(time.monotonic() - before, 3)

    def test_collector_lock_rejects_unsafe_paths_and_releases(self):
        report = str(ROOT / 'webui/web/public/support-report.php')
        code = """require $argv[3];
            $l=new AsusReportLock($argv[2],fileowner(dirname($argv[2])));
            try{$l->acquire();$second=new AsusReportLock($argv[2],fileowner(dirname($argv[2])));
                try{$second->acquire();$collision='unexpected';}catch(Throwable $e){$collision=$e->getMessage();}
                $l->release();$second->acquire();$second->release();echo json_encode(['state'=>'ok','collision'=>$collision]);
            }catch(Throwable $e){echo json_encode(['state'=>$e->getMessage()]);}"""
        for kind in ['normal','directory_link','file_link','fifo','open_directory','open_file']:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp); lock=p/'lock'; target=p/'target'
                if kind=='directory_link':
                    target.mkdir(mode=0o700);lock.symlink_to(target,target_is_directory=True)
                else:
                    lock.mkdir(mode=0o700)
                    if kind=='file_link':
                        target.write_text('canary');(lock/'collector.lock').symlink_to(target)
                    elif kind=='fifo':os.mkfifo(lock/'collector.lock',0o600)
                    elif kind=='open_directory':lock.chmod(0o777)
                    elif kind=='open_file':
                        (lock/'collector.lock').touch();(lock/'collector.lock').chmod(0o644)
                result=self.run_php(code,lock,report)
                self.assertEqual(result['state'],'ok' if kind=='normal' else 'unavailable')
                if kind=='normal':self.assertEqual(result['collision'],'busy')
                if target.is_file():self.assertEqual(target.read_text(),'canary')

    def test_unknown_command_and_source_are_denied(self):
        result = self.run_php('''$io=new AsusReportIO(); echo json_encode([
            $io->read('/etc/shadow',100),$io->streamCommand('reboot',static function($l){},1)]);''')
        self.assertEqual([x['state'] for x in result], ['denied','denied'])


if __name__ == '__main__':
    unittest.main()

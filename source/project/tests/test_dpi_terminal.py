"""Real PTY integration: protocol validation, fixed argv, bounded lifecycle."""
import os
import fcntl
from pathlib import Path
import shutil
import socket
import signal
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('gcc'), 'gcc required')
class DpiTerminalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory()
        cls.helper = Path(cls.build.name) / 'terminal'
        source = ROOT / 'asus/dpi/terminal.c'
        if not source.exists():
            raise AssertionError('native PTY broker has not been implemented')
        subprocess.run(['gcc', '-std=c99', '-Wall', '-Wextra', '-Werror', '-O2',
                        '-DDPI_IDLE_SECONDS=2', '-DDPI_HARD_SECONDS=5',
                        str(source), '-o', str(cls.helper)], check=True)
        cls.helper.chmod(0o755)
        fake = Path(cls.build.name) / 'detector.c'
        fake.write_text(r'''#define _DEFAULT_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <termios.h>
#include <sys/ioctl.h>
int main(int argc,char **argv){
 struct winsize w;struct termios t;ioctl(0,TIOCGWINSZ,&w);
 printf("TTY=%d,%d,%d SIZE=%u,%u LANG=%s TERM=%s CWD=",isatty(0),isatty(1),isatty(2),w.ws_col,w.ws_row,argc==3?argv[2]:"BAD",getenv("TERM"));
 char cwd[4096];puts(getcwd(cwd,sizeof(cwd)));fflush(stdout);
 tcgetattr(0,&t);cfmakeraw(&t);tcsetattr(0,TCSANOW,&t);
 char c;while(read(0,&c,1)==1){
  if(c=='q')return 7;
  if(c=='s'){ioctl(0,TIOCGWINSZ,&w);printf("SIZE=%u,%u\n",w.ws_col,w.ws_row);fflush(stdout);}
  else if(c=='d'){pid_t p=fork();if(!p){for(;;)sleep(1);}printf("CHILD=%d\n",p);fflush(stdout);}
  else if(c=='f'){char b[4096];memset(b,'X',sizeof(b));for(int i=0;i<600;i++)write(1,b,sizeof(b));}
  else {write(1,&c,1);}
 }return 0;
}''')
        cls.detector = Path(cls.build.name) / 'detector'
        subprocess.run(['gcc', '-std=c99', str(fake), '-o', str(cls.detector)], check=True)
        cls.detector.chmod(0o755)
        probe = Path(cls.build.name) / 'lifecycle-probe.c'
        probe.write_text(r'''#define _GNU_SOURCE
#include <dlfcn.h>
#include <unistd.h>
#include <stdlib.h>
#include <stdio.h>
#include <signal.h>
#include <fcntl.h>
#include <string.h>
pid_t setsid(void){
 static int calls;pid_t (*real_setsid)(void)=dlsym(RTLD_NEXT,"setsid");
 const char *marker=getenv("DPI_TEST_CHILD_BLOCKED");
 if(++calls==2&&marker){
  FILE *f=fopen(marker,"w");if(f){fprintf(f,"%d\n",getpid());fclose(f);}
  char release[4096];snprintf(release,sizeof(release),"%s.release",marker);
  while(access(release,F_OK))usleep(10000);
 }
 return real_setsid();
}
int kill(pid_t pid,int sig){
 int (*real_kill)(pid_t,int)=dlsym(RTLD_NEXT,"kill");
 const char *log=getenv("DPI_TEST_KILL_LOG");
 if(pid<0&&log){
  char path[80],b[4096],state='-';snprintf(path,sizeof(path),"/proc/%d/stat",-pid);
  FILE *f=fopen(path,"r");if(f){if(fgets(b,sizeof(b),f)){char *p=strrchr(b,')');if(p&&p[1]==' ')state=p[2];}fclose(f);}
  f=fopen(log,"a");if(f){fprintf(f,"%d %c\n",sig,state);fclose(f);}
 }
 return real_kill(pid,sig);
}''')
        cls.probe = Path(cls.build.name) / 'lifecycle-probe.so'
        subprocess.run(['gcc','-shared','-fPIC',str(probe),'-ldl','-o',str(cls.probe)],check=True)

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = Path(self.tmp.name) / 'run'
        self.run.mkdir(mode=0o700)
        self.addCleanup(self.tmp.cleanup)

    def launch(self, *extra, env=None):
        r = subprocess.run([str(self.helper), str(self.run), str(self.detector),
                            str(self.detector.parent), '100', '30', 'en', *extra],
                           capture_output=True, timeout=5, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.addCleanup(self.stop)
        return r

    def stop(self):
        try:
            self.request(b'S\n')
        except (OSError, AssertionError):
            pass

    def request(self, data):
        with socket.socket(socket.AF_UNIX) as s:
            s.settimeout(2)
            s.connect(str(self.run / 'control.sock'))
            s.sendall(data)
            f = s.makefile('rb')
            header = f.readline(160).decode().strip().split()
            self.assertEqual(header[0], 'DPT1')
            body = f.read(int(header[4]))
            self.assertEqual(len(body), int(header[4]))
            return header[1], int(header[2]), int(header[3]), body

    def poll_until(self, needle, offset=0):
        end = time.monotonic() + 3
        data = b''
        while time.monotonic() < end:
            state, offset, code, chunk = self.request(f'P {offset}\n'.encode())
            data += chunk
            if needle in data:
                return state, offset, code, data
            time.sleep(.025)
        self.fail(f'missing {needle!r} from {data[-300:]!r}')

    def test_actual_tty_fixed_arguments_input_resize_and_exit(self):
        self.launch()
        _, off, _, data = self.poll_until(b'CWD=')
        self.assertIn(b'TTY=1,1,1 SIZE=100,30 LANG=en TERM=xterm-256color', data)
        self.assertIn(str(self.detector.parent).encode(), data)
        self.request(b'R 72 22\n')
        self.request(b'I 1\ns')
        self.poll_until(b'SIZE=72,22', off)
        self.request(b'I 1\nq')
        time.sleep(.1)
        state, _, code, _ = self.request(b'P 0\n')
        self.assertEqual((state, code), ('exited', 7))

    def test_single_broker_and_bad_protocol_cannot_spawn_or_write(self):
        self.launch()
        duplicate = subprocess.run([str(self.helper), str(self.run), str(self.detector),
                                    str(self.detector.parent), '80', '24', 'ru'], timeout=5)
        self.assertNotEqual(duplicate.returncode, 0)
        for bad in [b'X\n', b'P -1\n', b'P 99999999999\n', b'R 0 24\n', b'I 1025\n', b'P 0 garbage\n']:
            with self.subTest(bad=bad):
                with socket.socket(socket.AF_UNIX) as s:
                    s.settimeout(2);s.connect(str(self.run / 'control.sock'));s.sendall(bad)
                    self.assertEqual(s.recv(100), b'ERR\n')
        self.assertEqual(self.request(b'P 0\n')[0], 'running')

    def test_output_limit_stops_program_and_never_exceeds_two_mib(self):
        self.launch();self.poll_until(b'CWD=');self.request(b'I 1\nf')
        time.sleep(.2)
        self.assertEqual(self.request(b'P 0\n')[0], 'output_limit')
        self.assertEqual((self.run / 'output').stat().st_size, 2097152)

    def test_no_poll_expiry_kills_entire_child_group(self):
        self.launch();self.poll_until(b'CWD=');self.request(b'I 1\nd')
        _, _, _, out = self.poll_until(b'CHILD=')
        child = int(out.split(b'CHILD=')[1].split()[0])
        time.sleep(2.3)
        self.assertEqual(self.request(b'P 0\n')[0], 'expired')
        status = Path(f'/proc/{child}/stat')
        if status.exists():
            self.assertEqual(status.read_text().split(') ')[1][0], 'Z')

    def test_poll_heartbeat_cannot_extend_hard_deadline(self):
        self.launch();start=time.monotonic()
        while time.monotonic()-start<7:
            state,_,_,_=self.request(b'P 0\n')
            if state!='running':
                self.assertEqual(state,'expired')
                self.assertGreater(time.monotonic()-start,4.5)
                return
            time.sleep(.3)
        self.fail('polling kept the terminal alive beyond the hard deadline')

    def test_launcher_waits_for_child_group_and_pre_ready_failure_kills_child(self):
        marker=Path(self.tmp.name)/'child-blocked'
        env=os.environ|{'LD_PRELOAD':str(self.probe),'DPI_TEST_CHILD_BLOCKED':str(marker)}
        process=subprocess.Popen([str(self.helper),str(self.run),str(self.detector),str(self.detector.parent),'100','30','en'],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            until=time.monotonic()+2
            while not marker.exists() and time.monotonic()<until:time.sleep(.01)
            self.assertTrue(marker.exists(),'PTY child did not enter the delayed setsid')
            child=int(marker.read_text())
            self.assertIsNone(process.poll(),'launcher reported ready before the PTY child created its group')
            brokers=[]
            for path in Path('/proc').iterdir():
                if not path.name.isdigit() or int(path.name) in [process.pid,child]:continue
                try:args=(path/'cmdline').read_bytes().split(b'\0')
                except OSError:continue
                if args[:2]==[os.fsencode(self.helper),os.fsencode(self.run)]:brokers.append(int(path.name))
            self.assertEqual(len(brokers),1)
            os.kill(brokers[0],signal.SIGTERM)
            process.communicate(timeout=3)
            self.assertNotEqual(process.returncode,0)
            status=Path(f'/proc/{child}/stat')
            if status.exists():self.assertEqual(status.read_text().split(') ')[1][0],'Z')
        finally:
            for path in Path('/proc').iterdir():
                if not path.name.isdigit():continue
                try:args=(path/'cmdline').read_bytes().split(b'\0')
                except OSError:continue
                if args[:2]==[os.fsencode(self.helper),os.fsencode(self.run)]:
                    try:os.kill(int(path.name),signal.SIGKILL)
                    except ProcessLookupError:pass
            process.communicate(timeout=3)

    def test_natural_exit_keeps_leader_unreaped_until_group_signals_finish(self):
        log=Path(self.tmp.name)/'group-signals'
        self.launch(env=os.environ|{'LD_PRELOAD':str(self.probe),'DPI_TEST_KILL_LOG':str(log)})
        self.poll_until(b'CWD=');self.request(b'I 1\nq')
        until=time.monotonic()+2
        while time.monotonic()<until:
            if self.request(b'P 0\n')[0]=='exited':break
            time.sleep(.02)
        self.assertEqual(log.read_text().splitlines(),['15 Z','9 Z'])

    def test_immediate_open_stop_never_hangs(self):
        for _ in range(12):
            self.launch()
            self.assertEqual(self.request(b'S\n')[0],'stopped')
            until=time.monotonic()+1
            while (self.run/'control.sock').exists() and time.monotonic()<until:time.sleep(.005)
            self.assertFalse((self.run/'control.sock').exists())
            for name in ['output','status']:(self.run/name).unlink()

    def test_exit_and_broker_signal_kill_descendants_and_release_inherited_locks(self):
        lease_path=Path(self.tmp.name)/'inherited.lock'
        with lease_path.open('w') as lease:
            fcntl.flock(lease,fcntl.LOCK_EX)
            r=subprocess.run([str(self.helper),str(self.run),str(self.detector),str(self.detector.parent),'100','30','en'],pass_fds=(lease.fileno(),),timeout=5)
            self.assertEqual(r.returncode,0)
        self.addCleanup(self.stop)
        with lease_path.open('w') as lease:
            fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
        self.poll_until(b'CWD=');self.request(b'I 1\nd')
        _,_,_,out=self.poll_until(b'CHILD=');child=int(out.split(b'CHILD=')[1].split()[0])
        brokers=[]
        for path in Path('/proc').iterdir():
            if not path.name.isdigit():continue
            try:args=(path/'cmdline').read_bytes().split(b'\0')
            except OSError:continue
            if args[:2]==[os.fsencode(self.helper),os.fsencode(self.run)]:brokers.append(int(path.name))
        self.assertEqual(len(brokers),1)
        os.kill(brokers[0],signal.SIGTERM)
        until=time.monotonic()+3
        while (self.run/'control.sock').exists() and time.monotonic()<until:time.sleep(.025)
        self.assertFalse((self.run/'control.sock').exists())
        self.assertTrue((self.run/'status').read_text().startswith('stopped '))
        status=Path(f'/proc/{child}/stat')
        if status.exists():self.assertEqual(status.read_text().split(') ')[1][0],'Z')

    def test_symlinks_nonprivate_runtime_and_extra_arguments_rejected(self):
        for mode in [0o755, 0o777]:
            self.run.chmod(mode)
            r = subprocess.run([str(self.helper), str(self.run), str(self.detector), str(self.detector.parent), '80', '24', 'en'], timeout=5)
            self.assertNotEqual(r.returncode, 0)
        self.run.chmod(0o700)
        (self.run / 'output').symlink_to(self.detector)
        r = subprocess.run([str(self.helper), str(self.run), str(self.detector), str(self.detector.parent), '80', '24', 'en'], timeout=5)
        self.assertNotEqual(r.returncode, 0)


if __name__ == '__main__':
    unittest.main()

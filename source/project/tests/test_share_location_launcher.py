"""Real executable boundary: native DNS cannot outlive CGI or its own budget."""
import os,signal,subprocess,tempfile,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class LocationLauncherTests(unittest.TestCase):
    def test_independent_deadline_and_parent_death_kill_worker(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);exe=p/'guard';source=ROOT/'asus/share/location-launch.c'
            r=subprocess.run(['cc','-Os','-nostdlib','-static','-fno-stack-protector','-fno-pie','-no-pie','-DLOCATION_MILLISECONDS=250',str(source),'-o',str(exe)],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertEqual(subprocess.run([exe,'/bin/true']).returncode,0)
            worker='import os,time,sys;open(sys.argv[1],"w").write(str(os.getpid()));time.sleep(20)'
            def alive(pid):
                try:return Path(f'/proc/{pid}/stat').read_text().split()[2]!='Z'
                except FileNotFoundError:return False
            for death in [False,True]:
                marker=p/str(death)
                parent=subprocess.Popen(['python3','-c','import subprocess,sys,time;subprocess.Popen(sys.argv[1:]);time.sleep(20)',str(exe),'/usr/bin/python3','-c',worker,str(marker)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                try:
                    end=time.monotonic()+2
                    while not marker.exists() and time.monotonic()<end:time.sleep(.01)
                    self.assertTrue(marker.exists());pid=int(marker.read_text())
                    if death:parent.kill();parent.wait(timeout=1)
                    end=time.monotonic()+2
                    while alive(pid) and time.monotonic()<end:time.sleep(.01)
                    self.assertFalse(alive(pid),'child survived CGI death or independent deadline')
                finally:
                    if parent.poll() is None:parent.kill();parent.wait(timeout=1)

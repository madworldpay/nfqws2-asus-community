"""Pinned Entware ash must not preserve core/update leases in its wrapper."""
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
TOOLS=ROOT/'.work/packaging-audit-20261012'
CACHE=Path(os.environ.get('ASUS_ASSET_CACHE',str(ROOT/'.work/asus-asset-cache')))
CASES={
    'aarch64':('qemu-aarch64','aarch64-sysroot','busybox_1.37.0-6_aarch64-3.10.ipk'),
    'armv7_modern':('qemu-arm','armv7-sysroot','busybox_1.37.0-6_armv7-3.2.ipk'),
    'armv7_legacy':('qemu-arm','armv7-legacy-sysroot','busybox_1.36.1-1b_armv7-2.6.ipk'),
}


class IpHealthWorkerFdTests(unittest.TestCase):
    def verify(self,family):
        emulator,sysroot,archive=CASES[family];emulator=TOOLS/emulator;sysroot=TOOLS/sysroot;busybox=sysroot/'opt/bin/busybox';package=CACHE/archive
        if not all(path.is_file() for path in [emulator,busybox,package]):self.skipTest('pinned BusyBox IPK and matching QEMU/sysroot required')
        pins=json.loads((ROOT/'asus/assets.json').read_text())
        self.assertEqual(hashlib.sha256(package.read_bytes()).hexdigest(),pins[archive]['sha256'])
        with tarfile.open(package) as outer:
            data=next(m for m in outer if m.name.removeprefix('./')=='data.tar.gz')
            with tarfile.open(fileobj=io.BytesIO(outer.extractfile(data).read()),mode='r:gz') as payload:
                member=next(m for m in payload if m.name.removeprefix('./')=='opt/bin/busybox')
                self.assertEqual(busybox.read_bytes(),payload.extractfile(member).read(),'execute exact pinned payload bytes')
        with tempfile.TemporaryDirectory(prefix='nfqws-health-fds-'+family+'-') as folder:
            root=Path(folder);private=root/'private';private.mkdir();public=root/'public';(public/'events').mkdir(parents=True)
            (root/'runtime.conf').write_text('STRATEGY=preserved\n');(root/'pid').write_text('41\n')
            helper=root/'worker.py';helper.write_text('''import json,os,sys,time
from pathlib import Path
root=Path(sys.argv[1]);ready=root/'worker.json.new';ready.write_text(json.dumps({'pid':os.getpid(),'wrapper':os.getppid()}));ready.replace(root/'worker.json')
while True:time.sleep(.05)
''')
            observer=root/'observer';observer.write_text('#!/bin/sh\nfor arg; do case "$arg" in --pidfile=*) printf "%s\\n" "$$" > "${arg#--pidfile=}";; esac; done\n');observer.chmod(0o700)
            script=root/'start.sh';script.write_text('''set -f
. '''+shlex.quote(str(ROOT/'ip-health/runtime.sh'))+'''
RUN_DIR='''+shlex.quote(str(root))+'''
PIDFILE="$RUN_DIR/pid";NFQUEUE_NUM=300;IPV6_ENABLED=0;ASUS_WAN=eth0
ASUS_HEALTH_PRIVATE="$RUN_DIR/private";ASUS_HEALTH_PUBLIC="$RUN_DIR/public"
ASUS_HEALTH_LIB='''+shlex.quote(str(ROOT/'ip-health'))+'''
NFQWS_BIN='''+shlex.quote(str(observer))+'''
USER='''+shlex.quote(str(os.getuid()))+'''
asus_running() { return 0; }
asus_ip_health_directory() { return 0; }
asus_ip_health_stop() { return 0; }
asus_interface_valid() { return 0; }
asus_ip_health_firewall_family() { return 0; }
nvram() { [ "$2" != lan_ifname ] || echo br0; }
ip() { echo 'eth0 inet 93.184.216.34'; }
awk() { case "$*" in *nfnetlink_queue*) return 1;; *) /usr/bin/awk "$@";; esac; }
asus_ip_health_php() {
    case "$1" in healthy) return 1;; loop) '''+shlex.join([sys.executable,str(helper),str(root)])+''';; *) return 0;; esac
}
exec 7>"$RUN_DIR/scheduler.lock" 8>"$RUN_DIR/update.lock" 9>"$RUN_DIR/control.lock"
/usr/bin/flock -x 7 && /usr/bin/flock -x 8 && /usr/bin/flock -x 9 || exit 1
asus_ip_health_start || exit 2
: > "$RUN_DIR/parent-ready"
while [ ! -f "$RUN_DIR/parent-release" ]; do sleep .02; done
''')
            with (root/'caller.stdout').open('wb') as out,(root/'caller.stderr').open('wb') as err:
                parent=subprocess.Popen([str(emulator),'-L',str(sysroot),str(busybox),'sh',str(script)],stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True)
                try:
                    deadline=time.monotonic()+4
                    while not ((root/'worker.json').exists() and (root/'parent-ready').exists()) and time.monotonic()<deadline:
                        if parent.poll() is not None:break
                        time.sleep(.01)
                    self.assertTrue((root/'worker.json').exists(),(root/'caller.stderr').read_text())
                    info=json.loads((root/'worker.json').read_text());self.assertNotEqual(info['wrapper'],parent.pid,'persistent function wrapper reproduced')
                    leases={(os.stat(root/name).st_dev,os.stat(root/name).st_ino) for name in ['scheduler.lock','update.lock','control.lock']}
                    def inherited(pid):
                        found={}
                        for descriptor in (Path('/proc')/str(pid)/'fd').iterdir():
                            try:
                                value=descriptor.stat()
                                if (value.st_dev,value.st_ino) in leases:found[descriptor.name]=os.readlink(descriptor)
                            except FileNotFoundError:pass
                        return found
                    self.assertEqual(set(inherited(parent.pid)),{'7','8','9'},'caller keeps its original leases until it exits')
                    (root/'parent-release').touch();parent.wait(timeout=2);self.assertEqual(parent.returncode,0,(root/'caller.stderr').read_text())
                    for role in ['wrapper','pid']:
                        self.assertEqual(inherited(info[role]),{},role+' must hold no lease inode at any FD number')
                    for name in ['scheduler.lock','update.lock','control.lock']:
                        with (root/name).open('a') as lease:fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    os.killpg(parent.pid,signal.SIGHUP);time.sleep(.05)
                    for role in ['wrapper','pid']:os.kill(info[role],0)
                    for role in ['wrapper','pid']:
                        self.assertEqual(os.readlink(Path('/proc')/str(info[role])/'fd/0'),'/dev/null')
                        for descriptor in ['1','2']:self.assertEqual(Path(os.readlink(Path('/proc')/str(info[role])/'fd'/descriptor)),private/'worker.log')
                    self.assertEqual((root/'runtime.conf').read_text(),'STRATEGY=preserved\n')
                    os.kill(info['pid'],signal.SIGTERM)
                    deadline=time.monotonic()+2
                    while time.monotonic()<deadline:
                        try:
                            if (Path('/proc')/str(info['wrapper'])/'stat').read_text().split(') ',1)[1].split()[0] in ['Z','X']:break
                        except FileNotFoundError:break
                        time.sleep(.01)
                    else:self.fail('function wrapper must exit naturally when its registered worker exits')
                finally:
                    try:os.killpg(parent.pid,signal.SIGTERM)
                    except ProcessLookupError:pass
                    try:parent.wait(timeout=1)
                    except subprocess.TimeoutExpired:os.killpg(parent.pid,signal.SIGKILL);parent.wait()

    def test_aarch64_worker_and_wrapper_drop_all_lease_aliases(self):self.verify('aarch64')
    def test_armv7_modern_worker_and_wrapper_drop_all_lease_aliases(self):self.verify('armv7_modern')
    def test_armv7_legacy_worker_and_wrapper_drop_all_lease_aliases(self):self.verify('armv7_legacy')


if __name__=='__main__':unittest.main()

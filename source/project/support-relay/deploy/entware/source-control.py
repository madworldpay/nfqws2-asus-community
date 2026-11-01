#!/opt/bin/python3
"""Own two bounded daemons. PID files never authorize signalling another service."""
import ctypes,fcntl,hashlib,json,os,resource,signal,stat,subprocess,sys,time
from pathlib import Path
FRONT=Path('/opt/var/run/nfqws-source-frontend')
RELAY=Path('/opt/var/run/nfqws-source-relay')
UPLOAD=Path('/opt/var/run/nfqws-source-body')
CONF='/opt/etc/nfqws-source/lighttpd.conf'
LIGHT='/opt/sbin/lighttpd'
PYTHON='/opt/bin/python3'
UID=65123

def run(args,**kw):
    return subprocess.run(args,check=True,timeout=15,**kw)

def pid(kind):
    file=(FRONT/'lighttpd.pid') if kind=='front' else (RELAY/'gunicorn.pid')
    try:
        s=file.lstat()
        if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1 or s.st_size>32 or s.st_uid not in (0,UID):return None
        value=file.read_text().strip()
        if not value.isdigit() or int(value)<=1:return None
        n=int(value);p=Path('/proc')/value
        status=dict(x.split(':',1) for x in (p/'status').read_text().splitlines() if ':' in x)
        expected=65534 if kind=='front' else UID
        if any(int(x)!=expected for x in status['Uid'].split()):return None
        command=(p/'cmdline').read_bytes()
        if kind=='front':
            if not os.path.samefile(p/'exe',LIGHT) or CONF.encode() not in command.split(b'\0'):return None
        elif b'nfqws_support.entware:load_app()' not in command or b'gunicorn' not in command:return None
        return n
    except (OSError,ValueError,KeyError):return None

def stop(kind):
    n=pid(kind)
    if n is None:return
    os.kill(n,signal.SIGTERM)
    for _ in range(100):
        if pid(kind)!=n:return
        time.sleep(.1)
    # No SIGKILL escalation: SMTP children use parent-death and lease semantics.
    raise RuntimeError('Owned service did not stop')

def harden():
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    if ctypes.CDLL(None,use_errno=True).prctl(38,1,0,0,0):
        raise RuntimeError('no_new_privs unavailable')

def front():
    run([LIGHT,'-tt','-f',CONF],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if not pid('front'):
        run([LIGHT,'-f',CONF],preexec_fn=harden)
    stamp=FRONT/'certificate.sha256'
    digest=hashlib.sha256(Path('/etc/cert.pem').read_bytes()).hexdigest()
    if not stamp.exists() or stamp.read_text()!=digest:stamp.write_text(digest)

def relay():
    if pid('relay'):return
    env={'PATH':'/opt/sbin:/opt/bin:/usr/sbin:/usr/bin:/sbin:/bin',
         'PYTHONPATH':'/opt/lib/nfqws-source/vendor:/opt/lib/nfqws-source/support-relay/src',
         'SSL_CERT_FILE':'/opt/etc/ssl/certs/ca-certificates.crt'}
    run([PYTHON,'-m','gunicorn','--daemon','--preload','--bind','127.0.0.1:8875',
         '--workers','1','--worker-class','sync','--timeout','25','--user',str(UID),'--group',str(UID),
         '--pid',str(RELAY/'gunicorn.pid'),'--worker-tmp-dir',str(RELAY),
         '--error-logfile','/dev/null','--chdir','/opt/lib/nfqws-source','nfqws_support.entware:load_app()'],env=env)
    for _ in range(40):
        if pid('relay'):return
        time.sleep(.1)
    raise RuntimeError('Mail receiver failed to start')

def prepare():
    if os.geteuid()!=0:raise RuntimeError('Root required')
    os.umask(0o077)
    parent=UPLOAD.parent.lstat()
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid!=0 or parent.st_mode&0o022 or not parent.st_mode&0o001:
        raise RuntimeError('Unsafe upload parent')
    # Large HTTP bodies spill to disk after 64 KiB. The unprivileged frontend
    # needs its own private spool outside the root-only control/PID directory.
    for directory,owner in [(FRONT,0),(RELAY,UID),(UPLOAD,65534),(Path('/opt/var/lib/nfqws-support'),UID)]:
        if directory.is_symlink():raise RuntimeError('Runtime directory cannot be a symlink')
        directory.mkdir(parents=True,exist_ok=True)
        directory.chmod(0o700);os.chown(directory,owner,owner)
    vendor=Path('/opt/etc/init.d/S80lighttpd')
    if vendor.exists():vendor.chmod(vendor.stat().st_mode&~0o111)
    # Stock certificate bytes are unchanged; remove world write permission.
    Path('/etc/cert.pem').chmod(0o644)


def main(action):
    if action=='status':
        print(json.dumps({'catalog_pid':pid('front'),'mail_pid':pid('relay')}));return
    prepare()
    with (FRONT/'control.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        if action=='stop':stop('front');stop('relay');return
        if action=='restart':stop('front');stop('relay')
        if action in ('start','restart','check'):
            stamp=FRONT/'certificate.sha256'
            changed=stamp.exists() and stamp.read_text()!=hashlib.sha256(Path('/etc/cert.pem').read_bytes()).hexdigest()
            if changed:
                run([LIGHT,'-tt','-f',CONF],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                stop('front')
            # A mail outage must not prevent download of already approved profiles.
            front()
            relay()
            run([PYTHON,'-m','nfqws_support.cleanup','--entware'],env={
                'PATH':'/opt/bin:/usr/bin:/bin',
                'PYTHONPATH':'/opt/lib/nfqws-source/vendor:/opt/lib/nfqws-source/support-relay/src'})
        elif action!='status':raise RuntimeError('Unknown action')
        print(json.dumps({'catalog_pid':pid('front'),'mail_pid':pid('relay')}))

if __name__=='__main__':
    try:main(sys.argv[1] if len(sys.argv)==2 else '')
    except Exception:
        print('NFQWS source service check failed',file=sys.stderr)
        raise SystemExit(1)

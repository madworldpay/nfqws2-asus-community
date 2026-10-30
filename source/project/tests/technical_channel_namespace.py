#!/usr/bin/env python3
"""Opt-in isolated channel acceptance. Run in fresh root mount+network namespaces.

Input JSON supplies project, php, qemu, merlin_binary, merlin_root, busybox,
busybox_root and private work paths. Router binaries stay outside the repository.
Only discovery paths are adapted because QEMU reports its own /proc executable.
All SSH traffic remains inside a network namespace with no external interface.
"""
import atexit
import base64
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys
import tempfile
import time
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import ed25519,padding,rsa

cfg=json.loads(Path(sys.argv[1]).read_text())
assert os.geteuid()==0 and all(Path('/proc/self/ns/'+kind).readlink()!=Path('/proc/1/ns/'+kind).readlink() for kind in ['net','mnt']),'fresh root mount and network namespaces required'
parent=Path(cfg['work']);parent.mkdir(parents=True,exist_ok=True)
work=Path(tempfile.mkdtemp(prefix='acceptance-',dir=parent));mounted=[]
def cleanup():
    for target in reversed(mounted):subprocess.run(['umount',target],check=False,capture_output=True)
    shutil.rmtree(work,ignore_errors=True)
atexit.register(cleanup)
subprocess.run(['mount','--make-rprivate','/'],check=True)
opt=work/'opt';tmp=work/'tmp'
for path in [opt,tmp]:path.mkdir(exist_ok=True);path.chmod(0o755 if path==opt else 0o777)
sshd_record=pwd.getpwnam('sshd');passwd=work/'passwd';passwd.write_text(f'root:x:0:0:root:/tmp/home/root:/bin/sh\nnfqs-aaaaaaaaaaaa:x:23991:23991:relay:/var/empty:/usr/sbin/nologin\nsshd:x:{sshd_record.pw_uid}:{sshd_record.pw_gid}:sshd:/run/sshd:/usr/sbin/nologin\n')
shadow=work/'shadow';shadow.write_text('root:*:20000:0:99999:7:::\nnfqs-aaaaaaaaaaaa:*:20000:0:99999:7:::\n');shadow.chmod(0o600)
for source,target in [(opt,'/opt'),(tmp,'/tmp'),(passwd,'/etc/passwd'),(shadow,'/etc/shadow')]:
    subprocess.run(['mount','--bind',str(source),target],check=True);mounted.append(target)
subprocess.run(['ip','link','set','lo','up'],check=True);subprocess.run(['ip','addr','add','94.103.80.201/32','dev','lo'],check=True)
for p in ['/opt/bin','/opt/share/nfqws-asus-web','/opt/share/nfqws2-asus','/opt/lib/nfqws2-asus/technical-channel','/opt/etc/nfqws-asus-web','/opt/fixture-proc/999','/tmp/home/root/.ssh']:
    Path(p).mkdir(parents=True,exist_ok=True);Path(p).chmod(0o700)
Path('/opt/etc/passwd').symlink_to('/etc/passwd');Path('/opt/etc/shadow').symlink_to('/etc/shadow')
project=Path(cfg['project']);public=Path('/opt/share/nfqws-asus-web')
for src in (project/'webui/web/public').glob('*.php'):shutil.copyfile(src,public/src.name)
# QEMU is the kernel-visible executable; substitute only daemon discovery.
runtime=public/'technical-channel-runtime.php';text=runtime.read_text().replace("glob('/proc/[0-9]*/comm')","glob('/opt/fixture-proc/[0-9]*/comm')").replace("readlink('/proc/'.$pid.'/exe')","readlink('/opt/fixture-proc/'.$pid.'/exe')").replace("file_get_contents('/proc/'.$pid.'/cmdline')","file_get_contents('/opt/fixture-proc/'.$pid.'/cmdline')").replace("'/usr/bin/ssh'","'/opt/bin/dbclient'");runtime.write_text(text.replace("        if($state==='failed'){","        if($state==='failed'){file_put_contents('/opt/fixture-failure.log',@file_get_contents($this->path('ssh.log')));"))
for src in (project/'asus/technical-channel').iterdir():shutil.copyfile(src,Path('/opt/lib/nfqws2-asus/technical-channel')/src.name)
for name in ['session.sh','guard.sh']:Path('/opt/lib/nfqws2-asus/technical-channel',name).chmod(0o700)
Path('/opt/bin/php-cgi').write_text('#!/bin/sh\nexec '+cfg['php']+' -n "$@"\n');Path('/opt/bin/php-cgi').chmod(0o700)
# Use complete actual binaries and libraries; wrappers only bridge CPU ABIs.
def wrapper(path,binary,root,applet=None):
    Path(path).write_text('#!/bin/sh\nexec '+cfg['qemu']+' -L '+root+(' -0 dropbearmulti' if binary==cfg['merlin_binary'] else '')+' '+binary+(' '+applet if applet else '')+' "$@"\n');Path(path).chmod(0o700)
wrapper('/opt/bin/dropbearmulti',cfg['merlin_binary'],cfg['merlin_root'])
wrapper('/opt/bin/dbclient',cfg['merlin_binary'],cfg['merlin_root'],'dbclient')
Path('/opt/libexec/nfqws2-asus').mkdir(parents=True)
wrapper('/opt/libexec/nfqws2-asus/busybox',cfg['busybox'],cfg['busybox_root'])
# Entware's busybox ELF interpreter is absolute /opt/lib, not QEMU -L relative.
for src in (Path(cfg['busybox_root'])/'opt/lib').iterdir():
    if src.is_file():shutil.copy2(src,Path('/opt/lib')/src.name)
qemu=[cfg['qemu'],'-L',cfg['merlin_root'],'-0','dropbearmulti',cfg['merlin_binary']]
keyout=subprocess.run(qemu+['dropbearkey','-t','ed25519','-f','/opt/hostkey'],check=True,text=True,capture_output=True).stdout
hostpub=next(x for x in keyout.splitlines() if x.startswith('ssh-ed25519 ')).split()[:2];hostpub=' '.join(hostpub)
Path('/opt/fixture-proc/999/comm').write_text('dropbear\n');Path('/opt/fixture-proc/999/exe').symlink_to('/opt/bin/dropbearmulti');Path('/opt/fixture-proc/999/cmdline').write_bytes(b'/usr/sbin/dropbear\0-r\0/opt/hostkey\0')
subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f','/opt/operator'],check=True)
operator=' '.join(Path('/opt/operator.pub').read_text().split()[:2])
signer=rsa.generate_private_key(public_exponent=65537,key_size=2048)
Path('/opt/share/nfqws2-asus/technical-channel-public.pem').write_bytes(signer.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo));Path('/opt/share/nfqws2-asus/technical-channel-public.pem').chmod(0o600)
subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f','/opt/relay-host'],check=True)
relaypub=' '.join(Path('/opt/relay-host.pub').read_text().split()[:2])
seed=ed25519.Ed25519PrivateKey.generate();private=seed.private_bytes(serialization.Encoding.Raw,serialization.PrivateFormat.Raw,serialization.NoEncryption());pub=seed.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
tunnel=base64.b64encode(b'\0\0\0\x0bssh-ed25519\0\0\0\x40'+private+pub).decode();tunnelpub=seed.public_key().public_bytes(serialization.Encoding.OpenSSH,serialization.PublicFormat.OpenSSH).decode()
Path('/opt/relay-key').write_text('restrict,port-forwarding,permitlisten="127.0.0.1:44900" '+tunnelpub+'\n');Path('/opt/relay-key').chmod(0o644)
Path('/opt/relay.conf').write_text('Port 22022\nListenAddress 94.103.80.201\nHostKey /opt/relay-host\nPidFile /opt/relay.pid\nUsePAM no\nStrictModes no\nLogLevel VERBOSE\nMatch User nfqs-aaaaaaaaaaaa\n AuthorizedKeysFile /opt/relay-key\n AuthenticationMethods publickey\n PasswordAuthentication no\n KbdInteractiveAuthentication no\n MaxSessions 0\n AllowTcpForwarding remote\n PermitListen 127.0.0.1:44900\n PermitOpen none\n GatewayPorts no\n ClientAliveInterval 15\n ClientAliveCountMax 2\nMatch all\n')
relaylog=open('/opt/relay.log','w');relay=subprocess.Popen(['/usr/sbin/sshd','-D','-e','-f','/opt/relay.conf'],stdout=relaylog,stderr=relaylog)
call="require '/opt/share/nfqws-asus-web/technical-channel.php';$c=new AsusTechnicalChannel();try{if($argv[1]==='start')$r=$c->start(stream_get_contents(STDIN));else $r=$c->{$argv[1]}();echo json_encode($r);}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);exit(1);}"
def api(mode,link=None):
    p=subprocess.run([cfg['php'],'-n','-r',call,mode],input=link,text=True,capture_output=True,timeout=12)
    assert not p.stderr,p.stderr
    result=json.loads(p.stdout);assert p.returncode==0,result
    return result

def invitation(seconds=30,host_key=None):
    now=int(time.time());v=dict(schema_version=1,purpose='technical_channel',session_id='a'*32,issued_at=now-1,expires_at=now+seconds,server='94.103.80.201',server_port=22022,server_user='nfqs-aaaaaaaaaaaa',remote_port=44900,host_key=host_key or relaypub,operator_key=operator,tunnel_key=tunnel)
    raw=json.dumps(v,separators=(',',':')).encode();b64=lambda x:base64.urlsafe_b64encode(x).decode().rstrip('=')
    return 'https://github.com/madworldpay/nfqws2-asus-community#technical-channel=v1.'+b64(raw)+'.'+b64(signer.sign(raw,padding.PKCS1v15(),hashes.SHA256()))

def operator_args(command):
    return ['/usr/bin/ssh','-F','/dev/null','-oBatchMode=yes','-oStrictHostKeyChecking=yes','-oUserKnownHostsFile=/opt/operator-known','-oConnectTimeout=2','-oIdentityAgent=none','-i','/opt/operator','-p','44900','root@127.0.0.1',command]
def operator_command(command):
    return subprocess.run(operator_args(command),capture_output=True,text=True,timeout=7)
Path('/opt/operator-known').write_text('[127.0.0.1]:44900 '+hostpub+'\n');Path('/opt/operator-known').chmod(0o600)
keys=Path('/tmp/home/root/.ssh/authorized_keys');known=Path('/tmp/home/root/.ssh/known_hosts');keys.write_bytes(b'original-without-newline');keys.chmod(0o640)

def ready():
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        s=api('status')
        if s['state']=='failed':raise AssertionError((s,Path('/opt/fixture-failure.log').read_text() if Path('/opt/fixture-failure.log').exists() else '',Path('/opt/relay.log').read_text()))
        p=operator_command('printf channel-ok')
        if p.returncode==0:
            assert p.stdout=='channel-ok',(p.stdout,p.stderr);return
        time.sleep(.2)
    raise AssertionError(('operator did not connect',s,p.returncode,p.stderr,Path('/opt/relay.log').read_text()))

def restored():
    assert keys.read_bytes()==b'original-without-newline',keys.read_bytes()
    assert keys.stat().st_mode&0o777==0o640
    assert not known.exists()
    assert Path('/tmp').stat().st_mode&0o7777==0o777
    assert not Path('/opt/etc/nfqws-asus-web/technical-channel/journal.json').exists()
    assert not Path('/opt/etc/nfqws-asus-web/technical-channel/journal.json.permissions').exists()
    assert not Path('/tmp/nfqws2-technical-channel/tunnel.key').exists()
try:
    time.sleep(.2)
    applets=subprocess.run(['/opt/libexec/nfqws2-asus/busybox','--list'],check=True,text=True,capture_output=True).stdout.splitlines()
    assert all(x in applets for x in ['sh','start-stop-daemon','usleep']) and 'setsid' not in applets and 'timeout' not in applets
    assert api('start',invitation())['state']=='connecting';ready();assert api('status')['state']=='connected';long=subprocess.Popen(operator_args('touch /opt/command-started; (sleep 3; touch /opt/survived-stop) & wait'),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    deadline=time.monotonic()+5
    while not Path('/opt/command-started').exists() and time.monotonic()<deadline:time.sleep(.05)
    assert Path('/opt/command-started').exists(),'actual command did not start'
    assert api('stop')['state']=='stopped';long.communicate(timeout=5);time.sleep(3.1);assert not Path('/opt/survived-stop').exists(),'actual command descendant survived stop';restored();print('PASS actual Merlin + packaged BusyBox start/operator/stop and exact permissions/key rollback',flush=True)
    assert api('start',invitation(4))['state']=='connecting';ready();time.sleep(4.2);assert api('status')['state']=='expired';restored();print('PASS signed expiry closes actual transport and restores exact state',flush=True)
    assert api('start',invitation())['state']=='connecting';ready();state=json.loads(Path('/tmp/nfqws2-technical-channel/state.json').read_text());os.kill(state['identity']['pid'],9);time.sleep(1);assert api('status')['state']=='failed';restored();print('PASS worker crash guardian restores exact state',flush=True)
    badhost=ed25519.Ed25519PrivateKey.generate().public_key().public_bytes(serialization.Encoding.OpenSSH,serialization.PublicFormat.OpenSSH).decode()
    assert api('start',invitation(host_key=badhost))['state']=='connecting'
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        failed=api('status')
        if failed['state']=='failed':break
        time.sleep(.1)
    assert failed['state']=='failed' and failed['diagnostic']['reason']=='host_key_mismatch',failed
    restored();print('PASS incorrect signed host pin fails closed and restores exact state',flush=True)
finally:
    try:api('stop')
    except Exception:pass
    relay.terminate();relay.wait(timeout=5);relaylog.close()

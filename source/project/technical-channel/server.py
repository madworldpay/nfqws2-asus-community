#!/usr/bin/env python3
"""Root-only, per-session OpenSSH tunnel accounts. No router keys or signing secrets."""
import datetime
import json
import os
from pathlib import Path
import pwd
import re
import subprocess
import sys
import time

BASE=Path('/var/lib/nfqws-technical')
KEYS=Path('/etc/ssh/nfqws-technical')
SELF=Path('/usr/local/libexec/nfqws-technical-server.py')

def run(*args):
    return subprocess.run(args,check=True,text=True,capture_output=True).stdout

def paths(sid):
    if not re.fullmatch('[a-f0-9]{32}',sid):raise ValueError('invalid session')
    user='nfqs-'+sid[:12];unit='nfqws-tech-'+sid
    return user,unit,Path('/etc/ssh/sshd_config.d/80-'+unit+'.conf')

def write(path,content,mode=0o600):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,'w') as f:f.write(content);f.flush();os.fsync(f.fileno())

def revoke(sid):
    user,unit,conf=paths(sid);record=BASE/(sid+'.json')
    if not record.is_file():return {'revoked':False}
    data=json.loads(record.read_text())
    try:entry=pwd.getpwnam(user)
    except KeyError:entry=None
    if entry and entry.pw_uid!=data['uid']:raise ValueError('account identity changed')
    if entry:
        subprocess.run(['pkill','-KILL','-u',str(entry.pw_uid)],capture_output=True)
        run('userdel',user)
    subprocess.run(['systemctl','disable','--now',unit+'.timer'],capture_output=True)
    for path in [conf,KEYS/(user+'.pub'),Path('/etc/systemd/system/'+unit+'.timer'),Path('/etc/systemd/system/'+unit+'.service')]:path.unlink(missing_ok=True)
    run('/usr/sbin/sshd','-t');run('systemctl','reload','ssh');run('systemctl','daemon-reload')
    record.unlink();return {'revoked':True}

def provision(data):
    sid=data['session_id'];user,unit,conf=paths(sid)
    port=data['remote_port'];expires=data['expires_at'];key=data['client_key']
    if type(port)!=int or not 1024<=port<=65535 or type(expires)!=int or not time.time()<expires<=time.time()+86400:raise ValueError('invalid limits')
    if not re.fullmatch(r'ssh-ed25519 [A-Za-z0-9+/]{68}',key):raise ValueError('invalid key')
    try:pwd.getpwnam(user)
    except KeyError:pass
    else:raise ValueError('account exists')
    if f'127.0.0.1:{port} ' in run('ss','-H','-ltn'):raise ValueError('port busy')
    BASE.mkdir(mode=0o700,exist_ok=True);KEYS.mkdir(mode=0o755,exist_ok=True)
    run('useradd','--system','--no-create-home','--home-dir','/var/empty','--shell','/usr/sbin/nologin','--password','*',user)
    uid=pwd.getpwnam(user).pw_uid
    write(BASE/(sid+'.json'),json.dumps({'session_id':sid,'user':user,'uid':uid,'remote_port':port,'expires_at':expires}))
    try:
        stamp=datetime.datetime.fromtimestamp(expires,datetime.timezone.utc)
        write(KEYS/(user+'.pub'),f'restrict,port-forwarding,permitlisten="127.0.0.1:{port}",expiry-time="{stamp:%Y%m%d%H%M%SZ}" {key}\n',0o644)
        write(conf,f'''# Managed temporary NFQWS2 channel {sid}
Match User {user}
    AuthorizedKeysFile {KEYS}/{user}.pub
    AuthenticationMethods publickey
    PubkeyAuthentication yes
    PasswordAuthentication no
    KbdInteractiveAuthentication no
    MaxSessions 0
    AllowTcpForwarding remote
    PermitListen 127.0.0.1:{port}
    PermitOpen none
    GatewayPorts no
    AllowStreamLocalForwarding no
    AllowAgentForwarding no
    X11Forwarding no
    PermitTTY no
    PermitTunnel no
Match all
''',0o600)
        write(Path('/etc/systemd/system/'+unit+'.service'),f'[Unit]\nDescription=Revoke temporary NFQWS2 channel {sid}\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 {SELF} revoke {sid}\n')
        write(Path('/etc/systemd/system/'+unit+'.timer'),f'[Unit]\nDescription=Expire temporary NFQWS2 channel {sid}\n[Timer]\nOnCalendar={stamp:%Y-%m-%d %H:%M:%S} UTC\nPersistent=true\n[Install]\nWantedBy=timers.target\n')
        run('/usr/sbin/sshd','-t')
        effective=run('/usr/sbin/sshd','-T','-C',f'user={user},host=localhost,addr=127.0.0.1')
        required=['maxsessions 0','allowtcpforwarding remote',f'permitlisten 127.0.0.1:{port}','permitopen none','gatewayports no','allowstreamlocalforwarding no','passwordauthentication no','permittty no']
        if not all(line in effective.splitlines() for line in required):raise ValueError('SSH restriction not applied')
        run('systemctl','reload','ssh');run('systemctl','daemon-reload');run('systemctl','enable','--now',unit+'.timer')
        host=Path('/etc/ssh/ssh_host_ed25519_key.pub').read_text().split()[:2]
        return {'user':user,'host_key':' '.join(host),'remote_port':port,'expires_at':expires,'policy_verified':True}
    except BaseException:
        revoke(sid);raise

if __name__=='__main__':
    if os.geteuid()!=0:sys.exit('root required')
    try:
        if sys.argv[1]=='provision':result=provision(json.load(sys.stdin))
        elif sys.argv[1]=='revoke':result=revoke(sys.argv[2])
        else:raise ValueError('invalid action')
        print(json.dumps(result))
    except Exception as e:
        print(json.dumps({'error':str(e)}));sys.exit(1)

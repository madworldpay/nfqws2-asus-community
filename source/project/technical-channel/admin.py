#!/usr/bin/env python3
"""Issue an offline-signed, temporary router channel. Uses the administrator's normal SSH login."""
import argparse
import base64
import ipaddress
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import ed25519,padding

PREFIX='https://github.com/madworldpay/nfqws2-asus-community#technical-channel=v1.'

def b64(raw):return base64.urlsafe_b64encode(raw).decode().rstrip('=')

def private(path,raw):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:f.write(raw)

def issue(args):
    address=ipaddress.ip_address(args.server)
    if address.version!=4 or not address.is_global:raise ValueError('public server IPv4 required')
    if not 1<=args.minutes<=1440:raise ValueError('lifetime 1..1440 minutes')
    signing=serialization.load_pem_private_key(args.signing_key.read_bytes(),password=None)
    args.output.mkdir(mode=0o700,parents=True,exist_ok=True)
    if args.output.is_symlink() or args.output.stat().st_mode&0o077:raise ValueError('output directory must be private (0700)')
    if any(args.output.iterdir()):raise ValueError('output directory must be empty')
    expected=serialization.load_pem_public_key(Path(__file__).with_name('technical-channel-public.pem').read_bytes())
    public=lambda k:k.public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
    if public(signing.public_key())!=public(expected):raise ValueError('wrong invitation signing key')
    sid=secrets.token_hex(16);tunnel=ed25519.Ed25519PrivateKey.generate();operator=ed25519.Ed25519PrivateKey.generate()
    pub=lambda k:k.public_key().public_bytes(serialization.Encoding.OpenSSH,serialization.PublicFormat.OpenSSH).decode()
    seed=tunnel.private_bytes(serialization.Encoding.Raw,serialization.PrivateFormat.Raw,serialization.NoEncryption())
    dbkey=b'\0\0\0\x0bssh-ed25519\0\0\0\x40'+seed+tunnel.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    now=int(time.time());expiry=now+args.minutes*60
    data=dict(session_id=sid,remote_port=args.remote_port,expires_at=expiry,client_key=pub(tunnel))
    # Host verification is mandatory for the normal root SSH connection. No tokens or passwords in arguments.
    ssh=['ssh','-T','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-p',str(args.ssh_port)]
    if args.control_path:ssh+=['-S',str(args.control_path)]
    if args.known_hosts:ssh+=['-o','UserKnownHostsFile='+str(args.known_hosts)]
    ssh+=['root@'+args.server]
    server=(Path(__file__).with_name('server.py')).read_text()
    # Installation is exclusive: refuse a foreign pre-existing helper.
    install="import pathlib,sys,hashlib,os; p=pathlib.Path('/usr/local/libexec/nfqws-technical-server.py'); raw=sys.stdin.buffer.read(); p.parent.mkdir(parents=True,exist_ok=True); assert not p.is_symlink(); assert not p.exists() or p.read_bytes()==raw, 'existing helper differs'; p.write_bytes(raw); p.chmod(0o600)"
    import shlex
    subprocess.run(ssh+['python3 -c '+shlex.quote(install)],input=server,text=True,capture_output=True,check=True)
    r=subprocess.run(ssh+['python3 /usr/local/libexec/nfqws-technical-server.py provision'],input=json.dumps(data),text=True,capture_output=True,check=True)
    result=json.loads(r.stdout)
    payload=dict(schema_version=1,purpose='technical_channel',session_id=sid,issued_at=now,expires_at=expiry,server=args.server,server_port=args.ssh_port,
                 server_user=result['user'],remote_port=args.remote_port,host_key=result['host_key'],operator_key=pub(operator),tunnel_key=base64.b64encode(dbkey).decode())
    raw=json.dumps(payload,separators=(',',':'),sort_keys=True).encode();signature=signing.sign(raw,padding.PKCS1v15(),hashes.SHA256())
    try:
        private(args.output/'CONNECT.txt',(PREFIX+b64(raw)+'.'+b64(signature)+'\n').encode())
        private(args.output/'operator',operator.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.OpenSSH,serialization.NoEncryption()))
        private(args.output/'operator.pub',(pub(operator)+'\n').encode())
        private(args.output/'session.json',(json.dumps({k:v for k,v in payload.items() if k!='tunnel_key'}|{'label':args.label,'policy_verified':result['policy_verified']},indent=2)+'\n').encode())
    except BaseException:
        subprocess.run(ssh+['python3 /usr/local/libexec/nfqws-technical-server.py revoke '+sid],capture_output=True)
        for name in ['CONNECT.txt','operator','operator.pub','session.json']:(args.output/name).unlink(missing_ok=True)
        raise
    print(json.dumps({'session_id':sid,'expires_at':expiry,'files':str(args.output),'remote_listener':'127.0.0.1:'+str(args.remote_port)}))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--server',required=True);p.add_argument('--ssh-port',type=int,default=22)
    p.add_argument('--remote-port',required=True,type=int);p.add_argument('--minutes',type=int,default=60)
    p.add_argument('--label',required=True);p.add_argument('--signing-key',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--control-path',type=Path);p.add_argument('--known-hosts',type=Path)
    issue(p.parse_args())

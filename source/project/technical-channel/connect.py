#!/usr/bin/env python3
"""Discover a router's UID0 login through its pinned, local technical-channel listener."""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import time

MARKER = b'NFQWS2-TECH-META/'
BANNER = re.compile(rb'NFQWS2-TECH-META/1 ([a-f0-9]{32}) ([A-Za-z0-9_][A-Za-z0-9_-]{0,31})')


def parse_banner(raw, session_id):
    if not isinstance(raw, bytes) or len(raw) > 16384 or not isinstance(session_id, str) or not re.fullmatch('[a-f0-9]{32}', session_id):
        raise ValueError('invalid operator metadata')
    lines = [line for line in raw.split(b'\n') if MARKER in line]
    match = BANNER.fullmatch(lines[0]) if len(lines) == 1 else None
    if not match or match[1].decode('ascii') != session_id:
        raise ValueError('operator metadata missing, invalid or from another session; client update may be required')
    return match[2].decode('ascii')


def load_session(directory):
    directory = Path(directory).absolute()
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError('session directory must be private and owned by the operator')
    fd = os.open(directory/'session.json', os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_size > 32768:
            raise ValueError('unsafe session metadata file')
        data = json.load(stream)
    if (not isinstance(data, dict) or data.get('schema_version') != 1 or data.get('purpose') != 'technical_channel'
            or not isinstance(data.get('session_id'), str) or not re.fullmatch('[a-f0-9]{32}', data['session_id'])
            or type(data.get('remote_port')) is not int or not 1024 <= data['remote_port'] <= 65535
            or type(data.get('expires_at')) is not int or data['expires_at'] <= time.time()):
        raise ValueError('invalid or expired session metadata')
    return directory, data


def ssh_base(session, known_hosts, host_alias, ssh='ssh'):
    if not re.fullmatch('[A-Za-z0-9_][A-Za-z0-9_.:-]{0,127}', host_alias):
        raise ValueError('invalid router host key alias')
    pin_path = str(Path(known_hosts).absolute())
    if re.search('[\x00-\x1f\x7f-\x9f]', pin_path) or '${' in pin_path:
        raise ValueError('unsafe router known_hosts path')
    # OpenSSH config quoting preserves Unicode; %% prevents token expansion.
    pin_value = '"'+pin_path.replace('%', '%%').replace('\\', '\\\\').replace('"', '\\"')+'"'
    # No config-derived proxy, password fallback, forwarding or persistent master.
    return [ssh, '-F', '/dev/null', '-T', '-p', str(session['remote_port']),
            '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
            '-o', 'UserKnownHostsFile='+pin_value,
            '-o', 'GlobalKnownHostsFile=/dev/null', '-o', 'HostKeyAlias='+host_alias,
            '-o', 'UpdateHostKeys=no', '-o', 'PasswordAuthentication=no',
            '-o', 'KbdInteractiveAuthentication=no', '-o', 'ForwardAgent=no',
            '-o', 'ClearAllForwardings=yes', '-o', 'ControlMaster=no',
            '-o', 'ControlPath=none', '-o', 'ConnectTimeout=8', '-o', 'LogLevel=INFO']


def discover(session, base):
    if session['expires_at'] <= time.time():
        raise ValueError('session expired')
    # No operator key is offered during discovery. This fixed discovery identity
    # requests SSH "none" authentication only; no shell/channel opens.
    args = base+['-N', '-o', 'PreferredAuthentications=none', '-o', 'PubkeyAuthentication=no',
                 '-l', 'nfqws-metadata', '127.0.0.1']
    with tempfile.TemporaryFile() as diagnostic:
        result = subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=diagnostic, timeout=12, check=False)
        diagnostic.seek(0)
        raw = diagnostic.read(16385)
    if result.returncode != 255:
        raise ValueError('metadata probe must end without authentication')
    login = parse_banner(raw, session['session_id'])
    if session['expires_at'] <= time.time():
        raise ValueError('session expired')
    return login


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session-dir', type=Path, required=True)
    parser.add_argument('--router-known-hosts', type=Path, required=True)
    parser.add_argument('--router-host-key-alias', required=True, help='existing trusted router identity in known_hosts')
    parser.add_argument('--command', help='root shell command; without this option print discovered metadata only')
    args = parser.parse_args()
    try:
        directory, session = load_session(args.session_dir)
        base = ssh_base(session, args.router_known_hosts, args.router_host_key_alias)
        login = discover(session, base)
        if args.command is None:
            print(json.dumps(dict(session_id=session['session_id'], login=login)))
            return 0
        key = directory/'operator'
        info = key.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('unsafe operator key file')
        # OpenSSH reads its key normally; the helper never reads key material.
        return subprocess.call(base+['-o', 'IdentitiesOnly=yes', '-o', 'PreferredAuthentications=publickey',
                                     '-i', str(key), '-l', login, '127.0.0.1', args.command])
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        parser.exit(1, str(error)+'\n')


if __name__ == '__main__':
    raise SystemExit(main())

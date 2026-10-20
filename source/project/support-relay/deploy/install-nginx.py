#!/usr/bin/env python3
"""Stage a new Debian/Ubuntu Nginx without starting its port-80 default site.

Only for a fresh host, after SMTP/TLS prerequisites are satisfied. Existing
Nginx installations and operator service policies require manual integration.
"""
import os
from pathlib import Path
import re
import subprocess
import sys


class InstallError(Exception):
    pass


def install(site, root=Path('/'), run=subprocess.run):
    etc=root/'etc/nginx'
    policy=root/'usr/sbin/policy-rc.d'
    mask=root/'etc/systemd/system/nginx.service'
    if any(p.exists() or p.is_symlink() for p in (etc,policy,mask,mask.with_name('nginx.service.d'))):
        raise InstallError('existing_operator_state')
    query=run(['dpkg-query','-W','-f=${db:Status-Status}','nginx'],capture_output=True,text=True)
    if query.returncode==0: raise InstallError('nginx_already_installed')
    content=Path(site).read_bytes()
    policy.parent.mkdir(parents=True,exist_ok=True)
    mask.parent.mkdir(parents=True,exist_ok=True)
    mask.symlink_to('/dev/null')  # Persistent until validation; a failed stage stays masked.
    try:
        with policy.open('xb') as stream: stream.write(b'#!/bin/sh\nexit 101\n')
        policy.chmod(0o755)
        inode=policy.stat().st_ino
    except BaseException:
        mask.unlink()
        raise
    try:
        run(['systemctl','daemon-reload'],check=True,capture_output=True)
        run(['apt-get','install','--no-install-recommends','nginx','python3-venv'],check=True)
        default=etc/'sites-enabled/default'
        if default.is_symlink() and default.resolve()==(etc/'sites-available/default').resolve():
            default.unlink()  # Only the default introduced by this package install.
        elif default.exists() or default.is_symlink():
            raise InstallError('unexpected_default_site')
        target=etc/'sites-available/nfqws-support.conf'
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as stream: stream.write(content)
        target.chmod(0o600)
        (etc/'sites-enabled').mkdir(exist_ok=True)
        (etc/'sites-enabled/nfqws-support.conf').symlink_to('../sites-available/nfqws-support.conf')
        run(['nginx','-t'],check=True,capture_output=True)
        result=run(['nginx','-T'],check=True,capture_output=True,text=True)
        listeners=re.findall(r'(?m)^\s*listen\s+([^;]+);',result.stdout)
        if listeners!=['443 ssl']: raise InstallError('expected_only_tcp443_tls')
        if not mask.is_symlink() or os.readlink(mask)!='/dev/null':
            raise InstallError('service_mask_changed')
        mask.unlink()
        run(['systemctl','daemon-reload'],check=True,capture_output=True)
        run(['systemctl','enable','--now','nginx'],check=True,capture_output=True)
    finally:
        # Do not remove an operator replacement made during package installation.
        if not policy.is_symlink() and policy.exists() and policy.stat().st_ino==inode:
            policy.unlink()


if __name__=='__main__':
    if os.geteuid()!=0 or len(sys.argv)!=2:
        sys.exit('Run as root with one privately rendered server-block file.')
    try: install(Path(sys.argv[1]))
    except Exception: sys.exit('Nginx staging failed; check privately. Do not unmask before validation.')

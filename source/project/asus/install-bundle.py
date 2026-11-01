#!/usr/bin/env python3
"""Embed the standalone ASUS recovery coordinator and exact shared verifier."""
import argparse
import base64
import gzip
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def render():
    files={}
    def add(name,path,mode=0o600):
        files[name]={'mode':mode,'data':base64.b64encode(path.read_bytes()).decode('ascii')}
    for source in sorted((ROOT/'webui/web/public').glob('*.php')):add('app/'+source.name,source)
    for name,target in [('install-main.php','main.php'),('install-worker.php','worker.php')]:add(target,ROOT/'asus'/name)
    add('resources/package-manifest.schema.json',ROOT/'updates/package-manifest.schema.json')
    add('resources/update-release-key.pem',ROOT/'updates/trusted-release-key.pem')
    launchers=ROOT/'asus/update/bin';record=json.loads((launchers/'launchers.json').read_text())
    if record['source_sha256']!=hashlib.sha256((ROOT/'asus/update/opkg-launch.c').read_bytes()).hexdigest():raise ValueError('Regenerate native launchers before the ASUS installer')
    for family in ['aarch64','armv7']:
        path=launchers/(family+'-opkg-launch')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=record['outputs'][family]['sha256']:raise ValueError('Native launcher digest mismatch')
        add('launchers/'+path.name,path,0o700)
    payload=base64.b64encode(gzip.compress(json.dumps(files,sort_keys=True,separators=(',',':')).encode(),mtime=0)).decode('ascii')
    source=(ROOT/'asus/install-extract.php').read_text()
    return (source.replace('<?php\n',"<?php\nconst NFQWS_ASUS_INSTALL_FILES = '"+payload+"';\n",1)).encode()

def shell():
    marker='NFQWS_ASUS_BUNDLE';code=render().decode()
    if marker in code:raise ValueError('Heredoc delimiter collision')
    result="nfqws_asus_emit_bundle() {\ncat <<'"+marker+"'\n"+code+'\n'+marker+'\n}\n'
    legacy=(ROOT.parent/'installer/install.sh').read_text().split('\nmain() {',1)[0]
    legacy+='\nnfqws_asus_legacy_finish "$@"\n'
    marker='NFQWS_ASUS_LEGACY'
    if marker in legacy:raise ValueError('Legacy heredoc delimiter collision')
    return result+"nfqws_asus_emit_legacy() {\ncat <<'"+marker+"'\n"+legacy+'\n'+marker+'\n}\n'

def embed(path):
    start='# BEGIN GENERATED ASUS RECOVERY INSTALLER\n';end='# END GENERATED ASUS RECOVERY INSTALLER\n'
    source=path.read_text();block=start+shell()+end
    if start in source:
        a=source.index(start);b=source.index(end,a)+len(end);source=source[:a]+block+source[b:]
    else:
        marker='# BEGIN GENERATED NATIVE OPENWRT INSTALLER\n'
        source=source.replace(marker,block+'\n'+marker)
    path.write_text(source)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path);parser.add_argument('--embed',type=Path);args=parser.parse_args()
    if args.embed:embed(args.embed)
    elif args.output:args.output.write_bytes(render())
    else:parser.error('--output or --embed is required')

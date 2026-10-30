#!/usr/bin/env python3
"""Generate the standalone native installer verifier from its actual shared code.

The bootstrap carries this closure in the trusted installer itself. Remote
metadata supplies only signed release data, never additional executable code.
"""
import argparse
import hashlib
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
PUBLIC=ROOT/'webui/web/public'
MODULES=[PUBLIC/name for name in [
    'platform.php','support-json-schema.php','update-manifest.php',
    'openwrt-update-manifest.php','update-store.php','update-lifecycle.php','update-package.php','openwrt-manual-context.php',
    'openwrt-update-environment.php','openwrt-update-package.php',
    'openwrt-update-manager.php','openwrt-apk-trust.php','update-github.php',
]]+[ROOT/'openwrt/install-plan.php',ROOT/'openwrt/install-state.php',ROOT/'openwrt/install-prepare.php',ROOT/'openwrt/install-execute.php']

def literal(text):
    return "'"+text.replace('\\','\\\\').replace("'","\\'")+"'"

def render(public_key=None,entry=False):
    key=(ROOT/'updates/trusted-release-key.pem').read_bytes()if public_key is None else public_key
    if not isinstance(key,bytes)or len(key)>8192 or not key.startswith(b'-----BEGIN PUBLIC KEY-----\n'):
        raise ValueError('A PEM public release key is required')
    key=key.decode('ascii');schema=(ROOT/'updates/openwrt-package-manifest.schema.json').read_text()
    parts=['<?php\n// Generated from shared native installer verification code.\n',
           'interface AsusUpdateSource { public function manifest():array; public function download(array $package,string $destination):void; }\n']
    for source in MODULES:
        raw=source.read_bytes();body=raw.decode('utf-8')
        if not body.startswith('<?php\n'):raise ValueError('Unexpected PHP module: '+str(source.relative_to(ROOT)))
        # Only source-owned top-level includes are flattened. Conditional method
        # bodies retain their normal semantics, and are not bootstrap entrypoints.
        body=re.sub(r'^require_once [^\n]+;\n','',body[6:],flags=re.M)
        parts.append('// '+str(source.relative_to(ROOT))+' sha256='+hashlib.sha256(raw).hexdigest()+'\n'+body+'\n')
    parts+=['const NFQWS_NATIVE_INSTALL_KEY = '+literal(key)+';\n',
            'const NFQWS_NATIVE_INSTALL_SCHEMA = '+literal(schema)+';\n']
    if entry:
        parts+=['const NFQWS_NATIVE_INSTALL_BRIDGE = '+literal(bridge(key.encode()))+';\n', (ROOT/'openwrt/install-main.php').read_text()[6:]]
    return ''.join(parts).encode('utf-8')

def bridge(public_key=None):
    key=(ROOT/'updates/trusted-release-key.pem').read_bytes()if public_key is None else public_key
    trusted='const NFQWS_NATIVE_INSTALL_KEY = '+literal(key.decode())+';\n'
    trusted+='const NFQWS_NATIVE_INSTALL_SCHEMA = '+literal((ROOT/'updates/openwrt-package-manifest.schema.json').read_text())+';\n'
    trusted+='const NFQWS_NATIVE_INSTALL_DISCOVERY = '+literal((PUBLIC/'update-github.php').read_text())+';\n'
    modules=''.join((ROOT/'openwrt'/name).read_text()[6:]+'\n'for name in ['install-local-source.php','install-trust.php'])
    return (ROOT/'openwrt/install-update.php').read_text().replace('try{', trusted+modules+'\ntry{',1)

def shell(public_key=None):
    code=render(public_key,entry=True).decode()
    marker='NFQWS_NATIVE_BUNDLE'
    if marker in code:raise ValueError('Bootstrap heredoc delimiter collision')
    return (ROOT/'openwrt/install-shell.sh').read_text()+'\nnfqws_native_emit_bundle() {\ncat <<\''+marker+'\'\n'+code+'\n'+marker+'\n}\n'+(ROOT/'openwrt/install-entry.sh').read_text()

def embed(path):
    start='# BEGIN GENERATED NATIVE OPENWRT INSTALLER\n';end='# END GENERATED NATIVE OPENWRT INSTALLER\n'
    text=path.read_text();block=start+shell()+end
    if start in text:
        a=text.index(start);b=text.index(end,a)+len(end);text=text[:a]+block+text[b:]
    else:
        marker='# Keep the entry point last so an incomplete piped download cannot run a partial installer.'
        text=text.replace(marker,block+'\n'+marker).replace('main "$@"\n','if [ -f /etc/openwrt_release ]; then nfqws_native_main "$@"; else main "$@"; fi\n')
    path.write_text(text)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);p.add_argument('--embed',type=Path);p.add_argument('--check',action='store_true');args=p.parse_args();
    if args.embed:
        embed(args.embed);return
    if not args.output:p.error('--output or --embed is required')
    data=render()
    if args.check:
        if not args.output.is_file()or args.output.read_bytes()!=data:p.error('Native installer verifier is stale; regenerate it from shared code')
    else:args.output.write_bytes(data)

if __name__=='__main__':main()

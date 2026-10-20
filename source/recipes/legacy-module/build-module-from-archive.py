#!/usr/bin/env python3
"""Archive variant: verify archived upstream blobs and reproduce the legacy backend.

Archive adaptation: source manifest check, empty vendor top-level .config,
one compile job, and an explicit original GNU build-id for path-independent
stripped metadata. Compilation and source flags otherwise match the original.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--source', type=Path, required=True)
p.add_argument('--toolchain', type=Path, required=True)
p.add_argument('--host-libs', type=Path)
a = p.parse_args()
here = Path(__file__).resolve().parent
source = a.source.resolve()
commit = (source/'SOURCE-COMMIT').read_text().strip()
for line in (source/'SOURCE-GIT-BLOBS.tsv').read_text().splitlines():
    mode, expected, name = line.split('\t', 2)
    p = source/name
    data = os.readlink(p).encode() if mode == '120000' else p.read_bytes()
    actual = hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
    if actual != expected:
        raise SystemExit('Archived source differs: '+name)
if commit != '26e1f3f17a2f29ba7cb9013c67142f8a8c8adfd7':
    raise SystemExit('Use the exact384.13_10 source commit')
src = source/'release/src-rt-6.x.4708'
kernel = src/'linux/linux-2.6.36'
# The vendor kernel requires SRCBASE/.config even for external modules.
# All model flags are explicit make arguments below; no router config is used.
(src/'.config').write_text('# Module build: model flags are passed explicitly.\n')
tc = a.toolchain.resolve()
env = {**os.environ, 'LC_ALL': 'C', 'KCONFIG_NOTIMESTAMP': '1'}
env['LD_LIBRARY_PATH'] = str(tc/'lib') + (':' + str(a.host_libs.resolve()) if a.host_libs else '')
common = ['make', '-j1', 'ARCH=arm', 'CROSS_COMPILE='+str(tc/'bin/arm-brcm-linux-uclibcgnueabi-'),
          'SRCBASE='+str(src), 'HOSTCFLAGS=-O2 -fcommon',
          'LDFLAGS_BUILD_ID=--build-id=0x793980be3bebe2b4ac7083dd45c5e6bdb0acaf38', *json.loads((here/'target-flags.json').read_text())]
shutil.copyfile(here/'kernel.config', kernel/'.config')
subprocess.run(common+['oldconfig'], input=b'\n'*512, cwd=kernel, env=env, check=True)
subprocess.run(common+['modules_prepare'], cwd=kernel, env=env, check=True)
shutil.copyfile(here/'Module.symvers', kernel/'Module.symvers')
out = kernel/'community-nfqueue'
out.mkdir(exist_ok=True)
shutil.copyfile(here/'nfnetlink_queue.c', out/'nfnetlink_queue.c')
shutil.copyfile(kernel/'net/netfilter/xt_NFQUEUE.c', out/'xt_NFQUEUE.c')
(out/'Makefile').write_text('obj-m += nfnetlink_queue.o xt_NFQUEUE.o\n')
subprocess.run(common+['M=community-nfqueue', 'modules'], cwd=kernel, env=env, check=True)
result = out/'nfnetlink_queue-stripped.ko'
subprocess.run([str(tc/'bin/arm-brcm-linux-uclibcgnueabi-strip'), '--strip-debug',
                '-o', str(result), str(out/'nfnetlink_queue.ko')], env=env, check=True)
digest = hashlib.sha256(result.read_bytes()).hexdigest()
if digest != '1e5fd88ebf5830d56f6b151de0c791f02b3c3db0a539490fbf32709add0151ab':
    raise SystemExit('Module differs from pinned artifact: '+digest)
print(result)
print(digest)

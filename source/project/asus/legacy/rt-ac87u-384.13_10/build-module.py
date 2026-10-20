#!/usr/bin/env python3
"""Reproduce the exact legacy backend in an expendable upstream worktree."""
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
commit = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
if commit != '26e1f3f17a2f29ba7cb9013c67142f8a8c8adfd7':
    raise SystemExit('Use the exact384.13_10 source commit')
src = source/'release/src-rt-6.x.4708'
kernel = src/'linux/linux-2.6.36'
tc = a.toolchain.resolve()
env = {**os.environ, 'LC_ALL': 'C', 'KCONFIG_NOTIMESTAMP': '1'}
env['LD_LIBRARY_PATH'] = str(tc/'lib') + (':' + str(a.host_libs.resolve()) if a.host_libs else '')
common = ['make', '-j4', 'ARCH=arm', 'CROSS_COMPILE='+str(tc/'bin/arm-brcm-linux-uclibcgnueabi-'),
          'SRCBASE='+str(src), 'HOSTCFLAGS=-O2 -fcommon', *json.loads((here/'target-flags.json').read_text())]
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

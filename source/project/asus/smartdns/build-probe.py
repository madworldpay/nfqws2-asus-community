#!/usr/bin/env python3
"""Reproduce the libc-independent recovery probe using the updater toolchain."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('launcher_build', HERE.parent/'update/build-launchers.py')
shared = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared)


def build_component(output, toolchain, name, manifest):
    output.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    if toolchain:
        env['PATH'] = str(toolchain/'usr/bin') + os.pathsep + env['PATH']
        env['LD_LIBRARY_PATH'] = str(toolchain/'usr/lib/x86_64-linux-gnu')
    source = HERE/(name+'.c')
    flags = shared.FLAGS + ['-Wall', '-Wextra', '-Werror']
    record = {'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'flags': flags, 'outputs': {}}
    for family, (target, options) in shared.TARGETS.items():
        compiler = next((shutil.which(target+'-gcc'+suffix, path=env['PATH'])
                         for suffix in ['', '-15'] if shutil.which(target+'-gcc'+suffix, path=env['PATH'])), None)
        if compiler is None:
            raise RuntimeError('cross compiler unavailable: '+target)
        dest = output/(family+'-'+name)
        subprocess.run([compiler, *options, *flags, str(source), '-o', str(dest)], env=env, check=True)
        record['outputs'][family] = {
            'sha256': hashlib.sha256(dest.read_bytes()).hexdigest(), 'compiler': target+'-gcc',
            'compiler_version': subprocess.check_output([compiler, '-dumpfullversion'], env=env, text=True).strip(),
            'options': options,
        }
    (output/manifest).write_text(json.dumps(record, sort_keys=True, indent=2)+'\n')


def build(output, toolchain=None):
    build_component(output, toolchain, 'dns-probe', 'probes.json')
    build_component(output, toolchain, 'session-owner', 'owners.json')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=HERE/'bin')
    parser.add_argument('--toolchain-root', type=Path)
    args = parser.parse_args()
    build(args.output, args.toolchain_root)

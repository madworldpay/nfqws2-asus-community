#!/usr/bin/env python3
"""Reproduce the pinned compatibility binary from an unmodified upstream tree."""
import argparse
import hashlib
import os
from pathlib import Path
import shlex
import subprocess

TARGET = 'armv5te-unknown-linux-musleabi'
DIGEST = 'c0e0045bab2ae654a9f0fef125602fc042b6f54705afdfa0d6bfc10557e74863'
RUST = '1.98.1-x86_64-unknown-linux-gnu'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['source', 'cargo-home', 'rustup-home', 'zig', 'target-dir', 'output']:
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    source, cargo, rustup, zig, target, output = [getattr(args, n).resolve() for n in
        ['source', 'cargo_home', 'rustup_home', 'zig', 'target_dir', 'output']]
    target.mkdir(parents=True, exist_ok=True)
    wrappers = target / 'compat-wrappers'
    wrappers.mkdir(exist_ok=True)
    cc, ar = wrappers / 'cc.py', wrappers / 'ar.py'
    cc.write_text('#!/usr/bin/env python3\nimport os,sys\nz=' + repr(str(zig)) +
                  '\na=[x for x in sys.argv[1:] if not x.startswith("--target=")]\n'
                  'os.execv(z,[z,"cc","-target","arm-linux-musleabi","-mcpu=arm926ej_s","-mfloat-abi=soft",*a])\n')
    ar.write_text('#!/usr/bin/env python3\nimport os,sys\nz=' + repr(str(zig)) +
                  '\nos.execv(z,[z,"ar",*sys.argv[1:]])\n')
    cc.chmod(0o755)
    ar.chmod(0o755)
    toolchain = rustup / 'toolchains' / RUST / 'bin'
    flags = ['--cfg', 'rustix_use_libc', '-C', 'force-unwind-tables=no', '-C', 'link-self-contained=no',
             f'--remap-path-prefix={source}=/src/dpi-detector',
             f'--remap-path-prefix={cargo}=/cargo', f'--remap-path-prefix={rustup}=/rustup']
    env = dict(os.environ, CARGO_HOME=str(cargo), RUSTUP_HOME=str(rustup),
               RUSTUP_TOOLCHAIN='1.98.1', CARGO_TARGET_DIR=str(target),
               CARGO_TARGET_ARMV5TE_UNKNOWN_LINUX_MUSLEABI_LINKER=str(cc),
               CC_armv5te_unknown_linux_musleabi=str(cc), AR_armv5te_unknown_linux_musleabi=str(ar),
               CARGO_ENCODED_RUSTFLAGS='\x1f'.join(flags),
               CFLAGS_armv5te_unknown_linux_musleabi=shlex.join([
                   f'-ffile-prefix-map={cargo}=/cargo', f'-ffile-prefix-map={zig.parent}=/zig']),
               PATH=str(toolchain) + os.pathsep + os.environ['PATH'])
    env.pop('RUSTFLAGS', None)
    subprocess.run([str(toolchain / 'cargo'), 'build', '--offline', '--locked', '--profile',
                    'release-router', '--target', TARGET, '-p', 'dpi-detector', '-j', '4'],
                   cwd=source, env=env, check=True)
    data = (target / TARGET / 'release-router/dpi-detector').read_bytes()
    if hashlib.sha256(data).hexdigest() != DIGEST:
        raise RuntimeError('Compatibility binary differs from the reviewed artifact')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
    output.chmod(0o644)
    print(f'{len(data)} bytes SHA256 {DIGEST}')


if __name__ == '__main__':
    main()

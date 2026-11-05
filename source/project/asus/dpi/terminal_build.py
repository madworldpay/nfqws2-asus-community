#!/usr/bin/env python3
"""Reproduce and verify fixed-program terminal helpers; packaging is offline."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

HERE=Path(__file__).resolve().parent
ZIG_VERSION='0.13.0'
ZIG_SHA256='7f9e3a661e909d5188d1b8b14f082b98a19c323a30d43bfdd1b2893ed37273e0'
FLAGS=['-std=c99','-O2','-static','-Wall','-Wextra','-Werror','-Wl,--build-id=none','-s']
TARGETS={
    'arm':('arm-linux-musleabi','arm926ej_s',['-mfloat-abi=soft'],[1,1,40]),
    'arm64':('aarch64-linux-musl','generic',[],[2,1,183]),
    'mips':('mips-linux-musl','mips32r2',['-msoft-float'],[1,2,8]),
    'mipsel':('mipsel-linux-musl','mips32r2',['-msoft-float'],[1,1,8]),
    'mips64':('mips64-linux-musl','mips64r2',['-msoft-float'],[2,2,8]),
    'x86':('x86-linux-musl','pentium4',[],[1,1,3]),
    'x86_64':('x86_64-linux-musl','x86_64',[],[2,1,62]),
}
ALIASES={'armv7-2.6':'arm','armv7-3.2':'arm','aarch64-3.10':'arm64'}


def _sha(raw):return hashlib.sha256(raw).hexdigest()


def _elf(raw,expected):
    if len(raw)<64 or raw[:4]!=b'\x7fELF' or raw[6]!=1:
        raise RuntimeError('Terminal helper ELF mismatch')
    endian='little' if raw[5]==1 else 'big'
    if [raw[4],raw[5],int.from_bytes(raw[18:20],endian)]!=expected:
        raise RuntimeError('Terminal helper ELF mismatch')
    wide=raw[4]==2
    offset=int.from_bytes(raw[32:40] if wide else raw[28:32],endian)
    size=int.from_bytes(raw[54:56] if wide else raw[42:44],endian)
    count=int.from_bytes(raw[56:58] if wide else raw[44:46],endian)
    if not count or size<(56 if wide else 32) or count>1024 or offset+size*count>len(raw):
        raise RuntimeError('Terminal helper ELF mismatch')
    if any(int.from_bytes(raw[at:at+4],endian)==3 for at in range(offset,offset+size*count,size)):
        raise RuntimeError('Terminal helper must be static')


def payload_for(engine: str, *, directory=None) -> bytes:
    """Return a source/hash/static-ELF verified payload for a trusted family."""
    family=ALIASES.get(engine,engine)
    if family not in TARGETS:raise ValueError('Unknown terminal helper family')
    root=Path(directory) if directory is not None else HERE
    manifest=json.loads((root/'bin/terminals.json').read_text())
    if manifest.get('schema_version')!=1 or manifest.get('source_sha256')!=_sha((root/'terminal.c').read_bytes()):
        raise RuntimeError('Terminal helper source changed; reproduce the helpers')
    compiler=manifest.get('compiler',{})
    if compiler!={'name':'zig','version':ZIG_VERSION,'sha256':ZIG_SHA256}:
        raise RuntimeError('Terminal helper compiler mismatch')
    record=manifest['outputs'][family]
    if record.get('name')!='dpi-terminal-'+family:raise RuntimeError('Terminal helper name mismatch')
    raw=(root/'bin'/record['name']).read_bytes()
    if record.get('size')!=len(raw) or record.get('sha256')!=_sha(raw):
        raise RuntimeError('Terminal helper SHA256 mismatch')
    _elf(raw,TARGETS[family][3])
    return raw


def reproduce(zig: Path, output: Path):
    zig=zig.resolve();output=output.resolve()
    if _sha(zig.read_bytes())!=ZIG_SHA256 or subprocess.check_output([str(zig),'version'],text=True).strip()!=ZIG_VERSION:
        raise RuntimeError('Use the pinned Zig 0.13.0 compiler')
    output.mkdir(parents=True,exist_ok=True)
    source=HERE/'terminal.c'
    manifest={'schema_version':1,'source_sha256':_sha(source.read_bytes()),
              'compiler':{'name':'zig','version':ZIG_VERSION,'sha256':ZIG_SHA256},'flags':FLAGS,'outputs':{}}
    with tempfile.TemporaryDirectory(prefix='nfqws-dpi-terminal-build-') as temporary:
        env=os.environ.copy();env.update(ZIG_GLOBAL_CACHE_DIR=temporary+'/global',ZIG_LOCAL_CACHE_DIR=temporary+'/local',SOURCE_DATE_EPOCH='0')
        for family,(target,cpu,options,identity) in TARGETS.items():
            path=output/('dpi-terminal-'+family)
            command=[str(zig),'cc','-target',target,'-mcpu='+cpu,*options,*FLAGS,
                     '-ffile-prefix-map='+str(HERE)+'=/src/dpi','-fdebug-prefix-map='+str(HERE)+'=/src/dpi',str(source),'-o',str(path)]
            subprocess.run(command,env=env,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=180)
            raw=path.read_bytes();_elf(raw,identity);path.chmod(0o644)
            manifest['outputs'][family]={'name':path.name,'target':target,'cpu':cpu,'options':options,
                                         'elf':identity,'size':len(raw),'sha256':_sha(raw)}
    (output/'terminals.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zig',required=True,type=Path)
    parser.add_argument('--output',default=HERE/'bin',type=Path)
    args=parser.parse_args();manifest=reproduce(args.zig,args.output)
    for family,record in manifest['outputs'].items():print(family,record['size'],record['sha256'])


if __name__=='__main__':main()

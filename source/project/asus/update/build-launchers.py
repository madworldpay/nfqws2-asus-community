#!/usr/bin/env python3
"""Reproduce the small syscall-only launchers, without installing a toolchain.

Normal cross GCC may be on PATH. --toolchain-root also accepts an extracted
cross-compiler prefix. Package construction consumes only validated outputs.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

HERE=Path(__file__).resolve().parent
TARGETS={'aarch64':('aarch64-linux-gnu',[]),'armv7':('arm-linux-gnueabi',['-marm','-march=armv7-a','-mfloat-abi=soft'])}
FLAGS=['-Os','-nostdlib','-static','-fno-builtin','-fno-stack-protector','-fno-pie','-no-pie','-Wl,--build-id=none','-Wl,-z,noexecstack','-s']


def build(output,toolchain=None):
    output.mkdir(parents=True,exist_ok=True);env=os.environ.copy()
    if toolchain:
        env['PATH']=str(toolchain/'usr/bin')+os.pathsep+env['PATH']
        env['LD_LIBRARY_PATH']=str(toolchain/'usr/lib/x86_64-linux-gnu')
    source=HERE/'opkg-launch.c'
    record={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'flags':FLAGS,'outputs':{}}
    for family,(target,options) in TARGETS.items():
        compiler=next((shutil.which(target+'-gcc'+suffix,path=env['PATH']) for suffix in ['', '-15'] if shutil.which(target+'-gcc'+suffix,path=env['PATH'])),None)
        if compiler is None:raise RuntimeError('cross compiler unavailable: '+target)
        dest=output/(family+'-opkg-launch')
        subprocess.run([compiler,*options,*FLAGS,str(source),'-o',str(dest)],env=env,check=True)
        version=subprocess.check_output([compiler,'-dumpfullversion'],env=env,text=True).strip()
        record['outputs'][family]={'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'compiler':target+'-gcc','compiler_version':version,'options':options}
    (output/'launchers.json').write_text(json.dumps(record,sort_keys=True,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=HERE/'bin');parser.add_argument('--toolchain-root',type=Path)
    args=parser.parse_args();build(args.output,args.toolchain_root)

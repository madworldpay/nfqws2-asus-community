#!/usr/bin/env python3
"""Reproduce libc-independent location guards with the updater toolchain."""
import argparse,hashlib,importlib.util,json,os,shutil,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('update_build',HERE.parent/'update/build-launchers.py')
shared=importlib.util.module_from_spec(spec);spec.loader.exec_module(shared)
def build(output,toolchain=None):
    output.mkdir(parents=True,exist_ok=True);env=os.environ.copy()
    if toolchain:
        env['PATH']=str(toolchain/'usr/bin')+os.pathsep+env['PATH'];env['LD_LIBRARY_PATH']=str(toolchain/'usr/lib/x86_64-linux-gnu')
    source=HERE/'location-launch.c';record={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'flags':shared.FLAGS,'outputs':{}}
    for family,(target,options) in shared.TARGETS.items():
        compiler=next((shutil.which(target+'-gcc'+suffix,path=env['PATH']) for suffix in ['', '-15'] if shutil.which(target+'-gcc'+suffix,path=env['PATH'])),None)
        if not compiler:raise RuntimeError('cross compiler unavailable: '+target)
        dest=output/(family+'-location-launch')
        subprocess.run([compiler,*options,*shared.FLAGS,str(source),'-o',str(dest)],env=env,check=True)
        record['outputs'][family]={'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'compiler':target+'-gcc','compiler_version':subprocess.check_output([compiler,'-dumpfullversion'],env=env,text=True).strip(),'options':options}
    (output/'launchers.json').write_text(json.dumps(record,sort_keys=True,indent=2)+'\n')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=HERE/'bin');p.add_argument('--toolchain-root',type=Path);a=p.parse_args();build(a.output,a.toolchain_root)

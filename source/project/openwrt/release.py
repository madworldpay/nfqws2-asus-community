#!/usr/bin/env python3
"""Generate native release data, then verify an external signature before sealing.

The signing key is never read here. Native APKs must already carry a signature
from the pinned public key; unsigned APKs cannot enter the published manifest.
"""
import argparse,base64,hashlib,io,json,re,subprocess,tarfile,tempfile
from pathlib import Path,PurePosixPath
HERE=Path(__file__).resolve().parent
CORE='1.3.2'

def targets():
    value=json.loads((HERE/'release-targets.json').read_text())
    return {(series,arch)for series in value['series']for arch in value['architectures']}

def regular(path,limit=33554432):
    path=Path(path);s=path.lstat()
    if path.is_symlink()or not path.is_file()or s.st_nlink!=1 or not 0<s.st_size<=limit:raise ValueError('invalid_artifact')
    return path

def checked(argv):
    p=subprocess.run([str(arg)for arg in argv],capture_output=True,timeout=45)
    if p.returncode:raise ValueError('native_artifact_verification_failed')
    return p.stdout

def members(raw,limit):
    if len(raw)>33554432:raise ValueError('archive_limit')
    result={};total=0
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz')as archive:
        for n,member in enumerate(archive):
            name=member.name
            while name.startswith('./'):name=name[2:]
            if name in ('','.'):continue
            p=PurePosixPath(name)
            if p.is_absolute()or'..'in p.parts or name in result or n>4096:raise ValueError('invalid_archive_member')
            total+=member.size
            if member.size<0 or total>limit:raise ValueError('archive_limit')
            if member.isfile():
                f=archive.extractfile(member)
                if f is None:raise ValueError('invalid_archive_member')
                result[name]=f.read()
            elif member.isdir()or member.issym():result[name]=None
            else:raise ValueError('invalid_archive_member')
    return result

def ipk(path):
    outer=members(path.read_bytes(),33554432)
    if set(outer)!={'debian-binary','control.tar.gz','data.tar.gz'}or outer['debian-binary']!=b'2.0\n':raise ValueError('invalid_ipk')
    control=members(outer['control.tar.gz'],1048576);text=control.get('control',b'').decode();fields={}
    for line in text.splitlines():
        if not line or line.startswith((' ','\t')):continue
        if ': 'not in line:raise ValueError('invalid_control')
        k,v=line.split(': ',1)
        if k in fields:raise ValueError('duplicate_control')
        fields[k]=v
    data=members(outer['data.tar.gz'],134217728);profile=data.get('usr/share/nfqws2/platform.json')
    if not isinstance(profile,bytes)or len(profile)>4096:raise ValueError('invalid_application_identity')
    allocated=sum(((len(raw)+4095)//4096)*4096 if isinstance(raw,bytes)else 4096 for raw in data.values())
    return {'name':fields.get('Package'),'version':fields.get('Version'),'arch':fields.get('Architecture')},json.loads(profile),max(1,allocated)

def apk(path,tool,public_key):
    if tool is None or public_key is None:raise ValueError('signed_apk_required')
    with tempfile.TemporaryDirectory(prefix='nfqws-native-release-')as td:
        root=Path(td);keys=root/'keys';keys.mkdir(mode=0o700);(keys/'release.pem').write_bytes(regular(public_key,8192).read_bytes())
        checked([tool,'verify','--keys-dir',keys,path]);info=json.loads(checked([tool,'adbdump','--format','json',path]))['info']
        dest=root/'payload';dest.mkdir();checked([tool,'extract','--keys-dir',keys,'--no-chown','--destination',dest,path])
        profile=dest/'usr/share/nfqws2/platform.json';regular(profile,4096);v=json.loads(profile.read_bytes())
        return {k:info.get(k)for k in ['name','version','arch']},v,info['installed-size']

def manifest(paths,build,web_version,notes,apk_tool=None,public_key=None):
    if type(build)is not int or not 1<=build<=2147483647 or not re.fullmatch(r'\d+\.\d+\.\d+',web_version)or not isinstance(notes,str)or len(notes)>2000:raise ValueError('invalid_release')
    packages=[];seen=set()
    for path in sorted(map(Path,paths)):
        regular(path);fmt=path.suffix[1:]
        if fmt=='ipk':record,profile,stored=ipk(path);series='24.10';version=CORE+'-'+str(build)
        elif fmt=='apk':record,profile,stored=apk(path,apk_tool,public_key);series='25.12';version=CORE+'-r'+str(build)
        else:raise ValueError('invalid_format')
        arch=record.get('arch');expected={'platform':'openwrt','series':series,'arch':arch,'format':fmt,'version':version,'application_build':build}
        if record.get('name')!='nfqws2-native'or record.get('version')!=version or not isinstance(arch,str)or not re.fullmatch(r'[a-z0-9][a-z0-9_+-]{0,99}',arch)or any(profile.get(k)!=v for k,v in expected.items())or path.name!='nfqws2-native_'+version+'_'+arch+'.'+fmt:raise ValueError('native_application_identity_mismatch')
        identity=(series,arch)
        if identity in seen:raise ValueError('duplicate_target')
        seen.add(identity)
        if type(stored)is not int or not 0<stored<=134217728:raise ValueError('invalid_installed_size')
        packages.append({'series':series,'arch':arch,'format':fmt,'version':version,'filename':path.name,'size':path.stat().st_size,'installed_size':stored,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    if not 1<=len(packages)<=64:raise ValueError('invalid_package_count')
    return {'schema_version':1,'platform':'openwrt','package':'nfqws2-native','core_version':CORE,'web_version':web_version,'build':build,'notes':notes,'packages':packages}

def envelope(raw,signature,public_key):
    if not isinstance(raw,bytes)or not 0<len(raw)<=32768 or not isinstance(signature,bytes)or len(signature)!=384:raise ValueError('invalid_signature')
    with tempfile.TemporaryDirectory()as td:
        root=Path(td);(root/'manifest').write_bytes(raw);(root/'signature').write_bytes(signature)
        p=subprocess.run(['openssl','dgst','-sha256','-verify',str(public_key),'-signature',str(root/'signature'),str(root/'manifest')],capture_output=True,timeout=10)
        if p.returncode:raise ValueError('invalid_signature')
    return {'manifest':base64.b64encode(raw).decode(),'signature':base64.b64encode(signature).decode()}

def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='mode',required=True)
    make=sub.add_parser('manifest');make.add_argument('--directory',required=True,type=Path);make.add_argument('--build',required=True,type=int);make.add_argument('--web-version',required=True);make.add_argument('--notes',required=True,type=Path);make.add_argument('--apk-tool',required=True,type=Path);make.add_argument('--public-key',required=True,type=Path)
    seal=sub.add_parser('seal');seal.add_argument('--manifest',required=True,type=Path);seal.add_argument('--signature',required=True,type=Path);seal.add_argument('--public-key',required=True,type=Path);seal.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if args.mode=='manifest':
        paths=list(args.directory.glob('*.ipk'))+list(args.directory.glob('*.apk'));v=manifest(paths,args.build,args.web_version,args.notes.read_text().strip(),args.apk_tool,args.public_key)
        if {(p['series'],p['arch'])for p in v['packages']}!=targets():parser.error('The complete native release matrix is required')
        (args.directory/'openwrt-release.json').write_text(json.dumps(v,ensure_ascii=False,separators=(',',':'))+'\n')
    else:
        raw=regular(args.manifest,32768).read_bytes();signature=regular(args.signature,384).read_bytes();v=envelope(raw,signature,args.public_key);args.output.mkdir(parents=True,exist_ok=True)
        (args.output/'openwrt-release.json').write_bytes(raw);(args.output/'openwrt-release.sig').write_text(v['signature']+'\n');(args.output/'openwrt-public.json').write_text(json.dumps(v,separators=(',',':'))+'\n')
if __name__=='__main__':main()

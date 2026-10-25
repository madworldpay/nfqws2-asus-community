#!/usr/bin/env python3
"""Native OpenWrt packaging with verified static engines and official tools.

IPK uses the pinned OpenWrt ipkg-build script. APK uses apk mkpkg from the
verified official SDK; no Entware runtime, libraries or kernel modules ship.
All builds are local. This tool never installs or publishes a package.
"""
import argparse
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
HERE=Path(__file__).resolve().parent
ASSETS=json.loads((HERE/'assets.json').read_text())
spec=importlib.util.spec_from_file_location('nfqws_native_platform',HERE/'platform.py')
platform=importlib.util.module_from_spec(spec);spec.loader.exec_module(platform)
DEPENDENCIES=['libc','firewall4','kmod-nft-queue','kmod-nfnetlink-queue','php8-cgi',
              'php8-mod-session','php8-mod-openssl','php8-mod-curl','ca-bundle','flock','uhttpd']


def native_metadata(series,arch,release=1):
    if series not in ('24.10','25.12') or not re.fullmatch(r'[1-9][0-9]{0,7}',str(release)):
        raise ValueError('invalid_native_release')
    engine=platform.engine_for_arch(arch)
    return dict(package='nfqws2-native',series=series,arch=arch,engine=engine,
                format='ipk'if series=='24.10'else'apk',
                version='1.3.2-'+('r'if series=='25.12'else'')+str(release),
                dependencies=DEPENDENCIES.copy(),elf=platform.ENGINES[engine].copy())


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb')as f:
        while chunk:=f.read(1024*1024):h.update(chunk)
    return h.hexdigest()


def pinned_asset(asset,cache,offline=False):
    path=Path(cache)/asset['name']
    if not path.exists():
        if offline:raise RuntimeError('Missing verified build asset: '+asset['name'])
        path.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent,delete=False)as f:
            tmp=Path(f.name)
            try:
                with urllib.request.urlopen(asset['url'],timeout=60)as source:shutil.copyfileobj(source,f)
                f.flush()
                if digest(tmp)!=asset['sha256']:raise RuntimeError('Build asset SHA256 mismatch: '+asset['name'])
                tmp.replace(path)
            finally:tmp.unlink(missing_ok=True)
    if digest(path)!=asset['sha256']:raise RuntimeError('Build asset SHA256 mismatch: '+asset['name'])
    return path


def source_payload(cache,offline=False):
    path=pinned_asset(ASSETS['engine_archive'],cache,offline)
    with tarfile.open(path)as outer:
        member=next(m for m in outer if m.name.removeprefix('./')=='data.tar.gz'and m.isfile())
        data=outer.extractfile(member).read()
    with tarfile.open(fileobj=io.BytesIO(data))as inner:
        # Read individual regular files. Never extract upstream archive paths.
        return {m.name.removeprefix('./'):inner.extractfile(m).read()for m in inner if m.isfile()}


def prepare_engine(target,source,upx=None):
    entry=ASSETS['engines'][target['engine']]
    data=source[entry['member']]
    if hashlib.sha256(data).hexdigest()!=entry['packed_sha256']:raise RuntimeError('Engine SHA256 mismatch')
    if entry['packed_sha256']!=entry['unpacked_sha256']:
        tool=upx or shutil.which('upx')or shutil.which('upx-ucl')
        if not tool:raise RuntimeError('Host UPX is required to unpack the verified engine')
        with tempfile.TemporaryDirectory(prefix='nfqws-native-engine-')as td:
            packed=Path(td)/'packed';unpacked=Path(td)/'unpacked';packed.write_bytes(data)
            subprocess.run([str(tool),'-d','-o',str(unpacked),str(packed)],check=True,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30,env={k:v for k,v in os.environ.items()if k!='UPX'})
            data=unpacked.read_bytes()
    if hashlib.sha256(data).hexdigest()!=entry['unpacked_sha256']:raise RuntimeError('Derived engine SHA256 mismatch')
    platform.validate_engine(data,target)
    return data


def native_defaults():
    text=(ROOT/'core/etc/nfqws2/nfqws2.conf').read_text()
    text=text.replace('/opt/etc/nfqws2/','/etc/nfqws2/').replace('/opt/var/log/','/var/log/')
    text=re.sub(r'^# Provider network interface.*?^ISP_INTERFACE=[^\n]*$',
        '# Logical uplinks are discovered from netifd. Override only when needed.\nISP_INTERFACE=""',text,flags=re.M|re.S,count=1)
    text=re.sub(r'^# Keenetic policy name\nPOLICY_NAME=[^\n]*\n# Policy mode[^\n]*\nPOLICY_EXCLUDE=[^\n]*\n','',text,flags=re.M,count=1)
    text=text.replace('# TCP ports for iptables rules','# TCP ports for native nftables capture').replace('# UDP ports for iptables rules','# UDP ports for native nftables capture')
    text+='\n# Client selection: all, include, or exclude.\nASUS_CLIENT_MODE="all"\nASUS_CLIENTS4=""\nASUS_CLIENTS6=""\n'
    if '/opt/'in text:raise RuntimeError('Unconverted native default path')
    return text.encode()


def payload_files(target,engine,source=None):
    platform.validate_engine(engine,target)
    files={'usr/bin/nfqws2':(engine,0o755),
        'usr/share/nfqws2/defaults/nfqws2.conf':(native_defaults(),0o600),
        'usr/share/nfqws2/platform.json':(json.dumps({k:target[k]for k in ['series','arch','engine','format','version']}|{'platform':'openwrt'},sort_keys=True).encode()+b'\n',0o644),
        'lib/upgrade/keep.d/nfqws2-native':(b'/etc/nfqws2/\n/etc/nfqws2-web/\n/etc/config/nfqws2-web\n',0o644)}
    for name in ['control.sh','platform.sh','firewall.sh','firewall-hook.sh','config.php','config-cli.php','flow.php','flow-cli.php','nfqws2.init']:
        installed='nfqws2-native'if name=='nfqws2.init'else name
        files['usr/lib/nfqws2/'+installed]=((HERE/name).read_bytes(),0o755 if name in ['control.sh','firewall-hook.sh','nfqws2.init']else 0o644)
    files['usr/lib/nfqws2/import-config.php']=((ROOT/'webui/web/public/import-config.php').read_bytes(),0o644)
    args=re.search(r'^_startup_args\(\) \{.*?^\}',(ROOT/'core/etc/init.d/common').read_text(),re.M|re.S)
    if not args:raise RuntimeError('Shared startup argument contract missing')
    files['usr/lib/nfqws2/args.sh']=((args.group()+'\n').encode(),0o644)
    for path in sorted((ROOT/'core/etc/nfqws2/lists').iterdir()):
        if path.is_file():files['usr/share/nfqws2/defaults/lists/'+path.name]=(path.read_bytes(),0o644)
    if source is not None:
        for name,data in source.items():
            prefix='opt/etc/nfqws2/'
            if not name.startswith(prefix):continue
            rel=name[len(prefix):]
            if not re.fullmatch(r'(?:lua/[a-zA-Z0-9_-]+\.lua\.gz|blobs/[a-zA-Z0-9_-]+\.bin)',rel):continue
            if rel.endswith('.gz'):data=gzip.decompress(data);rel=rel[:-3]
            files['usr/share/nfqws2/defaults/'+rel]=(data,0o644)
    for name in ['LICENSE','THIRD-PARTY-NOTICES.txt']:
        files['usr/share/licenses/nfqws2-native/'+name]=((ROOT/name).read_bytes(),0o644)
    return files


def write_files(root,files):
    root=Path(root);root.mkdir(parents=True,exist_ok=True);root.chmod(0o755)
    for name,(data,mode)in files.items():
        p=PurePosixPath(name)
        if p.is_absolute()or'..'in p.parts:raise ValueError('Unsafe package path')
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True)
        parent=path.parent
        while parent!=root:
            parent.chmod(0o755);parent=parent.parent
        path.write_bytes(data);path.chmod(mode)


def web_payload(dist=None):
    dist=Path(dist)if dist is not None else ROOT/'webui/web/dist'
    for name in ['index.html','index.php','asus.php','platform.php','openwrt-web.php']:
        if not (dist/name).is_file():raise RuntimeError('Build the shared production frontend before native packaging')
    files={'usr/share/nfqws2-web/'+str(p.relative_to(dist)):(p.read_bytes(),0o644)
           for p in sorted(dist.rglob('*'))if p.is_file()and not p.name.endswith('.map')}
    files['usr/share/nfqws2-web/platform-profile.json']=(b'{"schema_version":1,"platform":"openwrt"}\n',0o644)
    for name,installed in [('web.sh','web.sh'),('php-cgi.sh','php-cgi.sh'),('nfqws2-web.init','nfqws2-native-web')]:
        files['usr/lib/nfqws2-web/'+installed]=((HERE/name).read_bytes(),0o644 if name=='web.sh'else 0o755)
    files['usr/share/nfqws2/defaults/web-config']=((HERE/'web-config').read_bytes(),0o600)
    return files


def package_hook(target,action,upgrade=False):
    text='#!/bin/sh\numask 077\nPATH=/usr/sbin:/usr/bin:/sbin:/bin\nexport PATH\n'
    for key,value in [('ACTION',action),('ARCH',target['arch']),('SERIES',target['series']),('FORMAT',target['format'])]:
        text+="NFQWS_PKG_"+key+"='"+value+"'\n"
    if upgrade:text+='PKG_UPGRADE=1\n'
    return (text+(HERE/'package-lifecycle.sh').read_text()).encode()


def build_native(series,package_arch,cache,output,offline=False,upx=None,release=1):
    target=native_metadata(series,package_arch,release);output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    source=source_payload(cache,offline);engine=prepare_engine(target,source,upx)
    with tempfile.TemporaryDirectory(prefix='nfqws-native-package-')as td:
        stage=Path(td)/'payload';write_files(stage,payload_files(target,engine,source)|web_payload())
        hooks={key:package_hook(target,action)for key,action in [('preinst','preinstall'),('postinst','postinstall'),('prerm','preremove'),('postrm','postremove')]}
        if target['format']=='ipk':
            metadata='Package: nfqws2-native\nVersion: '+target['version']+'\nArchitecture: '+target['arch']+'\nDepends: '+', '.join(target['dependencies'])+'\nMaintainer: madworldpay\nSection: net\nLicense: MIT\nDescription: NFQWS2 community native OpenWrt service\n'
            write_files(stage,{'CONTROL/control':(metadata.encode(),0o644),**{'CONTROL/'+k:(v,0o755)for k,v in hooks.items()}})
            tool=pinned_asset(ASSETS['ipkg_build'],cache,offline)
            subprocess.run(['fakeroot','sh',str(tool),str(stage),str(output)],check=True,
                env={**os.environ,'SOURCE_DATE_EPOCH':'0'},stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
            package=output/(target['package']+'_'+target['version']+'_'+target['arch']+'.ipk')
        else:
            package=build_apk(target,stage,hooks,cache,output,offline)
        if not package.is_file():raise RuntimeError('Native package tool did not produce its expected artifact')
    checksum=digest(package)
    (output/(package.name+'.sha256')).write_text(checksum+'  '+package.name+'\n')
    return package


def build_apk(target,stage,hooks,cache,output,offline):
    sdk=pinned_asset(ASSETS['apk_sdk'],cache,offline)
    with tempfile.TemporaryDirectory(prefix='nfqws-native-apk-tool-')as td:
        tools=Path(td)/'tools';tools.mkdir()
        subprocess.run(['tar','--zstd','-xf',str(sdk),'-C',str(tools),'--strip-components=3','--wildcards',
            '*/staging_dir/host/bin/apk','*/staging_dir/host/bin/.apk.bin',
            '*/staging_dir/host/bin/fakeroot','*/staging_dir/host/bin/faked','*/staging_dir/host/bin/.faked.bin',
            '*/staging_dir/host/lib/*'],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120)
        scripts=Path(td)/'scripts';scripts.mkdir()
        pairs={'pre-install':'preinst','post-install':'postinst','pre-deinstall':'prerm','post-deinstall':'postrm'}
        for name,key in pairs.items():(scripts/name).write_bytes(hooks[key])
        (scripts/'pre-upgrade').write_bytes(package_hook(target,'preinstall',True))
        (scripts/'post-upgrade').write_bytes(package_hook(target,'postinstall',True))
        package=output/(target['package']+'-'+target['version']+'.apk')
        # sdk fakeroot uses its own matching preload library and loader.
        args=[str(tools/'bin/fakeroot'),str(tools/'bin/apk'),'mkpkg','--info','name:'+target['package'],
            '--info','version:'+target['version'],'--info','arch:'+target['arch'],
            '--info','license:MIT','--info','description:NFQWS2 community native OpenWrt service',
            '--info','origin:nfqws2-native','--info','url:https://github.com/madworldpay/nfqws2-asus-community',
            '--info','maintainer:madworldpay','--info','depends:'+' '.join(target['dependencies']),
            '--files',str(stage),'--output',str(package)]
        for name in list(pairs)+['pre-upgrade','post-upgrade']:args+=['--script',name+':'+str(scripts/name)]
        filelist='lib/apk/packages/nfqws2-native.list'
        allfiles=sorted('/'+str(p.relative_to(stage))for p in stage.rglob('*')if p.is_file())+['/'+filelist]
        write_files(stage,{filelist:(('\n'.join(allfiles)+'\n').encode(),0o644)})
        env={**os.environ,'SOURCE_DATE_EPOCH':'0','STAGING_DIR_HOST':str(tools)}
        env.pop('LD_PRELOAD',None)
        subprocess.run(args,check=True,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
        return package


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--series',required=True,choices=['24.10','25.12']);p.add_argument('--arch',required=True)
    p.add_argument('--cache',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--offline',action='store_true');p.add_argument('--upx');p.add_argument('--release',default=1,type=int)
    args=p.parse_args()
    try:print(build_native(args.series,args.arch,args.cache,args.output,args.offline,args.upx,args.release))
    except subprocess.CalledProcessError as e:
        raise SystemExit((e.stdout or b'').decode(errors='replace')+(e.stderr or b'').decode(errors='replace'))
    except (RuntimeError,ValueError)as e:raise SystemExit(str(e))


if __name__=='__main__':main()

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
              'php8-mod-session','php8-mod-openssl','php8-mod-curl','ca-bundle','flock','uhttpd','libopenssl3','libgcc']


def native_metadata(series,arch,release=1):
    if series not in ('24.10','25.12') or not re.fullmatch(r'[1-9][0-9]{0,7}',str(release)):
        raise ValueError('invalid_native_release')
    engine=platform.engine_for_arch(arch)
    return dict(package='nfqws2-native',series=series,arch=arch,engine=engine,
                format='ipk'if series=='24.10'else'apk',
                version='1.3.2-'+('r'if series=='25.12'else'')+str(release),
                application_build=int((ROOT/'BUILD_NUMBER').read_text()),
                dependencies=DEPENDENCIES.copy(),elf=platform.ENGINES[engine].copy())


def package_filename(target):
    return f"nfqws2-native_{target['version']}_{target['arch']}.{target['format']}"


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
        'usr/share/nfqws2/platform.json':(json.dumps({k:target[k]for k in ['series','arch','engine','format','version','application_build']}|{'platform':'openwrt'},sort_keys=True).encode()+b'\n',0o644),
        'lib/upgrade/keep.d/nfqws2-native':(b'/etc/nfqws2/\n/etc/nfqws2-web/\n/etc/config/nfqws2-web\n',0o644)}
    for name in ['control.sh','platform.sh','firewall.sh','firewall-hook.sh','config.php','config-cli.php','flow.php','flow-cli.php','resource-upgrade.php','nfqws2.init']:
        installed='nfqws2-native'if name=='nfqws2.init'else name
        files['usr/lib/nfqws2/'+installed]=((HERE/name).read_bytes(),0o755 if name in ['control.sh','firewall-hook.sh','nfqws2.init']else 0o644)
    for name,mode in [('quiesce.php',0o644),('quiesce.sh',0o755),('worker.php',0o644),('worker.sh',0o755)]:
        files['usr/lib/nfqws2/update/'+name]=((HERE/'update'/name).read_bytes(),mode)
    if target['format']=='apk':
        files['usr/lib/nfqws2/update/apk-precommit.php']=((HERE/'update/apk-precommit.php').read_bytes(),0o644)
        files['lib/apk/commit_hooks.d/10-nfqws2-native']=((HERE/'update/apk-precommit.sh').read_bytes(),0o755)
    lifecycle=(HERE/'package-lifecycle.sh').read_text();boundary='case "$NFQWS_PKG_ACTION" in'
    if lifecycle.count(boundary)!=1:raise RuntimeError('Native package function boundary is ambiguous')
    files['usr/lib/nfqws2/update/package-functions.sh']=(lifecycle.split(boundary,1)[0].encode(),0o644)
    files['usr/lib/nfqws2/import-config.php']=((ROOT/'webui/web/public/import-config.php').read_bytes(),0o644)
    args=re.search(r'^_startup_args\(\) \{.*?^\}',(ROOT/'core/etc/init.d/common').read_text(),re.M|re.S)
    if not args:raise RuntimeError('Shared startup argument contract missing')
    files['usr/lib/nfqws2/args.sh']=((args.group()+'\n').encode(),0o644)
    for path in sorted((ROOT/'core/etc/nfqws2/lists').iterdir()):
        if path.is_file():files['usr/share/nfqws2/defaults/lists/'+path.name]=(path.read_bytes(),0o644)
    files['usr/share/nfqws2/defaults/lua/local-guarded-ts.lua']=((ROOT/'asus/lua/local-guarded-ts.lua').read_bytes(),0o644)
    if source is not None:
        for name,data in source.items():
            prefix='opt/etc/nfqws2/'
            if not name.startswith(prefix):continue
            rel=name[len(prefix):]
            if not re.fullmatch(r'(?:lua/[a-zA-Z0-9_-]+\.lua\.gz|blobs/[a-zA-Z0-9_-]+\.bin)',rel):continue
            if rel.endswith('.gz'):data=gzip.decompress(data);rel=rel[:-3]
            files['usr/share/nfqws2/defaults/'+rel]=(data,0o644)
    baseline={'schema_version':1,'package_version':target['version'],'web_version':(ROOT/'VERSION').read_text().strip(),
        'build_number':target['application_build'], 'engine':{'version':'1.0.6','provider':'nfqws2-keenetic',
            'sha256':hashlib.sha256(engine).hexdigest(),'elf_class':target['elf']['class'],'elf_machine':target['elf']['machine']},'resources':{}}
    for name,(data,_)in files.items():
        for kind,directory in [('lua','lua'),('blob','blobs')]:
            prefix='usr/share/nfqws2/defaults/'+directory+'/'
            if name.startswith(prefix):baseline['resources'][kind+'/'+name[len(prefix):]]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    files['usr/share/nfqws2/report-baseline.json']=((json.dumps(baseline,sort_keys=True,separators=(',',':'))+'\n').encode(),0o644)
    for source,name in [('openwrt-package-manifest.schema.json','openwrt-package-manifest.schema.json'),('trusted-release-key.pem','update-release-key.pem')]:
        files['usr/share/nfqws2/'+name]=((ROOT/'updates'/source).read_bytes(),0o644)
    for name in ['profile-catalog.schema.json','dpi-catalog.json','dpi-profile.json','dpi-native-defaults.json',
                 'dpi-analysis-v2.schema.json','dpi-report.schema.json','dpi-envelope.schema.json','dpi-saved.schema.json',
                 'strategy.schema.json','strategy-v2.schema.json','resources.schema.json','dns-share.schema.json',
                 'share-v4.schema.json','share-envelope.schema.json','report.schema.json']:
        files['usr/share/nfqws2/'+name]=((ROOT/'support'/name).read_bytes(),0o644)
    dpi=json.loads((HERE/'dpi-assets.json').read_text())
    files['usr/share/nfqws2/dpi-native-artifact.json']=((json.dumps({'schema_version':1,'version':dpi['version'],
        'arch':target['arch'],'engine':target['engine'],'artifact':dpi['artifacts'].get(target['engine'])},sort_keys=True)+'\n').encode(),0o644)
    if target['engine']=='arm':
        legacy=(ROOT/'asus/dpi/legacy/dpi-detector-armv5te').read_bytes();record=dpi['artifacts']['arm']
        if len(legacy)!=record['size']or hashlib.sha256(legacy).hexdigest()!=record['sha256']:raise RuntimeError('Compatible ARM DPI SHA256 mismatch')
        files['usr/share/nfqws2/optional/dpi-detector-armv5te']=(legacy,0o644)
    files['usr/share/licenses/nfqws2-native/dpi-detector-MIT.txt']=((ROOT/'support/dpi-detector-MIT.txt').read_bytes(),0o644)
    for name in ['guard.sh','probe.sh','drop.sh','stop.sh','worker.php','cli.php']:
        data=(ROOT/'asus/dpi'/name).read_bytes()
        if name in ['worker.php','cli.php']:data=data.replace(b'/opt/share/nfqws-asus-web/',b'/usr/share/nfqws2-web/')
        files['usr/lib/nfqws2/dpi/'+name]=(data,0o644)
    files['usr/lib/nfqws2/dpi/paths.sh']=((HERE/'dpi-paths.sh').read_bytes(),0o644)
    files['usr/bin/nfqws2-dpi']=((ROOT/'asus/dpi/cli.sh').read_bytes().replace(b'/opt/bin/php-cgi',b'/usr/bin/php-cgi').replace(b'/opt/lib/nfqws2-asus/dpi/cli.php',b'/usr/lib/nfqws2/dpi/cli.php'),0o755)
    files['usr/share/nfqws2/profile-catalog-public.pem']=((ROOT/'asus/profile-catalog-public.pem').read_bytes(),0o644)
    files['usr/share/nfqws2/support-relay-default.json']=((ROOT/'asus/support-relay.json').read_bytes(),0o644)
    for name in ['LICENSE','THIRD-PARTY-NOTICES.txt']:
        files['usr/share/licenses/nfqws2-native/'+name]=((ROOT/name).read_bytes(),0o644)
    return files


def smartdns_runtime_files():
    # Keep the tested common owner algorithms. Every fixed replacement is
    # counted, so changes to their source contract fail the native build.
    def adapt(name,replacements):
        data=(ROOT/'asus/smartdns'/name).read_bytes()
        for before,after in replacements:
            before=before.encode();after=after.encode()
            if data.count(before)!=1:raise RuntimeError('SmartDNS native adapter contract changed: '+name+' '+repr(before))
            data=data.replace(before,after)
        return data
    files={}
    for name in ['config-worker.php','worker.php']:
        data=adapt(name,[('/opt/share/nfqws-asus-web/','/usr/share/nfqws2-web/')])
        files['usr/lib/nfqws2/smartdns/'+name]=(data,0o644)
    files['usr/lib/nfqws2/smartdns/control.php']=(adapt('control.php',[
        ('/opt/share/nfqws-asus-web/','/usr/share/nfqws2-web/'),
        ('new AsusSmartDnsNativeBackend($store,new AsusSmartDnsInstaller())','AsusSmartDnsNativeBackend::create($store,new AsusSmartDnsInstaller())')]),0o644)
    files['usr/lib/nfqws2/smartdns/config-worker.sh']=(adapt('config-worker.sh',[
        ('root=/opt/etc/nfqws-asus-web/smartdns','root=/etc/nfqws2-web/smartdns'),
        ('lib=/opt/lib/nfqws2-asus/smartdns','lib=/usr/lib/nfqws2/smartdns'),
        ('updates=/opt/var/lib/nfqws2-asus/updates','updates=/tmp/nfqws2-native-state/updates'),
        ('/opt/bin/php-cgi','/usr/bin/php-cgi'),
        ('"$bb" sleep 0.1','"$bb" sleep 1'),
        ('-lt 20','-lt 3'),
        ('"$lib/session-owner" "$job" "$$" "$ticks"','"$bb" setsid /bin/sh "$lib/config-worker.sh" session "$job" "$$" "$ticks"')]),0o644)
    files['usr/lib/nfqws2/smartdns/worker.sh']=(adapt('worker.sh',[
        ('bb=/opt/libexec/nfqws2-asus/busybox','bb=/bin/busybox'),
        ('/opt/lib/nfqws2-asus/smartdns-engine','/usr/lib/nfqws2/smartdns-engine'),
        ('/opt/bin/php-cgi','/usr/bin/php-cgi'),
        ('/opt/lib/nfqws2-asus/smartdns/worker.php','/usr/lib/nfqws2/smartdns/worker.php'),
        ('"$bb" usleep 250000','"$bb" sleep 1'),
        ('"$bb" usleep 1000000','"$bb" sleep 1')]),0o644)
    for source,name in [('smartdns-native-control.php','native-control.php'),('smartdns-runtime.sh','runtime.sh'),('smartdns-resume.sh','resume.sh'),('dnsmasq-transaction.sh','dnsmasq-transaction.sh'),('nfqws2-dns.init','nfqws2-native-dns'),('nfqws2-dns-resume.init','nfqws2-native-dns-resume')]:
        files['usr/lib/nfqws2/smartdns/'+name]=((HERE/source).read_bytes(),0o644 if name.endswith('.php')else 0o755)
    return files


def smartdns_payload(target,cache,offline=False,apk_tool=None):
    catalog=json.loads((HERE/'smartdns-assets.json').read_text())
    try:asset=catalog['artifacts'][target['series']][target['arch']]
    except KeyError:raise RuntimeError('No pinned native SmartDNS engine for this package architecture')
    path=pinned_asset(asset,cache,offline)
    if target['format']=='ipk':
        with tarfile.open(path)as outer:
            member=next(m for m in outer if m.name.removeprefix('./')=='data.tar.gz'and m.isfile());data=outer.extractfile(member).read()
        with tarfile.open(fileobj=io.BytesIO(data))as inner:
            candidates=[m for m in inner if m.name.removeprefix('./')=='usr/sbin/smartdns'and m.isfile()]
            if len(candidates)!=1:raise RuntimeError('Native SmartDNS payload mismatch')
            binary=inner.extractfile(candidates[0]).read()
    else:
        with tempfile.TemporaryDirectory(prefix='nfqws-smartdns-extract-')as td:
            tool=apk_tool
            if tool is None:
                sdk=pinned_asset(ASSETS['apk_sdk'],cache,offline);tools=Path(td)/'tools';tools.mkdir()
                subprocess.run(['tar','--zstd','-xf',str(sdk),'-C',str(tools),'--strip-components=3','--wildcards',
                    '*/staging_dir/host/bin/apk','*/staging_dir/host/bin/.apk.bin','*/staging_dir/host/lib/*'],
                    check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120)
                tool=tools/'bin/apk'
            dest=Path(td)/'unpack';dest.mkdir()
            # Package was pinned above; extract never executes its scripts.
            subprocess.run([str(tool),'extract','--allow-untrusted','--no-chown','--destination',str(dest),str(path)],
                check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
            binary=(dest/'usr/sbin/smartdns').read_bytes()
    if len(binary)!=asset['binary_size']or hashlib.sha256(binary).hexdigest()!=asset['binary_sha256']:
        raise RuntimeError('Native SmartDNS binary hash mismatch')
    elf=target['elf']
    if binary[:4]!=b'\x7fELF'or binary[4]!=elf['class']or binary[5]!=elf['endian']or int.from_bytes(binary[18:20],'little'if elf['endian']==1 else'big')!=elf['machine']:
        raise RuntimeError('Native SmartDNS ELF mismatch')
    artifact={'source':'bundled-native','version':asset['version'],'version_output':asset['version_output'],
        'sha256':asset['binary_sha256'],'elf_class':asset['elf_class'],'elf_data':asset['elf_data'],'elf_machine':asset['elf_machine'],
        'files':{'smartdns':{'size':asset['binary_size'],'sha256':asset['binary_sha256']}},'links':[]}
    record={'schema_version':1,'series':target['series'],'arch':target['arch'],'artifact':artifact}
    return {'usr/share/nfqws2/optional/smartdns':(binary,0o644),
        'usr/share/nfqws2/smartdns-native-artifact.json':((json.dumps(record,sort_keys=True)+'\n').encode(),0o644),
        'usr/share/nfqws2/smartdns-native-source.json':((json.dumps(asset,sort_keys=True)+'\n').encode(),0o644)}|smartdns_runtime_files()


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
    for name in ['index.html','index.php','asus.php','platform.php','openwrt-web.php','resource-paths.php']:
        if not (dist/name).is_file():raise RuntimeError('Build the shared production frontend before native packaging')
    # Vite copies PHP unchanged. A stale backend is unsafe when native hooks
    # depend on a newer module, even if an old frontend directory still exists.
    for source in (ROOT/'webui/web/public').glob('*.php'):
        installed=dist/source.name
        if not installed.is_file()or installed.read_bytes()!=source.read_bytes():
            raise RuntimeError('Rebuild the shared production frontend: native backend is stale')
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


def build_native(series,package_arch,cache,output,offline=False,upx=None,release=1,sign_key=None):
    target=native_metadata(series,package_arch,release);output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    source=source_payload(cache,offline);engine=prepare_engine(target,source,upx)
    with tempfile.TemporaryDirectory(prefix='nfqws-native-package-')as td:
        stage=Path(td)/'payload';write_files(stage,payload_files(target,engine,source)|web_payload()|smartdns_payload(target,cache,offline))
        hooks={key:package_hook(target,action)for key,action in [('preinst','preinstall'),('postinst','postinstall'),('prerm','preremove'),('postrm','postremove')]}
        if target['format']=='ipk':
            metadata='Package: nfqws2-native\nVersion: '+target['version']+'\nArchitecture: '+target['arch']+'\nDepends: '+', '.join(target['dependencies'])+'\nMaintainer: madworldpay\nSection: net\nLicense: MIT\nDescription: NFQWS2 community native OpenWrt service\n'
            write_files(stage,{'CONTROL/control':(metadata.encode(),0o644),**{'CONTROL/'+k:(v,0o755)for k,v in hooks.items()}})
            tool=pinned_asset(ASSETS['ipkg_build'],cache,offline)
            subprocess.run(['fakeroot','sh',str(tool),str(stage),str(output)],check=True,
                env={**os.environ,'SOURCE_DATE_EPOCH':'0'},stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
            package=output/package_filename(target)
        else:
            package=build_apk(target,stage,hooks,cache,output,offline,sign_key)
        if not package.is_file():raise RuntimeError('Native package tool did not produce its expected artifact')
    checksum=digest(package)
    (output/(package.name+'.sha256')).write_text(checksum+'  '+package.name+'\n')
    return package


def build_apk(target,stage,hooks,cache,output,offline,sign_key=None):
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
        package=output/package_filename(target)
        # sdk fakeroot uses its own matching preload library and loader.
        args=[str(tools/'bin/fakeroot'),str(tools/'bin/apk'),'mkpkg','--info','name:'+target['package'],
            '--info','version:'+target['version'],'--info','arch:'+target['arch'],
            '--info','license:MIT','--info','description:NFQWS2 community native OpenWrt service',
            '--info','origin:nfqws2-native','--info','url:https://github.com/madworldpay/nfqws2-asus-community',
            '--info','maintainer:madworldpay','--info','depends:'+' '.join(target['dependencies']),
            '--files',str(stage),'--output',str(package)]
        keys=None
        if sign_key is not None:
            sign_key=Path(sign_key).absolute();s=sign_key.lstat()
            if sign_key.is_symlink()or not sign_key.is_file()or s.st_nlink!=1 or s.st_uid not in (0,os.getuid())or s.st_mode&0o077:
                raise ValueError('APK signing key must be a private regular file')
            keys=Path(td)/'keys';keys.mkdir(mode=0o700)
            subprocess.run(['openssl','pkey','-in',str(sign_key),'-pubout','-out',str(keys/'nfqws2-native.pem')],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
            args+=['--sign-key',str(sign_key)]
        for name in list(pairs)+['pre-upgrade','post-upgrade']:args+=['--script',name+':'+str(scripts/name)]
        filelist='lib/apk/packages/nfqws2-native.list'
        allfiles=sorted('/'+str(p.relative_to(stage))for p in stage.rglob('*')if p.is_file())+['/'+filelist]
        write_files(stage,{filelist:(('\n'.join(allfiles)+'\n').encode(),0o644)})
        env={**os.environ,'SOURCE_DATE_EPOCH':'0','STAGING_DIR_HOST':str(tools)}
        env.pop('LD_PRELOAD',None)
        subprocess.run(args,check=True,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
        if keys is not None:
            # Never treat a signing command's zero exit alone as trust proof.
            # The router uses native trust verification, with no bypass flag.
            try:subprocess.run([str(tools/'bin/apk'),'verify','--keys-dir',str(keys),str(package)],check=True,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
            except Exception:
                package.unlink(missing_ok=True)
                raise
        return package


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--series',required=True,choices=['24.10','25.12']);p.add_argument('--arch',required=True)
    p.add_argument('--cache',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--offline',action='store_true');p.add_argument('--upx');p.add_argument('--release',default=1,type=int)
    p.add_argument('--sign-key',type=Path,help='Private signing key for native APK creation; keep outside source/output')
    args=p.parse_args()
    try:print(build_native(args.series,args.arch,args.cache,args.output,args.offline,args.upx,args.release,args.sign_key))
    except subprocess.CalledProcessError as e:
        raise SystemExit((e.stdout or b'').decode(errors='replace')+(e.stderr or b'').decode(errors='replace'))
    except (RuntimeError,ValueError)as e:raise SystemExit(str(e))


if __name__=='__main__':main()

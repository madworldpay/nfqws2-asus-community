#!/usr/bin/env python3
"""Build an Entware companion to the vendor's core and web server."""
import argparse
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
PACKAGE = 'nfqws2-keenetic-community'
STOCK_VERSION = '1.3.3'
PACKAGE_REVISION = 2
WEB_STOCK = 'nfqws-keenetic-web_3.0.24_all_entware.ipk'
WEB_SHA = '767b7003db0057d1d46513dcdd6c8c87dc666732a2f7b8c6d756b15cd7900565'
TARGETS = {
    'aarch64-3.10': ('arm64', '1315b74b9cf243a78dd0a23a5ebd8b7c94c6067e29a5713dbcf0541aedea9c91'),
    'mips-3.4': ('mips', 'f0d3bf7389f796e9b07481629d52fe687bda2dcd01b4a1f5518532d5c9ea7245'),
    'mipsel-3.4': ('mipsel', '3da1a9a57cfcc16d243fe128024ecfb2c8f11802d932643ea46509e8ec0465b5'),
}
WEB = 'opt/share/nfqws-asus-web'
PUBLIC = 'opt/share/www/nfqws/nfqws-community'
LIB = 'opt/lib/nfqws2-asus'
SHARE = 'opt/share/nfqws2-asus'
SHARED_DIRS = {'opt','opt/usr','opt/usr/bin','opt/etc','opt/etc/nfqws2','opt/etc/nfqws2/lua',
               'opt/lib','opt/libexec','opt/share','opt/share/licenses','opt/share/www','opt/share/www/nfqws'}
spec = importlib.util.spec_from_file_location('community_entware', PROJECT/'asus/build.py')
entware = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entware)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def document(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'))+'\n').encode(), 0o644


def vendor_files(path, checksum):
    raw = path.read_bytes()
    if digest(raw) != checksum:
        raise ValueError('Unexpected vendor package: '+path.name)
    with tarfile.open(fileobj=io.BytesIO(raw)) as outer:
        member = next(m for m in outer if m.name.removeprefix('./') == 'data.tar.gz')
        with tarfile.open(fileobj=outer.extractfile(member), mode='r:gz') as data:
            return {m.name.removeprefix('./'): data.extractfile(m).read() for m in data if m.isfile()}


def panel(dist):
    files = entware.web_payload(dist)
    if b'<base href="/nfqws-community/">' not in files[WEB+'/index.html'][0]:
        raise ValueError('Build the frontend with --base=/nfqws-community/')
    result = {}
    for path, value in files.items():
        name = path.removeprefix(WEB+'/')
        # Internal PHP and trust records live outside the stock document root.
        if name.endswith('.php') or name.startswith(('vendor-idna/', 'zapret2-pack/')):
            result[path] = value
        elif not name.startswith('vendor-'):
            result[PUBLIC+'/'+name] = value
        if name in ('strategy-picker/index.html','strategy-picker/picker.css','strategy-picker/picker.js'):
            result[path] = value
    # Keep a neutral title before loading the name reported by the firmware.
    for name in ('index.html', 'strategy-picker/index.html'):
        path = PUBLIC+'/'+name
        page, mode = result[path]
        if b'NFQWS2 ASUS' not in page or page.count(b'</head>') != 1:
            raise ValueError('Missing panel title: '+name)
        page = page.replace(b'NFQWS2 ASUS', 'NFQWS2 · Keenetic / Netcraze'.encode())
        page = page.replace(b'<html ', b'<html data-router-brand="Keenetic / Netcraze" ', 1)
        # The picker is served both as a file and through index.php?strategy-picker=1.
        page = page.replace(b'</head>', b'<script src="/nfqws-community/brand.php"></script></head>')
        if name.startswith('strategy-picker/'):
            page = page.replace(b'<a href="../">', b'<a href="../" data-panel-home>', 1)
            result[WEB+'/'+name] = page, mode
        result[path] = page, mode
    result[PUBLIC+'/index.php'] = (HERE/'web-entry.php').read_bytes(), 0o644
    result[PUBLIC+'/brand.php'] = (HERE/'brand.php').read_bytes(), 0o644
    result[WEB+'/keenetic-stock.php'] = (HERE/'stock.php').read_bytes(), 0o644
    result[WEB+'/keenetic-smartdns.php'] = (HERE/'smartdns.php').read_bytes(), 0o644
    result[WEB+'/platform-profile.json'] = (b'{"schema_version":1,"platform":"keenetic-entware"}\n', 0o644)
    manifest = json.loads(files[WEB+'/manifest.json'][0])
    manifest.update(name='NFQWS2 · Keenetic / Netcraze', short_name='NFQWS2', start_url='/nfqws-community/')
    for icon in manifest['icons']:
        icon['src'] = icon['src'].lstrip('/')
    result[PUBLIC+'/manifest.json'] = document(manifest)
    for brand in ('Keenetic', 'Netcraze'):
        result[PUBLIC+'/manifest-'+brand.lower()+'.json'] = document({**manifest, 'name': 'NFQWS2 · '+brand})
    for name in ('library','paths','queues','plan','transaction'):
        leaf='device-profiles-'+name+'.php'
        result[WEB+'/'+leaf] = entware.local('experimental/device-profiles/'+leaf)
    result[LIB+'/config.php'] = entware.local('openwrt/config.php')
    result[LIB+'/import-config.php'] = entware.local('webui/web/public/import-config.php')
    result[LIB+'/diagnostics.sh'] = entware.local('asus/diagnostics.sh')
    result[LIB+'/keenetic-diagnostics.sh'] = entware.local('keenetic/diagnostics.sh', True)
    result[LIB+'/keenetic-resource-layout.php'] = entware.local('keenetic/resource-layout.php')
    result[LIB+'/keenetic-update-worker.php'] = entware.local('keenetic/update-worker.php')
    result[SHARE+'/update-release-key.pem'] = entware.local('updates/trusted-release-key.pem')
    worker, _ = entware.local('asus/smartdns/worker.sh')
    result[LIB+'/smartdns/worker.sh'] = worker.replace(b'bb=/opt/libexec/nfqws2-asus/busybox', b'bb=/opt/bin/busybox'), 0o755
    result[LIB+'/smartdns/worker.php'] = entware.local('asus/smartdns/worker.php')
    result['opt/etc/init.d/S49nfqws-community-smartdns'] = entware.local('keenetic/smartdns-init.sh', True)
    for name in ('guard.sh','probe.sh','drop.sh','stop.sh','worker.php','cli.php'):
        result[LIB+'/dpi/'+name] = entware.local('asus/dpi/'+name)
    result[LIB+'/dpi/paths.sh'] = entware.local('keenetic/dpi-paths.sh')
    for path in sorted((PROJECT/'support').glob('*.json')):
        result[SHARE+'/'+path.name] = path.read_bytes(), 0o644
    result[SHARE+'/profile-catalog-public.pem'] = entware.local('asus/profile-catalog-public.pem')
    result.update({SHARE+'/'+name: value for name, value in entware.packaged_catalog.payload(PROJECT).items()})
    result[SHARE+'/defaults/nfqws2.conf'] = entware.local('core/etc/nfqws2/nfqws2.conf')
    entware.licenses(result, PACKAGE)
    for name in ('LICENSE','THIRD-PARTY-NOTICES.txt'):
        result['opt/share/licenses/'+PACKAGE+'/'+name] = entware.local(name)
    modules = PROJECT/'webui/web/node_modules'
    notices = [str(p.relative_to(modules))+'\n'+p.read_text(errors='replace') for p in sorted(modules.rglob('*'))
               if p.is_file() and p.name.lower().split('.')[0] in ('license','licence','notice','copying')]
    if not notices:
        raise ValueError('Missing frontend licenses')
    result['opt/share/licenses/'+PACKAGE+'/frontend-notices.txt'] = '\n\n'.join(notices).encode(), 0o644
    return result


def build(args):
    vendor_web=vendor_files(args.cache/WEB_STOCK, WEB_SHA)
    common=panel(args.dist)
    detector=json.loads((PROJECT/'openwrt/dpi-assets.json').read_bytes())
    number=(PROJECT/'BUILD_NUMBER').read_text().strip()
    if not number.isdecimal() or int(number)<1:
        raise ValueError('Invalid community build number')
    version=f'{STOCK_VERSION}+b{number}-{PACKAGE_REVISION}'
    args.output.mkdir(parents=True,exist_ok=True)
    for arch in args.arch or TARGETS:
        family, checksum=TARGETS[arch]
        stock=vendor_files(args.cache/f'nfqws2-keenetic_{STOCK_VERSION}_{arch}.ipk',checksum)
        files=dict(common)
        index = PUBLIC+'/index.html'
        page, mode = files[index]
        files[index] = page.replace(b'<html ', f'<html data-entware-arch="{arch}" '.encode(), 1), mode
        # Factories are separate from the operator's active config and lists.
        files[SHARE+'/defaults/nfqws2.conf']=stock['opt/etc/nfqws2/nfqws2.conf'],0o600
        resources={}
        for path, raw in stock.items():
            rel=path.removeprefix('opt/etc/nfqws2/')
            if rel.startswith('lua/') and rel.endswith('.lua.gz'):
                key=rel[:-3];raw=gzip.decompress(raw);dest=SHARE+'/factory/'+key
            elif rel.startswith('blobs/'):
                key='blob/'+Path(rel).name;dest=SHARE+'/defaults/'+rel
            else:
                continue
            files[dest]=raw,0o644
            resources[key]={'bytes':len(raw),'sha256':digest(raw)}
        for name in ('local-guarded-ts.lua', 'local-tls13-stun.lua'):
            raw, _ = entware.local('asus/lua/'+name)
            key = 'lua/'+name
            files[SHARE+'/factory/'+key] = raw, 0o644
            resources[key] = {'bytes':len(raw), 'sha256':digest(raw)}
        entware.blob_bundle.add_bundle(files, SHARE, SHARE+'/defaults')
        lists=entware.blob_bundle.add_module_resources(files, SHARE+'/factory/lists', SHARE+'/defaults/blobs')
        for path,(raw,_) in files.items():
            if path.startswith(SHARE+'/defaults/blobs/'):
                resources['blob/'+Path(path).name]={'bytes':len(raw),'sha256':digest(raw)}
        binary=stock['opt/usr/bin/nfqws2']
        artifact=detector['artifacts'][family]
        machine=int.from_bytes(binary[18:20], 'little' if binary[5]==1 else 'big')
        if binary[:4]!=b'\x7fELF' or [binary[4],binary[5],machine]!=[artifact['elf_class'],artifact['elf_data'],artifact['elf_machine']]:
            raise ValueError('Unexpected target ELF: '+arch)
        files[SHARE+'/report-baseline.json']=document({'schema_version':1,'package_version':version,
            'web_version':entware.WEB_VERSION,'resources':resources,'package_lists':lists,
            'engine':{'version':'1.0.7','provider':'nfqws2-keenetic','sha256':digest(binary),'elf_class':binary[4],'elf_machine':machine}})
        files[SHARE+'/keenetic-dpi-artifact.json']=document({'schema_version':1,'arch':arch,'engine':family,
            'version':detector['version'],'artifact':artifact})
        files.update(entware.dpi_terminal_payload(family))
        entware.public_payload.add_synthesis_seeds(files, WEB, SHARE, SHARE+'/factory/lua', number)
        if set(files)&(stock.keys()|vendor_web.keys()):
            raise ValueError('Community payload collides with a stock package')
        control=('Package: '+PACKAGE+'\nVersion: '+version+'\nArchitecture: '+arch+'\n'
            'Maintainer: NFQWS2 Community\nLicense: MIT\nSection: net\n'
            'Depends: nfqws2-keenetic (= '+STOCK_VERSION+'), nfqws-keenetic-web (>= 3.0.24), busybox, flock, php8-cgi, php8-mod-session, php8-mod-openssl, ca-bundle\n'
            'Conflicts: nfqws2-asus, nfqws-asus-web\n'
            'Description: Community panel for the stock KeeneticOS nfqws2 service\n').encode()
        controls={'control':(control,0o644),'preinst':entware.local('keenetic/preinst',True),
                  'postinst':entware.local('keenetic/postinst',True)}
        package=entware.compressed_tar({'debian-binary':(b'2.0\n',0o644),
            'control.tar.gz':(entware.compressed_tar(controls),0o644),
            'data.tar.gz':(entware.compressed_tar(files,omit_directories=SHARED_DIRS),0o644)})
        name=f'{PACKAGE}_{version}_{arch}.ipk'
        with (args.output/name).open('xb') as f:
            f.write(package)
        print(f'{digest(package)}  {name}')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for arg in ('cache','dist','output'):
        parser.add_argument('--'+arg,required=True,type=Path)
    parser.add_argument('--arch',action='append',choices=TARGETS)
    build(parser.parse_args())

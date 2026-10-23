#!/usr/bin/env python3
"""Build standalone ASUS IPKs. Downloads are pinned; nothing is published.

Requires a production frontend build in webui/web/dist. --offline refuses any
download and uses only already verified files from --cache.
"""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import os
import shutil
import shlex
import subprocess
import tempfile
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {
    'armv7-3.2': {'opkg_arch': 'all', 'filename_arch': 'armv7', 'family': 'armv7', 'elf_class': 1, 'elf_machine': 40,
                 'engine_asset': 'nfqws2-keenetic_1.3.2_all_entware.ipk',
                 'engine_member': 'opt/tmp/nfqws2_binary/nfqws2-armv7',
                 'packed_sha256': '19da1dd9e7f49e061bc7735f690d1a42b55f562976fa820a5794c28695412cbe',
                 'unpacked_sha256': '8bdb300328a358c069d11e957e4f88b23883abbbeb659c9ffa1ff48090ad70c6'},
    'aarch64-3.10': {'opkg_arch': 'aarch64-3.10', 'elf_class': 2, 'elf_machine': 183,
                     'engine_asset': 'nfqws2-keenetic_1.3.2_aarch64-3.10.ipk',
                     'engine_member': 'opt/usr/bin/nfqws2'},
}
for arch, target in TARGETS.items():
    for component, stem in [('busybox', 'busybox_1.37.0-6'),
                            ('lighttpd', 'lighttpd_1.4.82-2'),
                            ('mod_cgi', 'lighttpd-mod-cgi_1.4.82-2')]:
        target[component+'_asset'] = f'{stem}_{arch}.ipk'


def validate_elf(data, target, component):
    if (len(data) < 20 or data[:4] != b'\x7fELF' or
            data[4] != target['elf_class'] or data[5] != 1 or
            int.from_bytes(data[18:20], 'little') != target['elf_machine']):
        raise RuntimeError(f"Wrong ELF for {target['opkg_arch']}: {component}")


def prepare_engine(data, target):
    """Unpack the pinned ARM ELF on the build host, never on the router.

    UPX's old ARM loader can leave /proc/PID/exe unreadable on Linux2.6.
    Keep strict process identity checks and verify the derived bytes instead.
    """
    if 'unpacked_sha256' not in target:
        return data
    if hashlib.sha256(data).hexdigest() != target['packed_sha256']:
        raise RuntimeError('Unexpected packed engine SHA256')
    upx = os.environ.get('NFQWS_BUILD_UPX') or shutil.which('upx') or shutil.which('upx-ucl')
    if not upx:
        raise RuntimeError('ARM build requires host UPX (upx/upx-ucl or NFQWS_BUILD_UPX=/path/to/upx)')
    with tempfile.TemporaryDirectory(prefix='nfqws2-unpack-') as td:
        source, result = Path(td)/'packed', Path(td)/'unpacked'
        source.write_bytes(data)
        subprocess.run([upx, '-d', '-o', str(result), str(source)], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
                       env={k: v for k, v in os.environ.items() if k != 'UPX'})
        unpacked = result.read_bytes()
    if hashlib.sha256(unpacked).hexdigest() != target['unpacked_sha256']:
        raise RuntimeError('Unexpected unpacked engine SHA256')
    return unpacked
CORE_VERSION = '1.3.2-asus6'
WEB_VERSION = (ROOT/'VERSION').read_text().strip()
ASSETS = json.loads((ROOT/'asus/assets.json').read_text())


def package_version(build_number=None):
    number = (ROOT/'BUILD_NUMBER').read_text().strip() if build_number is None else str(build_number)
    if not re.fullmatch(r'[1-9][0-9]{0,8}', number):
        raise ValueError('Build number must be a positive decimal integer without leading zeros')
    return f'{CORE_VERSION}+b{number}'


def runtime_shim(family, service, binary):
    return (f'#!/bin/sh\n. /opt/lib/nfqws2-asus/abi.sh || exit 1\n'
            f'abi=$(asus_resolve_package_abi {family}) || exit 1\n'
            f'exec /opt/libexec/{service}/"$abi"/{binary} "$@"\n').encode(), 0o755


def asset(name, cache, offline):
    path = cache / name
    expected = ASSETS[name]
    if not path.exists():
        if offline:
            raise RuntimeError(f'Missing cached asset: {name}')
        print('Downloading', name)
        data = urllib.request.urlopen(expected['url'], timeout=60).read()
        if hashlib.sha256(data).hexdigest() != expected['sha256']:
            raise RuntimeError(f'SHA256 mismatch: {name}')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected['sha256']:
        raise RuntimeError(f'SHA256 mismatch: {name}')
    with tarfile.open(fileobj=io.BytesIO(data)) as outer:
        member = next(m for m in outer if m.name.removeprefix('./') == 'data.tar.gz')
        with tarfile.open(fileobj=io.BytesIO(outer.extractfile(member).read())) as inner:
            # Read bytes only; never extract paths/symlinks from external archives.
            return {m.name.removeprefix('./'): inner.extractfile(m).read() for m in inner if m.isfile()}


def compressed_tar(files):
    """files: path -> (bytes, mode). Normalize ownership, timestamps and order."""
    stream = io.BytesIO()
    with gzip.GzipFile(fileobj=stream, mode='wb', filename='', mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode='w', format=tarfile.USTAR_FORMAT) as tar:
            directories = set()
            for name in files:
                path = PurePosixPath(name)
                if path.is_absolute() or '..' in path.parts:
                    raise ValueError(f'Unsafe package path: {name}')
                directories.update(str(p) for p in path.parents if str(p) != '.')
            for name in sorted(directories):
                info = tarfile.TarInfo(name)
                info.type, info.mode = tarfile.DIRTYPE, 0o755
                tar.addfile(info)
            for name, (content, mode) in sorted(files.items()):
                info = tarfile.TarInfo(name)
                info.size, info.mode = len(content), mode
                tar.addfile(info, io.BytesIO(content))
    return stream.getvalue()


def local(path, executable=False):
    return (ROOT/path).read_bytes(), 0o755 if executable else 0o644


def update_launcher(target, base=None, stem='opkg-launch', manifest='launchers.json'):
    base = base or ROOT/'asus/update'
    meta = json.loads((base/'bin'/manifest).read_text())
    if meta['source_sha256'] != hashlib.sha256((base/(stem+'.c')).read_bytes()).hexdigest():
        raise RuntimeError('Update launcher source changed; reproduce both launchers first')
    family = 'aarch64' if target['elf_class'] == 2 else 'armv7'
    data = (base/'bin'/(family+'-'+stem)).read_bytes()
    if hashlib.sha256(data).hexdigest() != meta['outputs'][family]['sha256']:
        raise RuntimeError('Update launcher hash mismatch')
    validate_elf(data, target, 'update-launch')
    if int.from_bytes(data[16:18], 'little') != 2:
        raise RuntimeError('Update launcher must be a static executable')
    is64 = target['elf_class'] == 2
    offset = int.from_bytes(data[32:40] if is64 else data[28:32], 'little')
    size = int.from_bytes(data[54:56] if is64 else data[42:44], 'little')
    count = int.from_bytes(data[56:58] if is64 else data[44:46], 'little')
    if count > 16 or size != (56 if is64 else 32) or offset+size*count > len(data):
        raise RuntimeError('Invalid update launcher program headers')
    for index in range(count):
        header = data[offset+index*size:offset+(index+1)*size]
        kind = int.from_bytes(header[:4], 'little')
        flags = int.from_bytes(header[4:8] if is64 else header[24:28], 'little')
        if kind in [2, 3] or kind == 0x6474e551 and flags & 1:
            raise RuntimeError('Update launcher must not depend on a loader or executable stack')
    return data, 0o755


def licenses(data, package):
    for path in sorted((ROOT/'licenses').iterdir()):
        if path.is_file():
            data[f'opt/share/licenses/{package}/{path.name}'] = (path.read_bytes(), 0o644)
    data[f'opt/share/licenses/{package}/UPSTREAM.md'] = local('UPSTREAM.md')
    if package == 'nfqws2-asus':
        # Unified payload: keep the complete supplement once, not once per service.
        for name in ['LICENSE', 'THIRD-PARTY-NOTICES.txt']:
            data[f'opt/share/licenses/{package}/{name}'] = local(name)


def relay_preserver(action, version, *, opt='/opt', php='/opt/bin/php-cgi', owner=0, busybox=None, script_parent=None):
    """Inline the bounded preserver: old updaters accept no new control names."""
    if action not in ['prepare', 'finish']:
        raise ValueError('Invalid relay preservation action')
    quote = lambda value: "'" + str(value).replace('\\', '\\\\').replace("'", "\\'") + "'"
    digest = hashlib.sha256((ROOT/'asus/support-relay.json').read_bytes()).hexdigest()
    script = (ROOT/'asus/ipk/relay-config.php').read_text()
    script += ('\ntry {(new AsusRelayConffile('+quote(opt)+','+quote(version)+','+quote(digest)+','+str(int(owner))+'))->'+action+'();}'
               'catch(Throwable $e){file_put_contents("php://stderr","Cannot preserve support delivery settings.\\n");exit(1);}\n')
    bb=shlex.quote(busybox) if busybox else '"$ASUS_MIGRATION_BUSYBOX"'
    parent=shlex.quote(script_parent+'/.relay-script.XXXXXX') if script_parent else '"$ASUS_MIGRATION_DIR/.relay-script.XXXXXX"'
    secure_parent='' if script_parent else 'asus_migration_safe_dir "$ASUS_MIGRATION_DIR" || exit 1\n'
    return ('umask 077\n'+secure_parent+'ASUS_RELAY_SCRIPT_DIR=$('+bb+' mktemp -d '+parent+') || exit 1\n'+
            bb+' cat > "$ASUS_RELAY_SCRIPT_DIR/config.php" <<\'NFQWS_RELAY_CONFIG_PHP\'\n'+script+
            'NFQWS_RELAY_CONFIG_PHP\n'+
            'ASUS_RELAY_SCRIPT_STATUS=0\n'+shlex.quote(php)+' -n -d register_argc_argv=1 -q -f "$ASUS_RELAY_SCRIPT_DIR/config.php" || ASUS_RELAY_SCRIPT_STATUS=$?\n'+
            bb+' rm -f "$ASUS_RELAY_SCRIPT_DIR/config.php" || ASUS_RELAY_SCRIPT_STATUS=1\n'+
            bb+' rmdir "$ASUS_RELAY_SCRIPT_DIR" || ASUS_RELAY_SCRIPT_STATUS=1\n'+
            '[ "$ASUS_RELAY_SCRIPT_STATUS" = 0 ] || exit 1\n').encode()


def package(output, name, version, depends, conflicts, payload, prefix, conffiles='', arch='aarch64-3.10', filename_arch=None, family=None):
    control = {
        'Package': name, 'Version': version, 'Architecture': arch,
        'Maintainer': 'ASUS NFQWS Contributors <contributors@example.invalid>',
        'Depends': depends, 'Conflicts': conflicts, 'Replaces': 'nfqws-asus-web', 'Section': 'net',
        'License': 'Multiple (MIT, GPL-2.0, LGPL-2.1, BSD-3-Clause and others); see THIRD-PARTY-NOTICES.txt',
        'Description': f'{name}: NFQWS2 and WebUI for ASUS routers',
        'Installed-Size': str(sum(len(v[0]) for v in payload.values())),
    }
    scripts = {'control': (''.join(f'{k}: {v}\n' for k, v in control.items()).encode(), 0o644)}
    for script in ['preinst', 'postinst', 'prerm', 'postrm']:
        source = script if script in ['preinst', 'postrm'] else prefix+'-'+script
        scripts[script] = local('asus/ipk/'+source, True)
        if script == 'preinst':
            scripts[script] = (scripts[script][0].replace(b"ASUS_PACKAGE_ARCH='aarch64-3.10'", f"ASUS_PACKAGE_ARCH='{family or arch}'".encode()), 0o755)
            scripts[script] = (scripts[script][0].replace(b'. /opt/lib/nfqws2-asus/abi.sh', (ROOT/'asus/abi.sh').read_bytes()), 0o755)
        if prefix == 'unified' and script in ['preinst', 'postinst']:
            source_bytes = scripts[script][0]
            migration = (ROOT/'asus/ipk/migration.sh').read_bytes()
            if script == 'postinst':
                migration += b'\n'+(ROOT/'asus/ipk/defaults.sh').read_bytes()
            source_bytes = b'#!/bin/sh\n'+migration+b'\n'+source_bytes.split(b'\n', 1)[1]
            if script == 'preinst':
                source_bytes = source_bytes.replace(b"model=''", b"asus_migration_save || exit $?\nmodel=''", 1)
                source_bytes = source_bytes.replace(b'asus_preserve_relay() { :; }',b'asus_preserve_relay() {\nasus_migration_select_busybox || return 1\n'+relay_preserver('prepare',version)+b'}',1)
            else:
                source_bytes = source_bytes.replace(b'set -e\n',b'set -e\n'+relay_preserver('finish',version),1)
            scripts[script] = source_bytes, 0o755
    if prefix == 'unified':
        # These exact, pinned payload tools are also available to preinst before
        # unpacking. Reinstall must back up retained data after remove deleted
        # the private runtime; stock ASUS BusyBox may lack SHA256 and stat.
        helpers = ({'aarch64-3.10': 'opt/libexec/nfqws2-asus/busybox'} if (family or arch) == 'aarch64-3.10' else
                   {abi: f'opt/libexec/nfqws2-asus/{abi}/busybox' for abi in ['armv7-2.6', 'armv7-3.2']})
        for abi, source in helpers.items():
            scripts['busybox-migration-'+abi] = payload[source][0], 0o755
    if conffiles:
        scripts['conffiles'] = conffiles.encode(), 0o644
    result = compressed_tar({
        'debian-binary': (b'2.0\n', 0o644),
        'control.tar.gz': (compressed_tar(scripts), 0o644),
        'data.tar.gz': (compressed_tar(payload), 0o644),
    })
    path = output/f'{name}_{version}_{filename_arch or arch}.ipk'
    path.write_bytes(result)
    print(path.name, len(result), 'bytes')


def build_one(cache, output, offline, arch, build_number=None):
    target = TARGETS[arch]
    nfq = asset(target['engine_asset'], cache, offline)
    core = {}
    for name, content in nfq.items():
        if name == 'opt/usr/bin/nfqws2' or name.startswith(('opt/etc/nfqws2/lua/', 'opt/etc/nfqws2/blobs/', 'opt/etc/nfqws2/lists/')):
            if name.endswith('.lua.gz'):
                name, content = name[:-3], gzip.decompress(content)
            if name.startswith('opt/etc/nfqws2/lists/'):
                name += '.notactive'
            core[name] = content, 0o755 if '/bin/' in name else 0o644
    engine = prepare_engine(nfq[target['engine_member']], target)
    validate_elf(engine, target, 'engine')
    core['opt/usr/bin/nfqws2'] = engine, 0o755
    core['opt/etc/nfqws2/lua/local-guarded-ts.lua'] = local('asus/lua/local-guarded-ts.lua')
    baseline = {'schema_version': 1, 'package_version': package_version(build_number), 'web_version': WEB_VERSION,
                'engine': {'version': '1.0.6', 'provider': 'nfqws2-keenetic',
                           'sha256': hashlib.sha256(engine).hexdigest(),
                           'elf_class': engine[4], 'elf_machine': int.from_bytes(engine[18:20], 'little')},
                'resources': {}}
    for resource_name, (resource_data, _) in core.items():
        for kind, directory in [('lua', 'lua'), ('blob', 'blobs')]:
            prefix = f'opt/etc/nfqws2/{directory}/'
            if resource_name.startswith(prefix):
                baseline['resources'][kind + '/' + resource_name[len(prefix):]] = {
                    'sha256': hashlib.sha256(resource_data).hexdigest(), 'bytes': len(resource_data)}
    core['opt/share/nfqws2-asus/report-baseline.json'] = (
        (json.dumps(baseline, sort_keys=True, separators=(',', ':')) + '\n').encode(), 0o644)
    family = target.get('family', arch)
    core['opt/lib/nfqws2-asus/target.sh'] = f"ASUS_PACKAGE_ARCH='{family}'\n".encode(), 0o644
    config = (ROOT/'core/etc/nfqws2/nfqws2.conf').read_text()
    config = config.replace('# Provider network interface, e.g. eth3\n'
                            '# You can specify multiple interfaces separated by space, e.g. ISP_INTERFACE="eth3 nwg1"',
                            '# ASUS WAN: ISP_INTERFACE="" selects active WAN interfaces automatically.\n'
                            '# For manual selection, separate interface names with spaces, e.g. ISP_INTERFACE="eth0 ppp0"')
    config = config.replace('ISP_INTERFACE="eth3"', 'ISP_INTERFACE=""').replace('IPV6_ENABLED=1', 'IPV6_ENABLED=0')
    config = re.sub(r'# Keenetic policy name\nPOLICY_NAME=.*?POLICY_EXCLUDE=0',
                    '# ASUS client selection: all, include or exclude\nASUS_CLIENT_MODE="all"\n'
                    '# Space-separated IP addresses or CIDRs\nASUS_CLIENTS4=""\nASUS_CLIENTS6=""', config, flags=re.S)
    core['opt/etc/nfqws2/nfqws2.conf.notactive'] = config.encode(), 0o600
    for name in ['guard.sh', 'probe.sh', 'drop.sh', 'stop.sh', 'worker.php', 'cli.php']:
        core['opt/lib/nfqws2-asus/dpi/'+name] = local('asus/dpi/'+name)
    core['opt/bin/nfqws2-dpi'] = local('asus/dpi/cli.sh', True)
    if family == 'armv7':
        legacy_dpi = (ROOT/'asus/dpi/legacy/dpi-detector-armv5te').read_bytes()
        legacy_spec = json.loads((ROOT/'support/dpi-catalog.json').read_text())['artifacts']['armv7-2.6']
        validate_elf(legacy_dpi, target, 'legacy DPI Detector')
        if len(legacy_dpi) != legacy_spec['size'] or hashlib.sha256(legacy_dpi).hexdigest() != legacy_spec['sha256']:
            raise RuntimeError('Unexpected legacy DPI Detector payload')
        # Dormant package data; only the consented installer makes an executable copy.
        core['opt/libexec/nfqws2-asus/optional/dpi-detector-armv5te'] = legacy_dpi, 0o644
    for name in ['worker.sh', 'worker.php', 'cli.php', 'config-worker.sh', 'config-worker.php',
                 'native-state.sh', 'native-common.sh', 'primary-dns.sh', 'recovery.sh',
                 'lifecycle.sh', 'runtime.sh', 'control.sh', 'control.php', 'forwarding.awk', 'hook-edit.awk']:
        core['opt/lib/nfqws2-asus/smartdns/'+name] = local('asus/smartdns/'+name, name.endswith('.sh'))
    tools = {'schema_version': 1}
    for stem, manifest in [('dns-probe', 'probes.json'), ('session-owner', 'owners.json')]:
        helper = update_launcher(target, ROOT/'asus/smartdns', stem, manifest)
        core['opt/lib/nfqws2-asus/smartdns/'+stem] = helper
        tools[stem.replace('-', '_')+'_sha256'] = hashlib.sha256(helper[0]).hexdigest()
    core['opt/lib/nfqws2-asus/smartdns/tools.json'] = json.dumps(tools, sort_keys=True).encode(), 0o644
    core['opt/bin/nfqws2-smartdns'] = local('asus/smartdns/cli.sh', True)
    core['opt/bin/nfqws2-smartdns-control'] = local('asus/smartdns/control-cli.sh', True)
    core['opt/etc/init.d/S80nfqws2-smartdns'] = local('asus/smartdns/init.sh', True)
    core['opt/share/nfqws2-asus/smartdns-catalog.json'] = local('support/smartdns-catalog.json')
    for name in ['dpi-catalog.json', 'dpi-profile.json', 'dpi-native-defaults.json', 'dpi-analysis-v2.schema.json', 'dpi-report.schema.json', 'dpi-envelope.schema.json', 'dpi-saved.schema.json', 'strategy.schema.json', 'strategy-v2.schema.json', 'resources.schema.json', 'dns-share.schema.json', 'share-v4.schema.json', 'share-envelope.schema.json', 'report.schema.json']:
        core['opt/share/nfqws2-asus/'+name] = local('support/'+name)
    core['opt/share/nfqws2-asus/package-manifest.schema.json'] = local('updates/package-manifest.schema.json')
    core['opt/share/nfqws2-asus/update-release-key.pem'] = local('updates/trusted-release-key.pem')
    core['opt/libexec/nfqws2-asus/update-launch'] = update_launcher(target)
    core['opt/libexec/nfqws2-asus/location-launch'] = update_launcher(target, ROOT/'asus/share', 'location-launch')
    for name in ['worker.php', 'worker.sh', 'check.sh', 'lifecycle.sh']:
        core['opt/lib/nfqws2-asus/update/'+name] = local('asus/update/'+name, name in ['worker.sh', 'check.sh'])
    core['opt/share/licenses/nfqws2-asus/dpi-detector-MIT.txt'] = local('support/dpi-detector-MIT.txt')
    core['opt/share/doc/nfqws2-asus/USAGE.md'] = local('docs/USAGE.md')
    core['opt/share/doc/nfqws2-asus/IMPORT.md'] = local('docs/IMPORT.md')
    for name in ['platform.sh', 'lifecycle.sh', 'diagnostics.sh', 'abi.sh', 'compatibility.sh', 'legacy.sh']:
        core['opt/lib/nfqws2-asus/'+name] = local('asus/'+name)
    if family == 'armv7':
        profile = ROOT/'asus/legacy/rt-ac87u-384.13_10'
        module = (profile/'nfnetlink_queue.ko').read_bytes()
        validate_elf(module, target, 'legacy NFQUEUE module')
        if hashlib.sha256(module).hexdigest() != '1e5fd88ebf5830d56f6b151de0c791f02b3c3db0a539490fbf32709add0151ab':
            raise RuntimeError('Legacy NFQUEUE module SHA256 mismatch')
        core['opt/lib/nfqws2-asus/legacy/rt-ac87u-384.13_10/nfnetlink_queue.ko'] = module, 0o644
        for path in sorted(profile.iterdir()):
            if path.is_file() and path.suffix not in ['.ko', '.py']:
                core['opt/share/doc/nfqws2-asus/legacy/rt-ac87u-384.13_10/'+path.name] = path.read_bytes(), 0o644
    args = re.search(r'^_startup_args\(\) \{.*?^\}', (ROOT/'core/etc/init.d/common').read_text(), flags=re.M|re.S)
    if not args:
        raise RuntimeError('Pinned upstream argument function missing')
    # Keep the pinned upstream profile construction, including IPv6 binding.
    core['opt/lib/nfqws2-asus/args.sh'] = ('#!/bin/sh\n'+args[0]+'\n').encode(), 0o644
    core['opt/etc/init.d/S51nfqws2'] = local('asus/S51nfqws2', True)
    busybox = asset(target['busybox_asset'], cache, offline)
    validate_elf(busybox['opt/bin/busybox'], target, 'busybox')
    shell_path = '/opt/libexec/nfqws2-asus/busybox'
    if family == 'armv7':
        legacy = asset('busybox_1.36.1-1b_armv7-2.6.ipk', cache, offline)['opt/bin/busybox']
        validate_elf(legacy, target, 'legacy busybox')
        core['opt/libexec/nfqws2-asus/armv7-2.6/busybox'] = legacy, 0o755
        core['opt/libexec/nfqws2-asus/armv7-3.2/busybox'] = busybox['opt/bin/busybox'], 0o755
        core[shell_path[1:]] = runtime_shim(family, 'nfqws2-asus', 'busybox')
    else:
        core[shell_path[1:]] = busybox['opt/bin/busybox'], 0o755
    # Isolate applets from global Entware/POSIX symlinks. In particular, the
    # current Entware busybox preinst requires busybox before first installation.
    for applet in 'awk cat chmod cmp cp cut date find grep head id ip kill mkdir mv readlink rm rmdir sed sh sleep stat sysctl touch tr uname wc'.split():
        core['opt/lib/nfqws2-asus/bin/'+applet] = (
            f'#!{shell_path} sh\nexec {shell_path} {applet} "$@"\n'.encode(), 0o755)
    licenses(core, 'nfqws2-asus')
    conffiles = ''  # Active NFQWS2 config/lists are created once, never unpacked over.

    dist = ROOT/'webui/web/dist'
    for name in ['index.html', 'index.php', 'asus.php', 'ark.php', 'support-report.php',
                 'support-report-io.php', 'support-report-values.php',
                 'support-report-platform.php', 'support-report-network.php',
                 'support-mail.php', 'support-mail-proof.php', 'support-report-dns.php',
                 'share-api.php', 'share-bundle.php', 'share-source.php', 'share-strategy.php',
                 'share-location-worker.php', 'dpi-saved-store.php', 'dpi-saved-projector.php',
                 'import-api.php', 'import-config.php', 'import-document.php',
                 'import-plan.php', 'import-store.php', 'import-transaction.php']:
        if not (dist/name).is_file():
            raise RuntimeError('Build frontend first: cd webui/web && corepack yarn openapi && corepack yarn build')
    web = {'opt/share/nfqws-asus-web/'+str(p.relative_to(dist)): (p.read_bytes(), 0o644)
           for p in sorted(dist.rglob('*')) if p.is_file() and not p.name.endswith('.map')}
    light = asset(target['lighttpd_asset'], cache, offline)
    cgi = asset(target['mod_cgi_asset'], cache, offline)
    validate_elf(light['opt/sbin/lighttpd'], target, 'lighttpd')
    validate_elf(cgi['opt/lib/lighttpd/mod_cgi.so'], target, 'mod_cgi')
    if family == 'armv7':
        legacy_light = asset('lighttpd_1.4.71-1_armv7-2.6.ipk', cache, offline)['opt/sbin/lighttpd']
        legacy_cgi = asset('lighttpd-mod-cgi_1.4.71-1_armv7-2.6.ipk', cache, offline)['opt/lib/lighttpd/mod_cgi.so']
        validate_elf(legacy_light, target, 'legacy lighttpd')
        validate_elf(legacy_cgi, target, 'legacy mod_cgi')
        for abi, elf, module in [('armv7-2.6', legacy_light, legacy_cgi),
                                  ('armv7-3.2', light['opt/sbin/lighttpd'], cgi['opt/lib/lighttpd/mod_cgi.so'])]:
            web[f'opt/libexec/nfqws-asus-web/{abi}/lighttpd'] = elf, 0o755
            web[f'opt/lib/nfqws-asus-web/lighttpd/{abi}/mod_cgi.so'] = module, 0o644
        web['opt/libexec/nfqws-asus-web/lighttpd'] = runtime_shim(family, 'nfqws-asus-web', 'lighttpd')
    else:
        web['opt/libexec/nfqws-asus-web/lighttpd'] = light['opt/sbin/lighttpd'], 0o755
        web['opt/lib/nfqws-asus-web/lighttpd/mod_cgi.so'] = cgi['opt/lib/lighttpd/mod_cgi.so'], 0o644
    # mod_rewrite and mod_setenv are compiled into this pinned Entware binary.
    for name in ['web-lib.sh', 'php-cgi.sh']:
        web['opt/lib/nfqws-asus-web/'+name] = local('asus/'+name, name == 'php-cgi.sh')
    web['opt/etc/init.d/S81nfqws-asus-web'] = local('asus/S81nfqws-asus-web', True)
    web['opt/etc/nfqws-asus-web/auth.json'] = (ROOT/'asus/web-auth.json').read_bytes(), 0o600
    web['opt/etc/nfqws-asus-web/support-relay.json'] = (ROOT/'asus/support-relay.json').read_bytes(), 0o600
    web['opt/share/nfqws2-asus/support-relay-default.json'] = (ROOT/'asus/support-relay.json').read_bytes(), 0o644
    licenses(web, 'nfqws-asus-web')
    # Preserve notices from bundled frontend dependencies, including nested ones.
    notices = []
    modules = ROOT/'webui/web/node_modules'
    for p in sorted(modules.rglob('*')):
        if p.is_file() and p.name.lower().split('.')[0] in ['license', 'licence', 'notice', 'copying']:
            notices.append(str(p.relative_to(modules))+'\n'+p.read_text(errors='replace'))
    if not notices:
        raise RuntimeError('Frontend dependency license files are missing; install with the lockfile first')
    web['opt/share/licenses/nfqws-asus-web/frontend-notices.txt'] = '\n\n'.join(notices).encode(), 0o644
    output.mkdir(parents=True, exist_ok=True)
    overlap = core.keys() & web.keys()
    if overlap:
        raise RuntimeError(f'Overlapping core/web payload: {sorted(overlap)}')
    payload = {**core, **web}
    package(output, 'nfqws2-asus', package_version(build_number),
            'iptables, flock, php8-cgi, php8-mod-session, php8-mod-openssl, ca-bundle, libc, libssp, librt, libpthread, libpcre2, libnettle',
            'nfqws2-keenetic, nfqws-keenetic, tpws-keenetic, nfqws-keenetic-web, nfqws-asus-web',
            payload, 'unified', conffiles+'/opt/etc/nfqws-asus-web/auth.json\n/opt/etc/nfqws-asus-web/support-relay.json\n',
            target['opkg_arch'], target.get('filename_arch', arch), family)



def build(cache, output, offline, architectures=None, build_number=None):
    package_version(build_number)  # Reject invalid identity before producing either IPK.
    for arch in architectures or TARGETS:
        build_one(cache, output, offline, arch, build_number)
    (output/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n'
                                          for p in sorted(output.glob('*.ipk'))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, default=ROOT/'.work/downloads')
    parser.add_argument('--output', type=Path, default=ROOT/'dist')
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--arch', action='append', choices=sorted(TARGETS))
    parser.add_argument('--build-number', help='Explicit release build number; defaults to BUILD_NUMBER')
    cli = parser.parse_args()
    build(cli.cache.resolve(), cli.output.resolve(), cli.offline, cli.arch, cli.build_number)

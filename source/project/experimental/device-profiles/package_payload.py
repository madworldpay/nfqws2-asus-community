"""Add the complete optional device-profile runtime to a combined package.

All changes happen in memory. Unknown hook layouts abort the build, before any
package is written; the active owner configuration is never a package file.
"""
import hashlib
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def _overlay(name):
    spec = importlib.util.spec_from_file_location('nfqws_profiles_' + name, HERE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def integrate(payload, platform):
    if platform == 'asus-entware':
        web = 'opt/share/nfqws-asus-web'
        library = 'opt/lib/nfqws2-asus'
        helper = 'device-profiles-entware.sh'
        hooks = {'init': 'opt/etc/init.d/S51nfqws2',
                 'platform': library + '/platform.sh', 'lifecycle': library + '/lifecycle.sh'}
        required = ['opt/etc/nfqws2/nfqws2.conf.notactive']
    elif platform == 'openwrt':
        web = 'usr/share/nfqws2-web'
        library = 'usr/lib/nfqws2'
        helper = 'device-profiles-native.sh'
        hooks = {'init': library + '/nfqws2-native',
                 'control': library + '/control.sh', 'firewall': library + '/firewall.sh'}
        required = [library + '/config.php', 'usr/share/nfqws2/defaults/nfqws2.conf']
    else:
        raise ValueError('unsupported_device_profiles_platform')
    php_sources = sorted(HERE.glob('device-profiles-*.php'))
    source_names = {path.name for path in php_sources}
    required_sources = ['device-profiles-' + name + '.php' for name in
                        ['lab', 'library', 'paths', 'plan', 'queues', 'runtime', 'transaction']]
    required_sources += [helper, 'device-profiles-lab.html', 'device-profiles-lab.css',
                         'device-profiles-lab.js', 'dispatcher-hook.php.inc', 'native_overlay.py']
    if platform == 'asus-entware':
        required_sources.append('entware_overlay.py')
    for name in required_sources:
        if not (HERE / name).is_file() or (name.endswith('.php') and name not in source_names):
            raise ValueError('incomplete_device_profiles_source: ' + name)
    if any(path in payload for path in ['opt/etc/nfqws2/nfqws2.conf', 'etc/nfqws2/nfqws2.conf']):
        raise ValueError('active_config_in_payload')
    index = web + '/index.php'
    for path in [*hooks.values(), index, *required]:
        if path not in payload:
            raise ValueError('incomplete_device_profiles_payload: ' + path)
    source = {key: payload[path][0].decode('utf-8') for key, path in hooks.items()}
    native = _overlay('native_overlay')
    patched = (_overlay('entware_overlay').patch_entware(source) if platform == 'asus-entware'
               else native.patch_native(source))
    patched_index = native.patch_index(payload[index][0].decode('utf-8'),
                                       (HERE / 'dispatcher-hook.php.inc').read_text())
    result = dict(payload)
    for key, path in hooks.items():
        result[path] = patched[key].encode(), payload[path][1]
    result[index] = patched_index.encode(), payload[index][1]

    additions = {web + '/' + path.name: (path.read_bytes(), 0o644)
                 for path in php_sources}
    for source, destination in [('device-profiles-lab.html', 'device-profiles-lab.html'),
                                ('device-profiles-lab.css', 'device-profiles-lab.css'),
                                ('device-profiles-lab.js', 'device-profiles-lab.js')]:
        additions[web + '/device-profiles-lab/' + destination] = (HERE / source).read_bytes(), 0o644
    additions[library + '/' + helper] = (HERE / helper).read_bytes(), 0o755
    if platform == 'asus-entware':
        additions[library + '/config.php'] = (ROOT / 'openwrt/config.php').read_bytes(), 0o644
        additions[library + '/import-config.php'] = (ROOT / 'webui/web/public/import-config.php').read_bytes(), 0o644
        additions['opt/share/nfqws2-asus/defaults/nfqws2.conf'] = (
            payload['opt/etc/nfqws2/nfqws2.conf.notactive'][0], 0o600)
    manifest = {'schema_version': 1, 'files': {
        '/' + path: hashlib.sha256(result[path][0]).hexdigest() for path in [*hooks.values(), index]}}
    additions[web + '/device-profiles-build.json'] = (
        (json.dumps(manifest, sort_keys=True, separators=(',', ':')) + '\n').encode(), 0o644)
    for path, value in additions.items():
        if path in result and result[path] != value:
            raise ValueError('device_profiles_payload_collision: ' + path)
        result[path] = value
    return result

"""Snapshot a production Vite output; validate every verbatim public asset.

Compiled React inputs are not attested here: callers still build from a frozen
source checkout. Reviewed IDNA files retain their independent pinned supplier.
"""
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path


ZEMIDALA_OFFLINE = 'zapret2-pack/zemidala-offline.json'
SYNTHESIS_SEEDS = 'zapret2-pack/synthesis-seeds.json'


def add_synthesis_seeds(files, web_root, shared_root, lua_root, build_number):
    """Compile only against the catalog and resource bytes in this package."""
    here = Path(__file__).resolve().parent
    extractor_spec = importlib.util.spec_from_file_location('nfqws_synthesis_seeds', here/'synthesis_seeds.py')
    extractor = importlib.util.module_from_spec(extractor_spec)
    extractor_spec.loader.exec_module(extractor)
    pack_spec = importlib.util.spec_from_file_location('nfqws_preset_pack', here.parent/'asus/preset_pack.py')
    preset_pack = importlib.util.module_from_spec(pack_spec)
    pack_spec.loader.exec_module(preset_pack)

    pack_root = web_root + '/zapret2-pack/'
    catalog_root = shared_root + '/profile-catalog/v1/'
    packed = {path.removeprefix(pack_root): record for path, record in files.items() if path.startswith(pack_root)}
    signed = {path.removeprefix(shared_root+'/'): record for path, record in files.items() if path.startswith(catalog_root)}
    lua = {name: extractor.digest(files[lua_root+'/'+name][0]) for name in extractor.STOCK_LUA
           if lua_root+'/'+name in files}
    try:
        if not signed:
            raise ValueError('verified cloud catalog is absent')
        extra = json.loads(packed['samples.json'][0])
        samples = preset_pack.STOCK_SAMPLES | {ident: row['name'] for ident, row in extra.items()}
        blobs = {}
        for ident, name in samples.items():
            path = shared_root+'/defaults/blobs/'+name
            if path in files:
                blobs[extractor.digest(files[path][0])] = ident
        result = extractor.compile_seeds(packed, signed, lua, blobs, int(build_number))
        raw = (json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(',', ':'))+'\n').encode()
        if len(raw) > 262144 or any(len(result[p]) > 256 or any(len(row['sources']) > 128 for row in result[p])
                                   for p in extractor.PROTOCOLS):
            raise ValueError('synthesis seed catalog exceeds runtime bounds')
        files[web_root+'/'+SYNTHESIS_SEEDS] = raw, 0o644
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError('Invalid package inputs for synthesis seed catalog') from error


def zemidala_offline(source, catalog):
    source = Path(source)
    if source.is_symlink() or not source.is_file():
        raise ValueError('invalid Zemidala offline file')
    with source.open('rb') as fd:
        raw = fd.read(65537)
    if len(raw) > 65536:
        raise ValueError('Zemidala offline file is too large')
    records = json.loads(raw)
    expected = {row['id'] for row in json.loads(catalog)['entries']}
    if not isinstance(records, dict) or records.keys() != expected:
        raise ValueError('wrong Zemidala offline roster')
    for ident, record in records.items():
        if not isinstance(record, dict) or record.keys() != {'proto', 'steps'}:
            raise ValueError('invalid Zemidala offline record')
        proto, steps = record['proto'], record['steps']
        if proto not in ('http', 'tls') or not isinstance(steps, list) or not steps or not all(
            isinstance(step, str) and re.fullmatch(r'--lua-desync=[A-Za-z0-9_:+.,<>=!-]+', step)
            for step in steps
        ):
            raise ValueError('invalid Zemidala offline rule')
        digest = hashlib.sha256('\0'.join(('zemidala', proto, *steps)).encode()).hexdigest()[:24]
        if digest != ident:
            raise ValueError('changed Zemidala offline rule')
    return raw, 0o644


def payload(public, dist, verified_vendor):
    public, dist = Path(public), Path(dist)
    try:
        if public.is_symlink() or dist.is_symlink():
            raise ValueError('linked root')
        sources = {}
        for path in public.rglob('*'):
            if path.is_symlink():
                raise ValueError('linked public asset')
            if path.is_dir():
                continue
            if not path.is_file():
                raise ValueError('special public asset')
            name = path.relative_to(public).as_posix()
            if name == ZEMIDALA_OFFLINE:
                raise ValueError('Zemidala offline input belongs outside public source')
            if name == SYNTHESIS_SEEDS:
                raise ValueError('Synthesis seeds must be generated from verified package inputs')
            if name != 'mockServiceWorker.js' and not name.endswith('.map'):
                sources[name] = path
        files = {}
        for path in dist.rglob('*'):
            if path.is_symlink():
                raise ValueError('linked output')
            if path.is_dir():
                continue
            if not path.is_file():
                raise ValueError('special output')
            name = path.relative_to(dist).as_posix()
            if name == 'mockServiceWorker.js':
                raise ValueError('development worker in production output')
            if name.endswith('.map'):
                continue
            if name not in sources and name != 'index.html' and not (name.startswith('assets/') and not name.lower().endswith('.php')):
                raise ValueError('removed or unknown public output: ' + name)
            files[name] = (path.read_bytes(), 0o644)
        # Only the separately hash-pinned IDNA supplier may repair absent/stale
        # dist copies. It cannot bypass freshness for UI/backend modules.
        for name, value in verified_vendor.items():
            if not isinstance(name, str) or not name.startswith('vendor-idna/') or name not in sources:
                raise ValueError('unknown pinned dependency')
            if not isinstance(value, tuple) or len(value) != 2 or value[1] != 0o644 or value[0] != sources[name].read_bytes():
                raise ValueError('invalid pinned dependency')
            files[name] = value
        for name, source in sources.items():
            if name not in files or files[name] != (source.read_bytes(), 0o644):
                raise ValueError('missing or changed asset: ' + name)
        bundled = public.parent.parent/'zemidala-offline.json'
        offline = os.environ.get('NFQWS_ZEMIDALA_OFFLINE_INPUT')
        if not offline and bundled.is_file():
            offline = bundled
        if offline:
            index = 'zapret2-pack/zemidala-index.json'
            if index not in files:
                raise ValueError('missing Zemidala catalog index')
            files[ZEMIDALA_OFFLINE] = zemidala_offline(offline, files[index][0])
        return files
    except (OSError, ValueError, TypeError) as error:
        raise RuntimeError('Rebuild the shared production frontend: public assets are stale or unsafe (' + str(error) + ')') from error

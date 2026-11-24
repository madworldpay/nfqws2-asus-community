"""Snapshot a production Vite output; validate every verbatim public asset.

Compiled React inputs are not attested here: callers still build from a frozen
source checkout. Reviewed IDNA files retain their independent pinned supplier.
"""
import hashlib
import json
import os
import re
from pathlib import Path


ZEMIDALA_OFFLINE = 'zapret2-pack/zemidala-offline.json'


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

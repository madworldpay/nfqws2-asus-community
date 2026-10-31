"""Read the reviewed, pinned public blob bundle without network access."""
import hashlib
import json
from pathlib import Path
import re


def load_bundle(directory=None):
    root = Path(directory) if directory else Path(__file__).resolve().parent / 'blobs'
    catalog = json.loads((root / 'catalog.json').read_text())
    sources = json.loads((root / 'sources.json').read_text())
    if set(catalog) != {'schema_version', 'files'} or catalog['schema_version'] != 1:
        raise ValueError('Invalid blob catalog')
    files = {}
    provenance = {item['name']: item for item in sources['files']}
    for item in catalog['files']:
        if (set(item) != {'name', 'sha256', 'byte_length', 'format', 'label'}
                or not re.fullmatch(r'[a-zA-Z0-9_-]+\.bin', item['name'])
                or item['name'] in files or item['format'] not in ('tls', 'quic', 'stun', 'other')
                or set(item['label']) != {'ru', 'en'}
                or not all(isinstance(value, str) and 0 < len(value) <= 120 for value in item['label'].values())):
            raise ValueError('Invalid blob metadata')
        path = root / 'files' / item['name']
        if path.is_symlink() or not path.is_file():
            raise ValueError('Invalid blob file')
        data = path.read_bytes()
        source = provenance.get(item['name'], {})
        if (not 0 < len(data) <= 262144 or len(data) != item['byte_length']
                or hashlib.sha256(data).hexdigest() != item['sha256']
                or source.get('sha256') != item['sha256'] or source.get('size') != len(data)
                or source.get('source_repo') != 'bol-van/zapret2'
                or source.get('source_ref') != '221d7dff24bfec0cd5ac0a5070b8acef2008af3d'
                or source.get('license') != 'MIT'
                or hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() != source.get('source_blob_sha1')):
            raise ValueError('Pinned blob integrity mismatch: ' + item['name'])
        files[item['name']] = data
    if (not files or set(provenance) != set(files)
            or {path.name for path in (root / 'files').iterdir()} != set(files)):
        raise ValueError('Unlisted blob files')
    return files, catalog, sources


def add_bundle(payload, shared_root, defaults_root):
    """Package defaults only: lifecycle code preserves active owner files."""
    files, catalog, sources = load_bundle()
    for name, data in files.items():
        path = defaults_root + '/blobs/' + name
        if path in payload and payload[path][0] != data:
            raise RuntimeError('Upstream blob differs from pinned bundle: ' + name)
        payload[path] = data, 0o644
    for name, value in [('blob-catalog.json', catalog), ('blob-sources.json', sources)]:
        payload[shared_root + '/' + name] = (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode(), 0o644

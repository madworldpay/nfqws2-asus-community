"""Regular files from a pinned local engine and Lua archive."""
import hashlib
import io
import json
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parent
PIN = json.loads((ROOT / 'engine-release.json').read_text())
PROVENANCE = {key: PIN[key] for key in ('version', 'provider', 'commit', 'patches', 'default_resources_provider')}

def read(cache):
    raw = (cache / PIN['asset']).read_bytes()
    if hashlib.sha256(raw).hexdigest() != PIN['sha256']:
        raise RuntimeError('Engine release archive SHA256 mismatch')
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
        members = archive.getmembers()
        if (len(members) != len(PIN['members']) or
                {item.name for item in members} != PIN['members'].keys() or
                not all(item.isfile() for item in members)):
            raise RuntimeError('Unexpected engine release archive members')
        files = {item.name: archive.extractfile(item).read() for item in members}
    if any(hashlib.sha256(raw).hexdigest() != PIN['members'][name] for name, raw in files.items()):
        raise RuntimeError('Engine release member SHA256 mismatch')
    return files

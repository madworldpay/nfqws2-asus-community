"""Verify and include the frozen public cloud snapshot in each package."""
import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


def read_regular(path, limit):
    if path.is_symlink() or not path.is_file():
        raise ValueError('expected regular snapshot file')
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    if not 0 < len(raw) <= limit:
        raise ValueError('snapshot file exceeds limits')
    return raw


def payload(project):
    project = Path(project)
    root = project/'profile-catalog/snapshot/v1'
    directory = root/'files'
    prefix = 'profile-catalog/v1/'
    try:
        if any(path.is_symlink() or not path.is_dir() for path in (root.parent, root, directory)):
            raise ValueError('unsafe snapshot directory')
        if {path.name for path in root.iterdir()} != {'catalog.json', 'files'}:
            raise ValueError('unexpected snapshot entry')
        raw = read_regular(root/'catalog.json', 131072)
        envelope = json.loads(raw)
        if not isinstance(envelope, dict) or set(envelope) != {'manifest', 'signature'}:
            raise ValueError('invalid snapshot envelope')
        manifest = base64.b64decode(envelope['manifest'], validate=True)
        signature = base64.b64decode(envelope['signature'], validate=True)
        if (not 0 < len(manifest) <= 65536 or len(signature) != 384
                or base64.b64encode(manifest).decode() != envelope['manifest']
                or base64.b64encode(signature).decode() != envelope['signature']):
            raise ValueError('invalid snapshot signature')
        with tempfile.NamedTemporaryFile() as proof:
            proof.write(signature)
            proof.flush()
            subprocess.run(['openssl', 'dgst', '-sha256', '-verify', str(project/'asus/profile-catalog-public.pem'),
                            '-signature', proof.name], input=manifest, capture_output=True, check=True, timeout=15)
        index = json.loads(manifest)
        profiles = index['profiles']
        if index['schema_version'] != 1 or not isinstance(profiles, list) or len(profiles) > 128:
            raise ValueError('invalid snapshot catalog')
        files = {prefix+'catalog.json': (raw, 0o644)}
        expected = set()
        for entry in profiles:
            digest, size = entry['sha256'], entry['size']
            if not re.fullmatch(r'[a-f0-9]{64}', digest) or type(size) is not int or not 1 <= size <= 4194304:
                raise ValueError('invalid snapshot document binding')
            name = digest+'.json'
            content = read_regular(directory/name, size)
            if len(content) != size or hashlib.sha256(content).hexdigest() != digest:
                raise ValueError('snapshot document failed SHA-256 verification')
            expected.add(name)
            files[prefix+'files/'+name] = content, 0o644
        if {path.name for path in directory.iterdir()} != expected:
            raise ValueError('snapshot contains an unlisted document')
        return files
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        raise RuntimeError('Packaged cloud catalog snapshot is missing, changed or unsafe') from error

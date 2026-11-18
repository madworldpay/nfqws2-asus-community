"""Supply exact reviewed Unicode tables even when a frontend fixture omits them."""
import hashlib
import json
from pathlib import Path, PurePosixPath


def payload(public):
    root=Path(public)/'vendor-idna'
    try:
        if root.is_symlink():raise ValueError('symlink')
        if(root/'provenance.json').is_symlink():raise ValueError('symlink')
        raw=(root/'provenance.json').read_bytes();manifest=json.loads(raw);rows=manifest['files']
        if len(rows)!=21:raise ValueError('count')
        files={'vendor-idna/provenance.json':(raw,0o644)}
        pins={'polyfill-intl-idn':'533d68cf99c8f8ee2e8893c59ed59192e92cfd74',
              'polyfill-intl-normalizer':'ebd57ccc7edb93d632e184efbe7693d2517bab3b'}
        for row in rows:
            name=row['destination'];parts=PurePosixPath(name)
            if parts.is_absolute()or str(parts)!=name or any(x in ('.','..')for x in parts.parts)or parts.parts[0]not in ('idn','normalizer'):
                raise ValueError('path')
            if row['commit']!=pins.get(row['repo']):raise ValueError('pin')
            path=root/name
            if any(p.is_symlink()for p in [path,*path.parents]if p==root or root in p.parents):raise ValueError('symlink')
            if row['size']>200000:raise ValueError('size')
            data=path.read_bytes()
            if len(data)!=row['size']or hashlib.sha256(data).hexdigest()!=row['sha256']or hashlib.sha1(('blob '+str(len(data))+'\0').encode()+data).hexdigest()!=row['sha']:
                raise ValueError('hash')
            key='vendor-idna/'+name
            if key in files:raise ValueError('duplicate')
            files[key]=(data,0o644)
        return files
    except (OSError,ValueError,KeyError,TypeError)as error:
        raise RuntimeError('IDNA dependency is missing, changed or unsafe')from error

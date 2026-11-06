#!/usr/bin/env python3
"""Prepare an independent signed, data-only import add-on catalog offline.

Only explicitly reviewed bytes and an explicitly supplied RSA3072 key are read.
This publisher never fetches data, changes routers, or publishes profile v1.
"""
import argparse
import base64
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile


DOCUMENT_LIMIT = 65536
MANIFEST_LIMIT = 65536
ENVELOPE_LIMIT = 131072
ENTRY_FIELDS = {'id', 'title', 'description', 'attribution', 'updated_at',
                'revision', 'min_build', 'size', 'sha256'}
REVIEW_FIELDS = ENTRY_FIELDS - {'size', 'sha256'} | {'file', 'source_sha256'}
DOCUMENT_FIELDS = {'type', 'schema_version', 'id', 'title', 'description', 'kind', 'domains'}
ID = re.compile(r'[a-z0-9][a-z0-9-]{0,63}')
HASH = re.compile(r'[a-f0-9]{64}')
LABEL = re.compile(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?')
NON_PUBLIC_TLDS = {'localhost', 'local', 'lan', 'home', 'internal', 'invalid',
                   'test', 'example', 'onion'}


def unique(pairs):
    value = {}
    for key, child in pairs:
        if key in value:
            raise ValueError('duplicate JSON key')
        value[key] = child
    return value


def decode(raw):
    return json.loads(raw.decode('utf-8'), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('non-finite JSON')))


def no_symlinks(path):
    if any(part.is_symlink() for part in [path, *path.parents]):
        raise ValueError('symlink refused')


def regular(path, maximum):
    no_symlinks(path)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 1 <= info.st_size <= maximum:
        raise ValueError('invalid input file')
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_ino, opened.st_dev, opened.st_nlink, opened.st_size) != (info.st_ino, info.st_dev, 1, info.st_size):
            raise ValueError('input changed')
        raw = stream.read(maximum + 1)
    if len(raw) != info.st_size:
        raise ValueError('input changed')
    return raw


def integer(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum


def text(value, minimum, maximum):
    return isinstance(value, str) and minimum <= len(value) <= maximum and (minimum == 0 or bool(value.strip()))


def domain(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 253 or not value.isascii():
        return False
    labels = value.split('.')
    return (len(labels) >= 2 and all(LABEL.fullmatch(label) for label in labels)
            and bool(re.fullmatch(r'[a-z]{2,63}|xn--[a-z0-9-]{1,59}', labels[-1]))
            and labels[-1] not in NON_PUBLIC_TLDS
            and value != 'home.arpa' and not value.endswith('.home.arpa'))


def validate_entry(row, reviewed=False):
    if not isinstance(row, dict) or set(row) != (REVIEW_FIELDS if reviewed else ENTRY_FIELDS):
        raise ValueError('invalid add-on metadata fields')
    if (not isinstance(row['id'], str) or not ID.fullmatch(row['id'])
            or not text(row['title'], 1, 120) or not text(row['description'], 1, 600)
            or not text(row['attribution'], 0, 240)
            or not integer(row['revision'], 1, 2147483647)
            or not integer(row['min_build'], 92, 999999999)):
        raise ValueError('invalid add-on metadata')
    date = row['updated_at']
    if not isinstance(date, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z', date):
        raise ValueError('invalid updated_at')
    try:
        datetime.strptime(date, '%Y-%m-%dT%H:%M:%SZ')
    except ValueError:
        raise ValueError('invalid updated_at') from None
    digest = row['source_sha256' if reviewed else 'sha256']
    if not isinstance(digest, str) or not HASH.fullmatch(digest):
        raise ValueError('missing reviewed hash' if reviewed else 'invalid content hash')
    if reviewed:
        if not isinstance(row['file'], str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,123}\.json', row['file']):
            raise ValueError('invalid add-on filename')
    elif not integer(row['size'], 1, DOCUMENT_LIMIT):
        raise ValueError('invalid add-on size')


def validate_index(value, reviewed=False):
    if (not isinstance(value, dict) or set(value) != {'schema_version', 'revision', 'addons'}
            or type(value['schema_version']) is not int or value['schema_version'] != 1
            or not integer(value['revision'], 1, 2147483647)
            or not isinstance(value['addons'], list) or len(value['addons']) > 64):
        raise ValueError('invalid add-on catalog')
    ids = set()
    for row in value['addons']:
        validate_entry(row, reviewed)
        if row['id'] in ids:
            raise ValueError('duplicate add-on id')
        ids.add(row['id'])
    return value


def validate_document(raw, entry):
    value = decode(raw)
    if (not isinstance(value, dict) or set(value) != DOCUMENT_FIELDS
            or value['type'] != 'nfqws2_import_addon'
            or type(value['schema_version']) is not int or value['schema_version'] != 1
            or value['kind'] != 'scope_domains_v1'):
        raise ValueError('invalid data-only add-on document')
    if any(value[field] != entry[field] for field in ['id', 'title', 'description']):
        raise ValueError('add-on identity differs from reviewed metadata')
    domains = value['domains']
    if not isinstance(domains, list) or not 1 <= len(domains) <= 64 or not all(domain(item) for item in domains):
        raise ValueError('invalid public domain scope')
    if len(set(domains)) != len(domains):
        raise ValueError('duplicate domain')
    return value


def openssl(arguments, raw=None):
    result = subprocess.run(['openssl', *arguments], input=raw, capture_output=True, timeout=15)
    if result.returncode:
        raise ValueError('OpenSSL key/signature verification failed')
    return result.stdout


def public_key(key):
    regular(key, 8192)
    if stat.S_IMODE(key.stat().st_mode) & 0o077:
        raise ValueError('signing key permissions must be 0600 or 0400')
    public = openssl(['pkey', '-in', str(key), '-passin', 'pass:', '-pubout'])
    modulus = openssl(['rsa', '-pubin', '-noout', '-modulus'], public)
    if not modulus.startswith(b'Modulus=') or int(modulus.removeprefix(b'Modulus=').strip(), 16).bit_length() != 3072:
        raise ValueError('RSA3072 signing key required')
    return public


def verify(envelope, public):
    if len(envelope) > ENVELOPE_LIMIT:
        raise ValueError('add-on envelope too large')
    value = decode(envelope)
    if not isinstance(value, dict) or set(value) != {'manifest', 'signature'}:
        raise ValueError('invalid add-on envelope')
    decoded = []
    for field in ['manifest', 'signature']:
        if not isinstance(value[field], str):
            raise ValueError('invalid add-on envelope encoding')
        raw = base64.b64decode(value[field], validate=True)
        if base64.b64encode(raw).decode() != value[field]:
            raise ValueError('invalid add-on envelope encoding')
        decoded.append(raw)
    raw, signature = decoded
    if len(raw) > MANIFEST_LIMIT or len(signature) != 384:
        raise ValueError('invalid add-on envelope size')
    with tempfile.TemporaryDirectory(prefix='nfqws-addons-verify-') as temporary:
        folder = Path(temporary)
        (folder / 'public.pem').write_bytes(public)
        (folder / 'signature.bin').write_bytes(signature)
        openssl(['dgst', '-sha256', '-verify', str(folder / 'public.pem'),
                 '-signature', str(folder / 'signature.bin')], raw)
    return validate_index(decode(raw))


def write(path, raw, immutable=False):
    no_symlinks(path.parent)
    if path.exists() or path.is_symlink():
        previous = regular(path, DOCUMENT_LIMIT if immutable else ENVELOPE_LIMIT)
        if immutable:
            if previous != raw:
                raise ValueError('immutable file mismatch')
            return
    descriptor, temporary = tempfile.mkstemp(prefix='.write-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fchmod(stream.fileno(), 0o644)
            os.fsync(stream.fileno())
        if immutable:
            try:
                os.link(temporary, path)
            except FileExistsError:
                if regular(path, DOCUMENT_LIMIT) != raw:
                    raise ValueError('immutable file mismatch') from None
        else:
            os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def publish(args):
    paths = [Path(getattr(args, field)).absolute() for field in ['metadata', 'addons_dir', 'output', 'key']]
    for path in paths:
        no_symlinks(path)
    metadata, inputs, output, key = (path.resolve() for path in paths)
    if output.name != 'addons':
        raise ValueError('output must be a separate addons directory')
    if any(path.is_relative_to(output) for path in [metadata, inputs, key]):
        raise ValueError('reviewed inputs and key must be outside the served directory')
    if not inputs.is_dir():
        raise ValueError('invalid add-on input directory')
    approval = validate_index(decode(regular(metadata, ENVELOPE_LIMIT)), reviewed=True)
    index = {'schema_version': 1, 'revision': approval['revision'], 'addons': []}
    files = {}
    for row in approval['addons']:
        raw = regular(inputs / row['file'], DOCUMENT_LIMIT)
        digest = hashlib.sha256(raw).hexdigest()
        if digest != row['source_sha256']:
            raise ValueError('add-on changed since review')
        validate_document(raw, row)
        entry = {field: row[field] for field in ['id', 'title', 'description', 'attribution',
                                                'updated_at', 'revision', 'min_build']}
        entry.update(size=len(raw), sha256=digest)
        index['addons'].append(entry)
        files[digest] = raw
    manifest = json.dumps(index, ensure_ascii=False, separators=(',', ':')).encode()
    if len(manifest) > MANIFEST_LIMIT:
        raise ValueError('add-on catalog too large')
    public = public_key(key)
    signature = openssl(['dgst', '-sha256', '-sign', str(key), '-passin', 'pass:'], manifest)
    envelope = json.dumps({'manifest': base64.b64encode(manifest).decode(),
                           'signature': base64.b64encode(signature).decode()}, separators=(',', ':')).encode() + b'\n'
    verify(envelope, public)
    catalog = output / 'catalog.json'
    if catalog.exists() or catalog.is_symlink():
        previous = verify(regular(catalog, ENVELOPE_LIMIT), public)
        if previous['revision'] >= index['revision']:
            raise ValueError('catalog revision must increase')
    folder = output / 'files'
    no_symlinks(folder)
    # Detect corrupt retained objects before preparing any new public files.
    for digest, raw in files.items():
        path = folder / (digest + '.json')
        if (path.exists() or path.is_symlink()) and regular(path, DOCUMENT_LIMIT) != raw:
            raise ValueError('immutable file mismatch')
    folder.mkdir(parents=True, exist_ok=True, mode=0o755)
    for digest, raw in files.items():
        write(folder / (digest + '.json'), raw, immutable=True)
    write(catalog, envelope)
    print(f'Prepared add-on catalog revision {index["revision"]}: {len(files)} immutable documents')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ['metadata', 'addons-dir', 'key', 'output']:
        parser.add_argument('--' + field, required=True)
    try:
        publish(parser.parse_args())
    except (ValueError, OSError, subprocess.SubprocessError, KeyError, TypeError, RecursionError) as error:
        print('Add-on catalog not prepared: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

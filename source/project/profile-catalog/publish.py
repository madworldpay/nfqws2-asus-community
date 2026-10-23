#!/usr/bin/env python3
"""Validate reviewed inputs and atomically prepare a signed cloud catalog.

No network access, router execution, or automatic approval of submissions.
The signing key and real profiles belong outside the source tree.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ENTRY_FIELDS = {'id', 'title', 'category', 'provider', 'region', 'description',
                'attribution', 'updated_at', 'revision', 'min_build', 'file', 'source_sha256'}
INIT_FILES = {'zapret-lib.lua', 'zapret-antidpi.lua', 'zapret-auto.lua', 'local-guarded-ts.lua'}


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def decode(raw):
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('non-finite JSON')))


def regular(path, maximum):
    for part in [path, *path.parents]:
        if part.is_symlink():
            raise ValueError('symlink refused')
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > maximum:
        raise ValueError('invalid input file')
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_ino, opened.st_dev) != (info.st_ino, info.st_dev):
            raise ValueError('input changed')
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError('input too large')
    return raw


def php(php_binary, code, payload):
    run = subprocess.run([php_binary, '-n', '-r', code, str(ROOT/'webui/web/public')],
                         input=json.dumps(payload).encode(), capture_output=True, timeout=30)
    if run.returncode or run.stderr:
        raise ValueError('PHP validation failed')
    result = decode(run.stdout)
    if isinstance(result, dict) and 'error' in result:
        raise ValueError(str(result['error']))
    return result


def private_fields(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in {'password', 'passwd', 'private_key', 'access_token', 'authorization',
                               'credentials', 'installation_id', 'clients', 'wan_addresses'}:
                raise ValueError('private fields refused')
            private_fields(child)
    elif isinstance(value, list):
        for child in value:
            private_fields(child)
    elif isinstance(value, str):
        if re.search(r'-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----', value):
            raise ValueError('private key refused')


def validate_profile(raw, php_binary):
    value = decode(raw)
    private_fields(value)
    documents = [value]
    if isinstance(value, dict) and 'version' in value:
        documents = []
        for row in value.get('files', []):
            if not isinstance(row, dict) or row.get('type') not in {'strategy', 'resources', 'dns'}:
                raise ValueError('only strategy, resources and DNS may be published')
            documents.append(decode(base64.b64decode(row['data_base64'], validate=True)))
    for document in documents:
        private_fields(document)
        if isinstance(document, dict) and document.get('mode') == 'config':
            # Router identity stays local. Redacted legacy exports remain valid.
            for match in re.finditer(r'^\s*(ISP_INTERFACE|ASUS_CLIENTS4|ASUS_CLIENTS6|POLICY_NAME|USER)\s*=(.*)$', document.get('config', ''), re.M):
                if match[2].strip() not in {'"<hidden>"', "'<hidden>'", '""', "''"}:
                    raise ValueError('router identity refused')
    code = """require $argv[1].'/import-document.php';try{
      $v=json_decode(stream_get_contents(STDIN),true,32,JSON_THROW_ON_ERROR);
      echo json_encode(AsusImportDocument::read([$v['document']]),JSON_THROW_ON_ERROR);
    }catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}"""
    parsed = php(php_binary, code, {'document': raw.decode('utf-8')})
    if parsed['ignored']:
        raise ValueError('diagnostics refused')
    for row in parsed['resources']:
        if row['kind'] == 'lua':
            raise ValueError('Lua is supplied by the package')
        data = base64.b64decode(row['data_base64'], validate=True)
        if b'PRIVATE KEY-----' in data:
            raise ValueError('private key refused')
        if row['kind'] == 'blobs' and re.search(br'<!doctype\s+html|<html\b|version https://git-lfs', data[:2048], re.I):
            raise ValueError('blob is an HTML page or LFS pointer')
    for text in (parsed['values'].values() if isinstance(parsed['values'], dict) else []):
        words = shlex.split(text)
        for pos, word in enumerate(words):
            if word == '--lua-init' or word.startswith('--lua-init='):
                operand = words[pos+1] if word == '--lua-init' and pos+1 < len(words) else word.removeprefix('--lua-init=')
                if not operand.startswith('@/opt/etc/nfqws2/lua/') or operand.rsplit('/', 1)[-1] not in INIT_FILES:
                    raise ValueError('only packaged Lua init is allowed')
    # No Lua attachments are allowed above. These rows model only the package's
    # explicit Lua-presence contract, not measured file bytes. Their hashes are
    # symbolic; no file is reused, written, or trusted from this operator model.
    code = """require $argv[1].'/import-plan.php';try{
      $v=json_decode(stream_get_contents(STDIN),true,32,JSON_THROW_ON_ERROR);
      $doc=$v['document'];$selection=['blocks'=>[],'shared'=>[],'ports'=>[],
        'files'=>[],'dns'=>[],'allow_shared_impact'=>true,
        'allow_incomplete'=>false,'trusted_lua'=>false];
      foreach($doc['values']as $key=>$value)$selection[in_array($key,AsusImportConfig::BLOCKS,true)?'blocks':'shared'][]=['key'=>$key,'value'=>$value];
      foreach($doc['ports']as $key=>$value)$selection['ports'][]=['key'=>$key,'value'=>$value];
      foreach($doc['resources']as $file)$selection['files'][]=['id'=>$file['id']];
      foreach($doc['dns_sources']as $source)$selection['dns'][]=[
        'source_id'=>$source['id'],'source_sha256'=>$source['sha256'],
        'upstreams'=>$source['profile']['upstreams'],
        'records'=>array_map(fn($index,$value)=>['index'=>$index,'value'=>$value],array_keys($source['profile']['records']),$source['profile']['records'])];
      $files=[];foreach($v['packaged_lua']as $name)$files[]=[
        'id'=>substr(hash('sha256','/opt/etc/nfqws2/lua/'.$name),0,32),
        'kind'=>'lua','name'=>$name,'byte_length'=>0,
        'sha256'=>hash('sha256','package-presence:'.$name),'state'=>'available',
        'bundled_lua'=>true,'bundled_name'=>$name];
      $plan=AsusImportPlan::prepare($doc,$selection,'',['files'=>$files,'scan_truncated'=>false],null);
      echo json_encode(['ready'=>$plan['ready'],'problems'=>$plan['problems']],JSON_THROW_ON_ERROR);
    }catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}"""
    plan = php(php_binary, code, {'document': parsed, 'packaged_lua': sorted(INIT_FILES)})
    if not plan['ready']:
        raise ValueError('incomplete dependencies or invalid selectable profile')
    return parsed


def verified(envelope, public_key, php_binary):
    code = """require $argv[1].'/profile-catalog.php';try{
      $v=json_decode(stream_get_contents(STDIN),true,32,JSON_THROW_ON_ERROR);
      echo json_encode(AsusProfileCatalog::verify($v['envelope'],$v['key']),JSON_THROW_ON_ERROR);
    }catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}"""
    return php(php_binary, code, {'envelope': envelope.decode(), 'key': public_key.decode()})


def atomic(path, raw):
    if path.exists() or path.is_symlink():
        regular(path, 4194304)
    descriptor, temporary = tempfile.mkstemp(prefix='.write-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
            os.fchmod(stream.fileno(), 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def publish(args):
    paths = [Path(getattr(args, k)).absolute() for k in
             ['metadata', 'profiles_dir', 'output', 'private_key']]
    for path in paths:
        if any(part.is_symlink() for part in [path, *path.parents]):
            raise ValueError('symlink refused')
    metadata, inputs, output, key = (path.resolve() for path in paths)
    if any(p.is_relative_to(output) for p in [metadata, inputs, key]):
        raise ValueError('private inputs must be outside the served directory')
    for p in [inputs, output, *output.parents]:
        if p.is_symlink():
            raise ValueError('symlink refused')
    approval = decode(regular(metadata, 131072))
    if not isinstance(approval, dict) or set(approval) != {'schema_version', 'revision', 'profiles'} or approval['schema_version'] != 1:
        raise ValueError('invalid metadata')
    if type(approval['revision']) is not int or not 1 <= approval['revision'] <= 2147483647:
        raise ValueError('invalid revision')
    if not isinstance(approval['profiles'], list) or len(approval['profiles']) > 128:
        raise ValueError('invalid profile count')
    regular(key, 8192)
    if stat.S_IMODE(key.stat().st_mode) & 0o077:
        raise ValueError('signing key permissions must be 0600')
    public = subprocess.check_output(['openssl', 'pkey', '-in', str(key), '-pubout'], stderr=subprocess.PIPE, timeout=15)
    index = {'schema_version': 1, 'revision': approval['revision'], 'profiles': []}
    files = {}
    for row in approval['profiles']:
        if not isinstance(row, dict) or set(row) != ENTRY_FIELDS:
            raise ValueError('invalid profile metadata')
        if not isinstance(row['file'], str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,123}\.json', row['file']):
            raise ValueError('invalid profile filename')
        if not isinstance(row['source_sha256'], str) or not re.fullmatch(r'[a-f0-9]{64}', row['source_sha256']):
            raise ValueError('missing reviewed hash')
        raw = regular(inputs/row['file'], 4194304)
        digest = hashlib.sha256(raw).hexdigest()
        if digest != row['source_sha256']:
            raise ValueError('profile changed since review')
        validate_profile(raw, args.php)
        entry = {k: v for k, v in row.items() if k not in {'file', 'source_sha256'}}
        entry.update(size=len(raw), sha256=digest)
        index['profiles'].append(entry)
        files[digest] = raw
    raw_index = json.dumps(index, ensure_ascii=False, separators=(',', ':')).encode()
    if len(raw_index) > 65536:
        raise ValueError('catalog too large')
    signature = subprocess.check_output(['openssl', 'dgst', '-sha256', '-sign', str(key)], input=raw_index, stderr=subprocess.PIPE, timeout=15)
    envelope = json.dumps({'manifest': base64.b64encode(raw_index).decode(),
                           'signature': base64.b64encode(signature).decode()}, separators=(',', ':')).encode() + b'\n'
    verified(envelope, public, args.php)
    catalog = output/'catalog.json'
    if catalog.exists() or catalog.is_symlink():
        previous = verified(regular(catalog, 131072), public, args.php)
        if previous['revision'] >= index['revision']:
            raise ValueError('catalog revision must increase')
    output.mkdir(parents=True, exist_ok=True, mode=0o755)
    folder = output/'files'
    if folder.is_symlink():
        raise ValueError('symlink refused')
    folder.mkdir(exist_ok=True, mode=0o755)
    for digest, raw in files.items():
        path = folder/(digest+'.json')
        if path.exists() or path.is_symlink():
            if regular(path, 4194304) != raw:
                raise ValueError('immutable file mismatch')
        else:
            atomic(path, raw)
    atomic(catalog, envelope)
    print(f'Prepared catalog revision {index["revision"]}: {len(files)} profile files')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['metadata', 'profiles-dir', 'private-key', 'output']:
        parser.add_argument('--'+name, required=True)
    parser.add_argument('--php', default=shutil.which('php'))
    args = parser.parse_args()
    if not args.php:
        parser.error('PHP CLI with OpenSSL required: use --php')
    try:
        publish(args)
    except (ValueError, OSError, subprocess.SubprocessError, KeyError, TypeError) as error:
        print('Catalog not published: '+str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

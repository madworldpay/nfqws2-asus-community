"""Operator-only immutable release publisher. Signing key never enters the feed."""
import argparse
import base64
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import tarfile
import zlib

from common import MAX_PACKAGE, PACKAGE_RE, QUOTA, VERSION_RE, current_version, decode, directory, read_regular


def _control(raw):
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode='r|*') as outer:
            for member in outer:
                if member.name.removeprefix('./') == 'control.tar.gz':
                    if not member.isfile() or member.size > 262144:
                        raise ValueError()
                    compressed = outer.extractfile(member).read(262145)
                    decoder = zlib.decompressobj(31)
                    expanded = decoder.decompress(compressed, 262145)
                    if len(expanded) > 262144 or not decoder.eof:
                        raise ValueError()
                    with tarfile.open(fileobj=io.BytesIO(expanded)) as archive:
                        item = archive.getmember('./control') if './control' in archive.getnames() else archive.getmember('control')
                        if not item.isfile() or item.size > 16384:
                            raise ValueError()
                        fields = {}
                        for line in archive.extractfile(item).read(16385).decode().splitlines():
                            if line.startswith((' ', '\t')) or not line:
                                continue
                            key, value = line.split(':', 1)
                            if key in fields:
                                raise ValueError()
                            fields[key] = value.strip()
                        return fields
                if member.name.removeprefix('./') != 'debian-binary' or member.size > 32:
                    raise ValueError()
    except (ValueError, OSError, tarfile.TarError, UnicodeError, KeyError):
        pass
    raise ValueError('invalid_release')


def _source(source):
    owner = os.geteuid()
    try:
        value = decode(read_regular(source/'release.json', 32768, owner))
        expected = {'schema_version', 'package_version', 'core_version', 'web_version', 'build', 'notes', 'packages'}
        if (not isinstance(value, dict) or set(value) != expected or value['schema_version'] != 1
                or type(value['build']) is not int or not 1 <= value['build'] <= 2147483647
                or not isinstance(value['package_version'], str) or not VERSION_RE.fullmatch(value['package_version'])
                or value['package_version'] != value['core_version']+'+b'+str(value['build'])
                or not isinstance(value['web_version'], str) or not re.fullmatch(r'(?:0|[1-9][0-9]{0,5})\.(?:0|[1-9][0-9]{0,5})\.(?:0|[1-9][0-9]{0,5})', value['web_version'])
                or not isinstance(value['notes'], str) or len(value['notes']) > 2000
                or not isinstance(value['packages'], list) or not 1 <= len(value['packages']) <= 2):
            raise ValueError()
        files, seen = {}, set()
        for package in value['packages']:
            if not isinstance(package, dict) or set(package) != {'family', 'filename', 'size', 'sha256'}:
                raise ValueError()
            family = package['family']
            if (family not in ['aarch64-3.10', 'armv7'] or family in seen
                    or package['filename'] != f'nfqws2-asus_{value["package_version"]}_{family}.ipk'
                    or type(package['size']) is not int or not 1 <= package['size'] <= MAX_PACKAGE
                    or not isinstance(package['sha256'], str) or not re.fullmatch(r'[a-f0-9]{64}', package['sha256'])):
                raise ValueError()
            seen.add(family)
            raw = read_regular(source/package['filename'], MAX_PACKAGE, owner)
            if len(raw) != package['size'] or hashlib.sha256(raw).hexdigest() != package['sha256']:
                raise ValueError()
            control = _control(raw)
            if (control.get('Package') != 'nfqws2-asus' or control.get('Version') != value['package_version']
                    or control.get('Architecture') != ('all' if family == 'armv7' else family)):
                raise ValueError()
            files[package['filename']] = raw
        return value, files
    except (ValueError, TypeError, KeyError, OSError, UnicodeError):
        raise ValueError('invalid_release') from None


def _write(path, raw, group):
    with path.open('xb') as target:
        os.fchmod(target.fileno(), 0o640)
        os.fchown(target.fileno(), -1, group)
        target.write(raw);target.flush();os.fsync(target.fileno())


def _remove_owned_directory(path, owner):
    directory(path, owner)
    entries = list(path.iterdir())
    for item in entries:
        if item.name not in ['manifest.json', 'manifest.sig'] and not PACKAGE_RE.fullmatch(item.name):
            raise ValueError('invalid_state')
        read_regular(item, MAX_PACKAGE if item.name.endswith('.ipk') else 32768, owner)
    for item in entries:
        item.unlink()
    path.rmdir()


def _inventory(root, owner):
    total = 0
    for base, dirs, files in os.walk(root, followlinks=False):
        directory(base, owner)
        for name in dirs:
            directory(Path(base)/name, owner)
        for name in files:
            path = Path(base)/name
            read_regular(path, MAX_PACKAGE, owner)
            total += path.stat().st_size
    return total


def publish_release(source, key, output, quota_bytes=QUOTA):
    source, key, output = Path(source).absolute(), Path(key).absolute(), Path(output).absolute()
    value, files = _source(source)
    owner = os.geteuid()
    key_info = key.lstat()
    if (not stat.S_ISREG(key_info.st_mode) or key_info.st_uid != owner
            or stat.S_IMODE(key_info.st_mode) != 0o600 or key_info.st_nlink != 1):
        raise ValueError('invalid_key')
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))+'\n').encode()
    if len(raw) > 32768:
        raise ValueError('invalid_release')
    signed = subprocess.run(['openssl', 'dgst', '-sha256', '-sign', str(key)], input=raw,
                            capture_output=True, timeout=15)
    if signed.returncode or len(signed.stdout) != 384:
        raise ValueError('invalid_key')
    files.update({'manifest.json': raw, 'manifest.sig': base64.b64encode(signed.stdout)+b'\n'})
    info = directory(output, owner, create=True)
    group = info.st_gid
    directory(output/'releases', owner, create=True, group=group)
    fd = os.open(output/'publish.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o640)
    with os.fdopen(fd, 'r+b') as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('busy') from None
        read_regular(output/'publish.lock', 0, owner)
        for item in output.iterdir():
            if re.fullmatch(r'\.stage-[a-f0-9]{24}', item.name):
                _remove_owned_directory(item, owner)
            elif re.fullmatch(r'\.pointer-[a-f0-9]{24}', item.name):
                read_regular(item, 1024, owner);item.unlink()
        used = _inventory(output, owner)
        version = value['package_version'];release = output/'releases'/version
        result = {'version': version, 'revision': hashlib.sha256(raw).hexdigest()}
        if release.exists():
            if all(read_regular(release/name, MAX_PACKAGE, owner) == data for name, data in files.items()):
                return result
            raise ValueError('release_exists')
        if (output/'current.json').exists():
            current = current_version(output, owner)
            if int(current.rsplit('+b', 1)[1]) >= value['build']:
                raise ValueError('old_release')
        incoming = sum(map(len, files.values()))+1024
        space = os.statvfs(output)
        if used+incoming > quota_bytes or space.f_bavail*space.f_frsize < incoming+10485760:
            raise ValueError('insufficient_space')
        stage = output/('.stage-'+secrets.token_hex(12))
        directory(stage, owner, create=True, group=group)
        try:
            for name, content in files.items():
                _write(stage/name, content, group)
            os.rename(stage, release)
            pointer = output/('.pointer-'+secrets.token_hex(12))
            _write(pointer, json.dumps({'version': version}).encode(), group)
            os.replace(pointer, output/'current.json')
        finally:
            if stage.exists():
                _remove_owned_directory(stage, owner)
        versions = sorted((p for p in (output/'releases').iterdir() if VERSION_RE.fullmatch(p.name)),
                          key=lambda p: int(p.name.rsplit('+b', 1)[1]), reverse=True)
        for obsolete in versions[2:]:
            _remove_owned_directory(obsolete, owner)
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--release-dir', required=True, type=Path)
    parser.add_argument('--key-file', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(publish_release(args.release_dir, args.key_file, args.output)))
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        code = str(error) if isinstance(error, ValueError) and str(error) in ['invalid_release', 'invalid_key', 'invalid_state', 'insufficient_space', 'busy', 'old_release', 'release_exists'] else 'publish_failed'
        parser.exit(1, code+'\n')

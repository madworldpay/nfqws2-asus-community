"""Small filesystem/format boundary shared by the read-only feed and publisher."""
import json
import os
from pathlib import Path
import re
import stat

VERSION = r'(?:0|[1-9][0-9]{0,5})\.(?:0|[1-9][0-9]{0,5})\.(?:0|[1-9][0-9]{0,5})-asus[1-9][0-9]{0,5}\+b[1-9][0-9]{0,9}'
VERSION_RE = re.compile(VERSION + r'\Z')
PACKAGE_RE = re.compile(r'nfqws2-asus_(' + VERSION + r')_(aarch64-3\.10|armv7)\.ipk\Z')
MAX_PACKAGE = 32 * 1024 * 1024
QUOTA = 100 * 1024 * 1024


def read_regular(path, maximum, owner):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in path.parents):
        raise ValueError('invalid_state')
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    except OSError:
        raise ValueError('invalid_state') from None
    with os.fdopen(fd, 'rb') as source:
        info = os.fstat(source.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != owner or info.st_nlink != 1
                or info.st_mode & 0o022 or info.st_size > maximum):
            raise ValueError('invalid_state')
        raw = source.read(maximum + 1)
        if len(raw) > maximum:
            raise ValueError('invalid_state')
        return raw


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('invalid_state')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('invalid_state')))


def directory(path, owner, create=False, group=None):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in [path, *path.parents]):
        raise ValueError('invalid_state')
    if create and not path.exists():
        path.mkdir(mode=0o750)
        if group is not None:
            os.chown(path, -1, group)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != owner or info.st_mode & 0o022:
        raise ValueError('invalid_state')
    return info


def current_version(root, owner):
    value = decode(read_regular(Path(root)/'current.json', 1024, owner))
    if not isinstance(value, dict) or set(value) != {'version'} or not isinstance(value['version'], str) or not VERSION_RE.fullmatch(value['version']):
        raise ValueError('invalid_state')
    return value['version']

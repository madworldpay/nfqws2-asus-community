"""Only the operator's fixed systemd credential can supply mail settings."""

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import stat


@dataclass(frozen=True)
class RelayConfig:
    username: str = field(repr=False)
    password: str = field(repr=False)
    sender: str = field(repr=False)
    recipient: str = field(repr=False)
    hmac_key: bytes = field(repr=False)
    port: int = 465
    source_limit: int = 3
    global_limit: int = 20


def load_credentials(directory):
    try:
        path = Path(directory) / 'relay-config'
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            meta = os.fstat(stream.fileno())
            # systemd 255 may expose root:root credentials as 0440 with a
            # per-service-user ACL. Permit root or service primary group only;
            # foreign groups, write bits and all world access remain forbidden.
            systemd_read = (stat.S_IMODE(meta.st_mode) == 0o440
                            and meta.st_uid == 0
                            and meta.st_gid in (0, os.getegid()))
            if not stat.S_ISREG(meta.st_mode) or (meta.st_mode & 0o077 and not systemd_read):
                raise ValueError()
            raw = stream.read(8193)
        if len(raw) > 8192:
            raise ValueError()
        def pairs(items):
            out = {}
            for key, value in items:
                if key in out: raise ValueError()
                out[key] = value
            return out
        value = json.loads(raw, object_pairs_hook=pairs)
        required = {'username','password','sender','recipient','hmac_key'}
        if not isinstance(value, dict) or not required <= value.keys() or value.keys() - required - {'port','source_limit','global_limit'}:
            raise ValueError()
        address = r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]{0,250}[A-Za-z0-9])?"
        for key in ['username','sender','recipient']:
            if not isinstance(value[key], str) or len(value[key]) > 254 or not re.fullmatch(address, value[key]): raise ValueError()
        if value['sender'] != value['username']: raise ValueError()
        password = value['password']
        if not isinstance(password, str) or not re.fullmatch('[a-zA-Z0-9]{16}', password): raise ValueError()
        if not isinstance(value['hmac_key'], str) or not re.fullmatch('[a-f0-9]{64}', value['hmac_key']): raise ValueError()
        for key, default, maximum in [('port',465,65535),('source_limit',3,100),('global_limit',20,1000)]:
            value.setdefault(key, default)
            if type(value[key]) is not int or not 1 <= value[key] <= maximum: raise ValueError()
        if value['port'] not in (465,587): raise ValueError()
        value['hmac_key'] = bytes.fromhex(value['hmac_key'])
        return RelayConfig(**value)
    except (OSError, ValueError, TypeError):
        raise ValueError('invalid_config') from None

#!/usr/bin/env python3
"""Prepare the signed ASUS update channel and its public version badge."""

import argparse
import base64
import json
from pathlib import Path
import re
import subprocess
import tempfile


def publish(repo: Path, envelope: bytes) -> int:
    feed = json.loads(envelope)
    if set(feed) != {'manifest', 'signature'}:
        raise ValueError('Invalid update envelope')
    raw = base64.b64decode(feed['manifest'], validate=True)
    signature = base64.b64decode(feed['signature'], validate=True)
    if len(raw) > 32768 or len(signature) != 384:
        raise ValueError('Invalid update envelope')
    key = repo / 'source/project/updates/trusted-release-key.pem'
    with tempfile.NamedTemporaryFile() as proof:
        proof.write(signature)
        proof.flush()
        subprocess.run(['openssl', 'dgst', '-sha256', '-verify', str(key), '-signature', proof.name],
                       input=raw, check=True, capture_output=True, timeout=15)

    manifest = json.loads(raw)
    build = manifest['build']
    version = manifest['package_version']
    if (type(build) is not int or not 1 <= build <= 2147483647
            or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+-asus[0-9]+\+b' + str(build), version)
            or len(manifest['packages']) != 2
            or {p['family'] for p in manifest['packages']} != {'armv7', 'aarch64-3.10'}):
        raise ValueError('The ASUS channel must cover ARMv7 and ARM64')

    channel = repo / 'updates/v2'
    (channel / 'public.json').write_bytes(envelope)
    (channel / 'asus-build.json').write_text(json.dumps({'build': build}) + '\n', encoding='utf-8')
    return build


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('signed_envelope', type=Path)
    parser.add_argument('--repo-root', type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args()
    print(publish(args.repo_root, args.signed_envelope.read_bytes()))

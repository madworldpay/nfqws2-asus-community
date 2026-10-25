"""Read native OpenWrt metadata as data and select a compatible engine family.

Brand and model are informational. Package architecture is authoritative; uname
alone cannot distinguish ABI, endianness or the minimum instruction set.
"""
import json
from pathlib import Path
import re
import shlex

ENGINES = json.loads(Path(__file__).with_name('architectures.json').read_text())


def parse_release(text: str) -> dict:
    if not isinstance(text, str) or len(text) > 16384 or '\0' in text:
        raise ValueError('invalid_release_metadata')
    result = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        match = re.fullmatch(r'(DISTRIB_[A-Z0-9_]+)=(.*)', line)
        if not match or match[1] in result:
            raise ValueError('invalid_release_metadata')
        try:
            words = shlex.split(match[2], comments=True)
        except ValueError as error:
            raise ValueError('invalid_release_metadata') from error
        if len(words) != 1 or any(c in words[0] for c in '$`\r\n'):
            raise ValueError('invalid_release_metadata')
        result[match[1]] = words[0]
    return result


def engine_for_arch(arch: str) -> str:
    if not isinstance(arch, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_+-]{0,99}', arch):
        raise ValueError('invalid_package_architecture')
    if arch in ('all', 'noarch') or re.search(r'-(?:2\.6|3\.2|3\.10)$', arch):
        raise ValueError('native_architecture_required')
    if re.fullmatch(r'aarch64(?:_[a-z0-9_-]+)?', arch):
        return 'arm64'
    if re.fullmatch(r'arm_(?:cortex-a[0-9]+|arm1176jzf-s)(?:_[a-z0-9_-]+)?', arch):
        return 'arm'
    if re.fullmatch(r'mips(?:el)?_(?:4kec|24kc|24kec|74kc|1004kc)(?:_[a-z0-9_-]+)?', arch):
        return 'mipsel' if arch.startswith('mipsel_') else 'mips'
    if re.fullmatch(r'mips64_octeon(?:plus)?', arch):
        return 'mips64'
    if re.fullmatch(r'x86_64(?:_[a-z0-9_-]+)?', arch):
        return 'x86_64'
    if re.fullmatch(r'i386_(?:pentium(?:[234]|-mmx|-m)?|geode|i586|i686)', arch) or arch in ('i586', 'i686'):
        return 'x86'
    raise ValueError('engine_unavailable: '+arch)


def resolve_platform(release: dict, board: dict, package_manager: str,
                     architectures: list[str]) -> dict:
    if package_manager not in ('opkg', 'apk'):
        raise ValueError('native_package_manager_required')
    keys = ('DISTRIB_ID', 'DISTRIB_RELEASE', 'DISTRIB_TARGET', 'DISTRIB_ARCH')
    if not isinstance(release, dict) or any(not isinstance(release.get(k), str) or
                                           not release[k] for k in keys):
        raise ValueError('invalid_release_metadata')
    version, target, arch = (release[k] for k in keys[1:])
    if not re.fullmatch(r'[a-z0-9_-]+/[a-z0-9_-]+', target):
        raise ValueError('invalid_release_metadata')
    if version == 'SNAPSHOT':
        series = 'SNAPSHOT'
    else:
        match = re.fullmatch(r'(\d{2}\.\d{2})(?:\.\d+)?(?:[-+][A-Za-z0-9_.-]+)?', version)
        if not match:
            raise ValueError('invalid_release_metadata')
        series = match[1]
    if not isinstance(architectures, list) or arch not in architectures:
        raise ValueError('package_architecture_mismatch')
    if not isinstance(board, dict) or not isinstance(board.get('release', {}), dict):
        raise ValueError('invalid_board_metadata')
    reported = board.get('release', {})
    for field, expected in [('target', target), ('version', version)]:
        if reported.get(field) not in (None, expected):
            raise ValueError('platform_metadata_conflict')
    engine = engine_for_arch(arch)
    return dict(platform='openwrt', distribution=release['DISTRIB_ID'], version=version,
                series=series, target=target, arch=arch, engine=engine,
                format='ipk' if package_manager == 'opkg' else 'apk',
                package_manager=package_manager, elf=ENGINES[engine].copy())


def validate_engine(data: bytes, target: dict) -> None:
    expected = target['elf']
    if (len(data) < 64 or data[:4] != b'\x7fELF' or data[6] != 1 or
            data[4] != expected['class'] or data[5] != expected['endian']):
        raise ValueError('engine_elf_mismatch')
    endian = 'little' if data[5] == 1 else 'big'
    if (int.from_bytes(data[16:18], endian) not in (2, 3) or
            int.from_bytes(data[18:20], endian) != expected['machine'] or
            int.from_bytes(data[20:24], endian) != 1):
        raise ValueError('engine_elf_mismatch')

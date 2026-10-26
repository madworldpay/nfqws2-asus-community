"""Native OpenWrt identity, CPU compatibility and package format boundaries."""
import importlib.util
from pathlib import Path
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('native_openwrt', ROOT/'openwrt/platform.py')
platform = importlib.util.module_from_spec(spec)
spec.loader.exec_module(platform)


class OpenWrtPlatformTests(unittest.TestCase):
    def resolve(self, arch='arm_cortex-a9', version='24.10.8', manager='opkg',
                target='bcm53xx/generic', model='Asus RT-AC87U', **changes):
        release = dict(DISTRIB_ID='OpenWrt', DISTRIB_RELEASE=version,
                       DISTRIB_TARGET=target, DISTRIB_ARCH=arch)
        release.update(changes)
        board = dict(model=model, release=dict(target=target, version=version))
        return platform.resolve_platform(release, board, manager, ['all', 'noarch', arch])

    def test_actual_ac87u_uses_native_architecture_and_ipk(self):
        r = self.resolve()
        self.assertEqual((r['platform'], r['series'], r['format'], r['arch'], r['engine']),
                         ('openwrt', '24.10', 'ipk', 'arm_cortex-a9', 'arm'))

    def test_new_release_uses_apk_and_preserves_target(self):
        r = self.resolve('aarch64_cortex-a53', '25.12.6', 'apk', 'mediatek/filogic')
        self.assertEqual((r['format'], r['target'], r['engine']),
                         ('apk', 'mediatek/filogic', 'arm64'))

    def test_cpu_families_and_brands_share_the_same_contract(self):
        for arch, engine in [('arm_cortex-a7_neon-vfpv4', 'arm'),
                             ('arm_cortex-a15_neon-vfpv4', 'arm'),
                             ('aarch64_cortex-a72', 'arm64'),
                             ('mipsel_24kc', 'mipsel'), ('mipsel_74kc', 'mipsel'),
                             ('mips_24kc', 'mips'), ('mips64_octeonplus', 'mips64'),
                             ('i386_pentium4', 'x86'), ('x86_64', 'x86_64')]:
            with self.subTest(arch=arch):
                r = self.resolve(arch, model='Other manufacturer / custom board')
                self.assertEqual(r['engine'], engine)
                self.assertNotIn('asus', r['platform'])

    def test_missing_binary_is_distinct_from_an_unsupported_brand(self):
        for arch in ['riscv64_riscv64', 'arm_arm926ej-s', 'arm_arm1176jzf-s', 'mips_mips32r6', 'i386_i486']:
            with self.subTest(arch=arch), self.assertRaisesRegex(ValueError, 'engine_unavailable'):
                self.resolve(arch)

    def test_entware_abi_and_ambiguous_manager_cannot_be_selected(self):
        for arch in ['armv7-3.2', 'aarch64-3.10', 'all']:
            with self.subTest(arch=arch), self.assertRaises(ValueError):
                self.resolve(arch)
        for manager in ['opkg apk', '/opt/bin/opkg', '', 'apt']:
            with self.subTest(manager=manager), self.assertRaisesRegex(ValueError, 'package_manager'):
                self.resolve(manager=manager)

    def test_release_and_installed_architecture_must_agree(self):
        release = dict(DISTRIB_ID='OpenWrt', DISTRIB_RELEASE='24.10.8',
                       DISTRIB_TARGET='bcm53xx/generic', DISTRIB_ARCH='arm_cortex-a9')
        with self.assertRaisesRegex(ValueError, 'architecture_mismatch'):
            platform.resolve_platform(release, {}, 'opkg', ['all', 'mipsel_24kc'])
        with self.assertRaisesRegex(ValueError, 'metadata_conflict'):
            platform.resolve_platform(release, {'release': {'target': 'ramips/mt7621'}},
                                      'opkg', ['arm_cortex-a9'])

    def test_snapshot_and_derivative_are_not_brand_blacklisted(self):
        r = self.resolve(version='SNAPSHOT', manager='apk', DISTRIB_ID='ImmortalWrt')
        self.assertEqual((r['distribution'], r['series'], r['format']),
                         ('ImmortalWrt', 'SNAPSHOT', 'apk'))

    def test_metadata_is_parsed_as_data_never_shell(self):
        text = "DISTRIB_ID='OpenWrt'\nDISTRIB_RELEASE='24.10.8'\nDISTRIB_TARGET='bcm53xx/generic'\nDISTRIB_ARCH='arm_cortex-a9'\n"
        self.assertEqual(platform.parse_release(text)['DISTRIB_ARCH'], 'arm_cortex-a9')
        for bad in [text+"DISTRIB_ARCH='mips_24kc'\n",
                    text.replace("'arm_cortex-a9'", "'arm_cortex-a9'; reboot"),
                    text.replace("'arm_cortex-a9'", '$(id)')]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                platform.parse_release(bad)

    @staticmethod
    def elf(cls, endian, machine):
        data = bytearray(64)
        data[:7] = b'\x7fELF'+bytes([cls, endian, 1])
        fmt = '<' if endian == 1 else '>'
        struct.pack_into(fmt+'HHI', data, 16, 2, machine, 1)
        return bytes(data)

    def test_elf_checks_endian_class_and_machine_for_each_family(self):
        cases = [('arm_cortex-a9', 1, 1, 40), ('aarch64_cortex-a53', 2, 1, 183),
                 ('mipsel_24kc', 1, 1, 8), ('mips_24kc', 1, 2, 8),
                 ('mips64_octeonplus', 2, 2, 8), ('i386_pentium4', 1, 1, 3),
                 ('x86_64', 2, 1, 62)]
        for arch, cls, endian, machine in cases:
            target = self.resolve(arch)
            with self.subTest(arch=arch):
                platform.validate_engine(self.elf(cls, endian, machine), target)
                for wrong in [b'not ELF', self.elf(3-cls, endian, machine),
                              self.elf(cls, 3-endian, machine), self.elf(cls, endian, 999)]:
                    with self.assertRaisesRegex(ValueError, 'engine_elf_mismatch'):
                        platform.validate_engine(wrong, target)

    def test_native_engine_cannot_require_a_foreign_dynamic_loader(self):
        data=bytearray(self.elf(1,1,40))+bytearray(32)
        struct.pack_into('<I',data,28,64)
        struct.pack_into('<HH',data,42,32,1)
        struct.pack_into('<I',data,64,3)  # PT_INTERP
        with self.assertRaisesRegex(ValueError,'engine_dynamic_loader'):
            platform.validate_engine(bytes(data),self.resolve())


if __name__ == '__main__':
    unittest.main()

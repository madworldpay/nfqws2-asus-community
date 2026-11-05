"""Offline package helpers must match both reviewed source and static ABI."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


class DpiTerminalBuildTests(unittest.TestCase):
    def module(self):
        path=ROOT/'asus/dpi/terminal_build.py'
        self.assertTrue(path.is_file(),'offline packages need a verified terminal helper recipe')
        spec=importlib.util.spec_from_file_location('dpi_terminal_build',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module

    def test_every_package_family_gets_a_static_helper_with_its_own_abi(self):
        module=self.module()
        for family,identity in [('arm',(1,1,40)),('arm64',(2,1,183)),('mips',(1,2,8)),
                                ('mipsel',(1,1,8)),('mips64',(2,2,8)),('x86',(1,1,3)),('x86_64',(2,1,62))]:
            with self.subTest(family=family):
                raw=module.payload_for(family)
                self.assertEqual(raw[:4],b'\x7fELF')
                self.assertEqual((raw[4],raw[5],int.from_bytes(raw[18:20],'little' if raw[5]==1 else 'big')),identity)
        self.assertEqual(module.payload_for('armv7-2.6'),module.payload_for('arm'))
        self.assertEqual(module.payload_for('armv7-3.2'),module.payload_for('arm'))
        self.assertEqual(module.payload_for('aarch64-3.10'),module.payload_for('arm64'))

    def test_changed_source_and_tampered_helper_are_rejected_offline(self):
        import shutil
        module=self.module()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);shutil.copytree(ROOT/'asus/dpi/bin',root/'bin');shutil.copyfile(ROOT/'asus/dpi/terminal.c',root/'terminal.c')
            before=module.payload_for('arm64',directory=root)
            (root/'terminal.c').write_bytes(b'changed source')
            with self.assertRaisesRegex(RuntimeError,'source'):module.payload_for('arm64',directory=root)
            shutil.copyfile(ROOT/'asus/dpi/terminal.c',root/'terminal.c')
            (root/'bin/dpi-terminal-arm64').write_bytes(before[:-1]+bytes([before[-1]^1]))
            with self.assertRaisesRegex(RuntimeError,'SHA256'):module.payload_for('arm64',directory=root)
        with self.assertRaisesRegex(ValueError,'family'):module.payload_for('../../bin/sh')

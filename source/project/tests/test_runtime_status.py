"""Read the real status route against local module/proc fixtures only."""
import os
import unittest
from unittest.mock import patch
import test_auth_api as auth
PHP = auth.PHP

@unittest.skipUnless(PHP, 'optional PHP CLI interpreter not supplied')
class RuntimeStatusTests(unittest.TestCase):
    def setUp(self):
        self.fixture = auth.PasswordApiTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.base = self.fixture.base
        self.module = self.base/'sys/module/ark'
        self.module.parent.mkdir(parents=True)
        self.modules = self.base/'modules'
        bindir = self.base/'bin'; bindir.mkdir()
        opkg = bindir/'opkg'
        opkg.write_text('#!/bin/sh\necho "Version: 1.3.1-asus6+b65"\n')
        opkg.chmod(0o755)
        init = self.base/'opt/etc/init.d/S51nfqws2'
        init.parent.mkdir(parents=True)
        init.write_text('#!/bin/sh\necho "nfqws2 is running"\n')
        init.chmod(0o755)
        index = self.base/'index.php'
        source = index.read_text().replace("define('ROOT_DIR', '/opt');", "define('ROOT_DIR', '"+str(self.base/'opt')+"');")
        source = source.replace('/sys/module',str(self.module.parent)).replace('/proc/modules',str(self.modules))
        index.write_text(source)
        env = patch.dict(os.environ, {'PATH':str(bindir)+':'+os.environ.get('PATH','')})
        env.start(); self.addCleanup(env.stop)
        self.fixture.login()

    def status(self):
        code, value = self.fixture.request({'cmd':'status'})
        self.assertEqual(code,200)
        self.assertIs(value['service'],True,'process remains separate from ARK readiness')
        self.assertIn('ark_loaded',value)
        return value['ark_loaded']

    def test_status_uses_exact_module_name_and_preserves_nullable_unknown(self):
        for raw, want in [('nf_ark 4096 0 - Live 0x0\n',False),('ark 4096 0 - Live 0x0\n',True),('',False)]:
            with self.subTest(raw=raw):
                self.modules.write_text(raw)
                self.assertIs(self.status(),want)
        self.modules.unlink()
        self.assertIsNone(self.status())
        self.modules.write_text('')
        self.module.parent.rmdir()
        self.assertIsNone(self.status(),'Unreadable/missing sysfs cannot confirm an unloaded module')

    def test_sys_module_is_authoritative_even_when_proc_is_missing_or_oversized(self):
        self.module.mkdir(parents=True)
        self.assertIs(self.status(),True)
        self.modules.write_text('x'*262145)
        self.assertIs(self.status(),True)
        self.module.rmdir()
        self.assertIsNone(self.status())

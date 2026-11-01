"""Optional module cannot reach updater rollback/force modes."""
import subprocess
import os
import shlex
import test_package_update_opkg_lock as guard_fixtures
SOURCE=guard_fixtures.SOURCE

class SocketsOpkgLockTests(guard_fixtures.PackageUpdateOpkgLockTests):
    def setUp(self):
        super().setUp()
        args=[os.environ.get('UPDATE_TEST_CC','gcc'),*shlex.split(os.environ.get('UPDATE_TEST_CFLAGS','')),'-Os','-nostdlib','-static','-fno-builtin','-fno-stack-protector','-fno-pie','-no-pie','-DSOCKETS_ONLY=1',
              '-DUPDATE_ROOT="'+str(self.state)+'"','-DOPKG_LOCK="'+str(self.lock)+'"','-DOPKG_BIN="'+str(self.opkg)+'"',
              '-DUPDATE_OWNER='+str(os.getuid()),str(SOURCE),'-o',str(self.binary)]
        r=subprocess.run(args,capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
    def test_explicit_resume_executes_only_own_configure_under_same_mutex(self):
        result=subprocess.run(self.argv()+['configure'],capture_output=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(self.log.read_text(),'preflightopkg:configure php8-mod-sockets')
    def test_rollback_is_confined_to_the_sealed_old_package_under_the_native_mutex(self):
        for action in ['rollback','rollback-verify','--force-reinstall']:
            with self.subTest(action=action):
                result=subprocess.run(self.argv()+[action],capture_output=True,timeout=5)
                self.assertEqual(result.returncode,75);self.assertFalse(self.log.exists())
    def test_verify_only_holds_same_native_mutex_and_never_executes_opkg(self):
        result=subprocess.run(self.argv()+['rollback-verify'],capture_output=True,timeout=5)
        self.assertEqual(result.returncode,75);self.assertFalse(self.log.exists())

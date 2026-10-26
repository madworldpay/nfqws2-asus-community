"""Bootstrap execution uses native transactions only after rechecking signed state."""
import os,shlex,subprocess,unittest,uuid
from pathlib import Path
from test_openwrt_install_prepare import NativeInstallPreparation,ROOT
class NativeInstallExecution(NativeInstallPreparation):
 def test_direct_install_executes_native_manager_once_and_detects_installed_version(self):
  # Reuse the signed inert package preparation, then execute it using the real
  # native manager. Its hook is a marker, not our application's service hooks.
  self.assertTrue((ROOT/'openwrt/install-execute.php').is_file(),'Native bootstrap needs verified native execution after preparation')
  self.run_case(False,execute=True)
 def test_complete_command_checks_then_installs_without_source_checkout(self):
  self.run_case(False,execute='shell')
 def test_preparation_changed_after_signature_check_is_rejected(self):
  self.assertTrue((ROOT/'openwrt/install-execute.php').is_file(),'Native execution must revalidate sealed metadata and archive')
  self.run_case(False,execute='tamper')
if __name__=='__main__':unittest.main()

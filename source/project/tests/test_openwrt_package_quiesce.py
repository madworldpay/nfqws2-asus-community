"""The fixed native controller holds EX while nested DNS restoration is authorized."""
import unittest
import test_openwrt_manual_context as fixtures
class NativePackageQuiesce(fixtures.ManualNativeContext):
 test_exact_controller_restores_dns_while_ordinary_mutations_stay_blocked=None
 test_manual_recovery_can_ignore_a_dead_ui_ticket_without_sh_lease_deadlock=None
 test_unprotected_manager_journal_cannot_authorize_controller=None
 test_stale_manager_journal_cannot_authorize_even_the_fixed_controller=None
 test_writable_controller_parent_cannot_grant_the_exception=None
 def test_real_controller_keeps_ordinary_mutations_blocked_during_dns_restore(self):
  self.assertTrue((fixtures.ROOT/'openwrt/update/quiesce.php').exists(),'fixed root native controller missing')
  self.assertEqual(self.run_case('ok',production=True),{'authorized':True,'ordinary_blocked':True})
 def test_wrapper_refuses_writable_parent_before_executing_controller(self):
  self.assertEqual(self.run_case('unsafe-wrapper',production=True),{'refused':True,'entry_started':False})
 def test_active_ordinary_mutation_blocks_controller_before_any_stop(self):
  self.assertTrue((fixtures.ROOT/'openwrt/update/quiesce.php').exists(),'fixed root native controller missing')
  self.assertEqual(self.run_case('busy',production=True),{'busy':True})
if __name__=='__main__':unittest.main()

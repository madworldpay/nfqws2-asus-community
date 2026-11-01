"""Periodic core restarts use real shell timing and PHP storage/HTTP fixtures."""
import fcntl
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

import test_auth_api as auth

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT/'webui/web/public'
PHP = auth.PHP


class RestartTimerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.config = self.base/'restart-schedule.conf'
        self.state = self.base/'timer'
        self.uptime = self.base/'uptime'; self.uptime.write_text('100.00 0.00\n')
        self.proc = self.base/'proc'; (self.proc/'41').mkdir(parents=True)
        # /proc/PID/stat starttime is field 22, with a parenthesized comm.
        (self.proc/'41/stat').write_text('41 (nfqws2 worker) S '+'0 '*18+'500 0\n')
        self.config.write_text('enabled=1\ninterval_hours=4\nwatchdog_enabled=0\nrevision='+'a'*32+'\nwatchdog_revision='+'c'*32+'\n')
        self.config.chmod(0o600)
        source=ROOT/'asus/restart-schedule.sh';self.lib=self.base/'restart-schedule.sh'
        if source.exists():self.lib.write_text(source.read_text().replace("awk '{print $5}')\" = 0 ]", "awk '{print $5}')\" = "+str(os.getuid())+" ]").replace('-v owner=0','-v owner='+str(os.getuid())))

    def due(self):
        self.assertTrue(self.lib.is_file(), 'restart timer runtime is missing')
        script = '. '+shlex.quote(str(self.lib))+'\nnfqws_restart_schedule_due 41'
        return subprocess.run(['sh','-c',script],capture_output=True,text=True,env={**os.environ,
            'NFQWS_RESTART_CONFIG':str(self.config),'NFQWS_RESTART_STATE':str(self.state),
            'NFQWS_RESTART_UPTIME':str(self.uptime),'NFQWS_RESTART_PROC':str(self.proc)})

    def test_due_uses_elapsed_uptime_and_never_restarts_at_first_tick(self):
        self.assertEqual(self.due().returncode,1)
        self.uptime.write_text('14499.90 0\n'); self.assertEqual(self.due().returncode,1)
        self.uptime.write_text('14500.00 0\n'); self.assertEqual(self.due().returncode,0)
        # An overdue tick stays due until a successful process replacement.
        self.assertEqual(self.due().returncode,0)

    def test_writable_settings_cannot_authorize_a_due_restart(self):
        self.assertEqual(self.due().returncode,1)
        self.uptime.write_text('14500 0\n');self.config.chmod(0o666)
        self.assertNotEqual(self.due().returncode,0)

    def test_new_process_reboot_and_changed_setting_restart_the_countdown(self):
        self.assertEqual(self.due().returncode,1)
        self.uptime.write_text('20000 0\n'); self.assertEqual(self.due().returncode,0)
        (self.proc/'41/stat').write_text('41 (nfqws2) S '+'0 '*18+'600 0\n')
        self.assertEqual(self.due().returncode,1)
        self.uptime.write_text('10 0\n'); self.assertEqual(self.due().returncode,1)
        self.config.write_text('enabled=1\ninterval_hours=12\nwatchdog_enabled=0\nrevision='+'b'*32+'\nwatchdog_revision='+'c'*32+'\n')
        self.uptime.write_text('50000 0\n'); self.assertEqual(self.due().returncode,1)

    def test_disabled_absent_malformed_and_symlink_config_never_become_due(self):
        for raw in ['enabled=0\ninterval_hours=4\nrevision='+'a'*32+'\n',
                    'enabled=1\ninterval_hours=0\nrevision='+'a'*32+'\n',
                    'enabled=1\ninterval_hours=169\nrevision='+'a'*32+'\n',
                    'enabled=1\ninterval_hours=4\nrevision='+'a'*32+'\nextra=1\n',
                    'enabled=1\ninterval_hours=$(touch BAD)\nrevision='+'a'*32+'\n']:
            with self.subTest(raw=raw):
                self.config.write_text(raw); self.assertNotEqual(self.due().returncode,0)
        self.config.unlink(); self.assertNotEqual(self.due().returncode,0)
        other=self.base/'other'; other.write_text('enabled=1\ninterval_hours=1\nrevision='+'a'*32+'\n')
        self.config.symlink_to(other); self.assertNotEqual(self.due().returncode,0)
        self.assertFalse((self.base/'BAD').exists())

    def watchdog(self, mode='due'):
        self.assertTrue(self.lib.is_file())
        return subprocess.run(['sh','-c','. '+shlex.quote(str(self.lib))+'; nfqws_watchdog_'+mode],capture_output=True,text=True,env={**os.environ,
            'NFQWS_RESTART_CONFIG':str(self.config),'RUN_DIR':str(self.base),
            'NFQWS_RESTART_UPTIME':str(self.uptime)})

    def test_watchdog_has_three_increasing_attempt_delays_and_latches_after_failure(self):
        self.config.write_text(self.config.read_text().replace('watchdog_enabled=0','watchdog_enabled=1'))
        self.assertEqual(self.watchdog().returncode,1)
        for now,attempt,next_due in [(160,1,460),(460,2,1360),(1360,3,0)]:
            with self.subTest(attempt=attempt):
                self.uptime.write_text(str(now-1)+' 0\n');self.assertEqual(self.watchdog().returncode,1)
                self.uptime.write_text(str(now)+' 0\n');self.assertEqual(self.watchdog().returncode,0)
                self.assertEqual(self.watchdog('attempt').returncode,0)
                self.assertEqual((self.base/'watchdog-state').read_text().split()[1:3],[str(attempt),str(next_due)])
        self.uptime.write_text('99999 0\n');self.assertEqual(self.watchdog().returncode,1)
        self.assertEqual((self.base/'watchdog-state').read_text().split()[3],'locked')
        # A timer edit cannot clear the watchdog latch.
        self.config.write_text(self.config.read_text().replace('revision='+'a'*32,'revision='+'b'*32))
        self.assertEqual(self.watchdog().returncode,1)
        # A deliberate watchdog toggle uses its own revision and rearms it.
        self.config.write_text(self.config.read_text().replace('watchdog_revision='+'c'*32,'watchdog_revision='+'d'*32))
        self.assertEqual(self.watchdog().returncode,1)
        self.assertEqual((self.base/'watchdog-state').read_text().split()[1],'0')

    def test_successful_recovery_retains_attempt_counter_and_off_never_recovers(self):
        self.assertEqual(self.watchdog().returncode,1)
        self.assertFalse((self.base/'watchdog-state').exists())
        self.config.write_text(self.config.read_text().replace('watchdog_enabled=0','watchdog_enabled=1'))
        self.watchdog();self.uptime.write_text('160 0\n');self.watchdog('attempt')
        self.assertEqual(self.watchdog('running').returncode,0)
        self.assertEqual((self.base/'watchdog-state').read_text().split()[1:4],['1','0','ready'])
        self.assertEqual(self.watchdog().returncode,1)
        self.assertEqual((self.base/'watchdog-state').read_text().split()[2],'460')

    def test_writable_watchdog_state_cannot_unlock_or_authorize_recovery(self):
        self.config.write_text(self.config.read_text().replace('watchdog_enabled=0','watchdog_enabled=1'))
        self.assertEqual(self.watchdog().returncode,1)
        (self.base/'watchdog-state').chmod(0o666);self.uptime.write_text('160 0\n')
        self.assertNotEqual(self.watchdog().returncode,0)


class RestartPlatformTests(RestartTimerTests):
    def native(self, *, running=True, update_busy=False, stopped=False, runtime_path=None, action='scheduledrestart'):
        guard=self.base/'service-lease.sh';guard.write_text('nfqws_native_update_enter() { [ "$UPDATE_BUSY" != 1 ]; }\n')
        control=self.base/'control';control.write_text('''#!/bin/sh
printf '%s\\n' "$1" >> "$CALLS"
if [ "$1" = process-pid ]; then [ "$RUNNING" = 1 ] || exit 1; echo 41; fi
''');control.chmod(0o700)
        init=self.base/'init';init.write_text((ROOT/'openwrt/nfqws2.init').read_text().replace('/usr/lib/nfqws2/update/service-lease.sh',str(guard)).replace('/usr/lib/nfqws2/restart-schedule.sh',str(self.lib)))
        if stopped:
            if (self.base/'started').exists():(self.base/'started').unlink()
        else:(self.base/'started').touch()
        script='''action="$ACTION"; NFQWS_CONTROL="$CONTROL"; NFQWS_RUN="$RUN_DIR"
. "$INIT" || exit $?
restart() { echo core-restart >> "$CALLS"; }
start() { echo core-start >> "$CALLS"; }
if [ "$action" = reload ]; then reload_service; else "$action"; fi
'''
        return subprocess.run(['/bin/sh','-c',script],capture_output=True,text=True,env={**os.environ,
            'PATH':runtime_path or os.environ['PATH'],'ACTION':action,
            'RUNNING':'1'if running else'0','UPDATE_BUSY':'1'if update_busy else'0',
            'RUN_DIR':str(self.base),'CONTROL':str(control),'INIT':str(init),'CALLS':str(self.base/'calls'),
            'NFQWS_RESTART_CONFIG':str(self.config),'NFQWS_RESTART_STATE':str(self.state),
            'NFQWS_RESTART_UPTIME':str(self.uptime),'NFQWS_RESTART_PROC':str(self.proc)})

    def calls(self):
        file=self.base/'calls';return file.read_text().splitlines()if file.exists()else[]

    def test_native_due_tick_restarts_core_and_manual_stop_never_starts_it(self):
        self.assertEqual(self.native().returncode,0)
        self.uptime.write_text('14500 0\n')
        p=self.native(running=False);self.assertEqual(p.returncode,0,p.stderr)
        self.assertNotIn('core-restart',self.calls())
        p=self.native();self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(self.calls()[-3:],['preflight','firewall','core-restart'])

    def test_native_updater_blocks_before_process_check_or_restart(self):
        p=self.native(update_busy=True);self.assertNotEqual(p.returncode,0)
        self.assertEqual(self.calls(),[])

    def test_native_periodic_and_watchdog_work_with_base_applets_without_stat(self):
        binary=self.base/'native-bin';binary.mkdir()
        for applet in ['awk','sed','cat','mv','rm','ls']:(binary/applet).symlink_to('/usr/bin/busybox')
        self.assertEqual(self.native(runtime_path=str(binary)).returncode,0)
        self.uptime.write_text('14500 0\n');p=self.native(runtime_path=str(binary));self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn('core-restart',self.calls())
        (self.base/'calls').unlink();self.config.write_text(self.config.read_text().replace('watchdog_enabled=0','watchdog_enabled=1'))
        self.uptime.write_text('20000 0\n');self.assertEqual(self.native(running=False,runtime_path=str(binary)).returncode,0)
        self.uptime.write_text('20060 0\n');p=self.native(running=False,runtime_path=str(binary));self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn('core-restart',self.calls())

    def test_native_reload_never_recovers_dead_or_manually_stopped_core(self):
        for running,stopped in [(False,False),(False,True),(True,True)]:
            with self.subTest(running=running,stopped=stopped):
                if (self.base/'calls').exists():(self.base/'calls').unlink()
                p=self.native(running=running,stopped=stopped,action='reload');self.assertEqual(p.returncode,0,p.stderr)
                self.assertNotIn('core-start',self.calls());self.assertNotIn('preflight',self.calls());self.assertNotIn('firewall',self.calls())

    def asus_real_start(self, *, watchdog=False, manual_latch=False):
        self.config.write_text(self.config.read_text().replace('watchdog_enabled=0','watchdog_enabled='+('1'if watchdog else'0')))
        strategy=self.base/'strategy';strategy.write_text('STRATEGY=fixture\n')
        engine=self.base/'engine';engine.write_text('#!/bin/sh\necho attempted >> '+shlex.quote(str(self.base/'engine-attempts'))+'\nexit 1\n');engine.chmod(0o700)
        lifecycle=self.base/'real-lifecycle';lifecycle.write_text((ROOT/'asus/lifecycle.sh').read_text().replace('/opt/var/lib/nfqws2-asus/import',str(self.base/'import')).replace("awk '{print $5}')\" = 0 ]", "awk '{print $5}')\" = "+str(os.getuid())+" ]"))
        if manual_latch:
            (self.base/'started').touch();(self.base/'watchdog-state').write_text('c'*32+' 3 0 locked\n');(self.base/'watchdog-state').chmod(0o600)
        script='''umask 077
. "$TIMER"; . "$LIFECYCLE"
asus_running() { return 1; }
asus_check() { :; }; asus_sysctls() { :; }; asus_kill() { :; }
asus_firewall_stop() { :; }; asus_restore_sysctls() { :; }; asus_error() { :; }; cru() { :; }
asus_interfaces() { [ "$WAN_UP" = 1 ] && echo wan0; }; _startup_args() { :; }
asus_start || exit $?
WAN_UP=1
for now in 100 160 460 1360 5000 6000 7000 8000; do
 printf '%s 0\\n' "$now" > "$NFQWS_RESTART_UPTIME"
 asus_reconcile || :
done
'''
        return subprocess.run(['sh','-c',script],capture_output=True,text=True,env={**os.environ,
            'TIMER':str(self.lib),'LIFECYCLE':str(lifecycle),'RUN_DIR':str(self.base),'PIDFILE':str(self.base/'pid'),
            'CONFFILE':str(strategy),'NFQWS_BIN':str(engine),'NFQWS_RESTART_CONFIG':str(self.config),'NFQWS_RESTART_UPTIME':str(self.uptime)})

    def test_asus_first_failed_launch_after_wan_wait_is_not_an_unlimited_retry(self):
        p=self.asus_real_start();self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual((self.base/'engine-attempts').read_text().splitlines(),['attempted'])

    def test_asus_manual_start_rearms_old_latch_while_waiting_for_wan(self):
        p=self.asus_real_start(watchdog=True,manual_latch=True);self.assertEqual(p.returncode,0,p.stderr)
        self.assertTrue((self.base/'engine-attempts').exists(),'manual start must rearm the old latch before returning waiting for WAN')
        self.assertEqual(len((self.base/'engine-attempts').read_text().splitlines()),4,'one authorized first launch and three bounded recoveries')

    def test_native_validated_manual_launch_rearms_old_latch_before_readiness_failure(self):
        state=self.base/'watchdog-state';state.write_text('c'*32+' 3 0 locked\n');state.chmod(0o600)
        (self.base/'started').touch();(self.base/'launch.env').write_text("NFQWS_LAUNCH_ARGS='--qnum=300'\n")
        control=self.base/'manual-control';control.write_text('#!/bin/sh\n[ "$1" != check-started ]\n');control.chmod(0o700)
        guard=self.base/'manual-guard';guard.write_text('nfqws_native_update_enter() { :; }\n')
        init=self.base/'manual-init';init.write_text((ROOT/'openwrt/nfqws2.init').read_text().replace('/usr/lib/nfqws2/update/service-lease.sh',str(guard)))
        body='''action=start; NFQWS_RUN="$RUN_DIR"; NFQWS_CONTROL="$CONTROL"
. "$INIT"
procd_open_instance() { :; }; procd_set_param() { :; }; procd_close_instance() { :; }
stop() { stop_service; }
start_service && service_started
'''
        p=subprocess.run(['/bin/sh','-c',body],capture_output=True,text=True,env={**os.environ,'RUN_DIR':str(self.base),'CONTROL':str(control),'INIT':str(init)})
        self.assertNotEqual(p.returncode,0,'fixture deliberately fails actual queue readiness')
        self.assertFalse(state.exists(),'an explicit validated launch must rearm before an early process failure')
        self.assertTrue((self.base/'started').exists(),'requested running intent is retained for the bounded watchdog')

    def asus(self, *, stopped=False, import_busy=False, running=True, initial=False):
        source=ROOT/'asus/lifecycle.sh';lifecycle=self.base/'lifecycle.sh'
        lifecycle.write_text(source.read_text().replace('/opt/var/lib/nfqws2-asus/import',str(self.base/'import')).replace("awk '{print $5}')\" = 0 ]", "awk '{print $5}')\" = "+str(os.getuid())+" ]"))
        (self.base/'pid').write_text('41\n')
        if stopped:
            if (self.base/'enabled').exists():(self.base/'enabled').unlink()
        else:(self.base/'enabled').touch()
        if not initial:(self.base/'started').touch()
        lockdir=self.base/'import';lockdir.mkdir(mode=0o700,exist_ok=True);lock=lockdir/'writer.lock';lock.touch(mode=0o600)
        script='''. "$TIMER"; . "$LIFECYCLE"
asus_running() { [ "$RUNNING" = 1 ]; }
asus_validate() { return 0; }
asus_firewall_stop() { echo core-firewall-stop >> "$CALLS"; }
asus_kill() { echo core-stop >> "$CALLS"; }
asus_start() { echo core-start >> "$CALLS"; }
asus_interfaces() { echo wan0; }
asus_snapshot() { echo unchanged; }
asus_firewall_apply() { :; }
asus_reconcile
'''
        (self.base/'wan').write_text('wan0\n');(self.base/'snapshot').write_text('unchanged\n')
        with lock.open('r+')as lease:
            if import_busy:fcntl.flock(lease,fcntl.LOCK_EX)
            return subprocess.run(['sh','-c',script],capture_output=True,text=True,env={**os.environ,
                'TIMER':str(self.lib),'LIFECYCLE':str(lifecycle),'RUN_DIR':str(self.base),'PIDFILE':str(self.base/'pid'),
                'RUNNING':'1'if running else'0',
                'CALLS':str(self.base/'calls'),'NFQWS_RESTART_CONFIG':str(self.config),'NFQWS_RESTART_STATE':str(self.state),
                'NFQWS_RESTART_UPTIME':str(self.uptime),'NFQWS_RESTART_PROC':str(self.proc)})

    def test_asus_reconcile_reuses_timer_and_defers_import_or_manual_stop(self):
        p=self.asus();self.assertEqual(p.returncode,0,p.stderr)
        self.uptime.write_text('14500 0\n');self.assertEqual(self.asus(import_busy=True).returncode,0)
        self.assertEqual(self.calls(),[])
        self.assertEqual(self.asus(stopped=True).returncode,0);self.assertEqual(self.calls(),[])
        p=self.asus();self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(self.calls(),['core-firewall-stop','core-stop','core-start'])

    def test_watchdog_off_leaves_unexpected_exit_stopped_on_both_platforms(self):
        for run in [self.asus,self.native]:
            with self.subTest(platform=run.__name__):
                p=run(running=False);self.assertEqual(p.returncode,0,p.stderr)
                self.assertNotIn('core-start',self.calls());self.assertNotIn('core-restart',self.calls())

    def test_asus_initial_wan_wait_still_reconciles_without_watchdog(self):
        p=self.asus(running=False,initial=True);self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(self.calls(),['core-start'])

    def test_watchdog_execution_is_bounded_and_manual_stop_blocks_due_attempt(self):
        self.config.write_text(self.config.read_text().replace('watchdog_enabled=0','watchdog_enabled=1'))
        for run,call in [(self.asus,'core-start'),(self.native,'core-restart')]:
            with self.subTest(platform=run.__name__):
                for name in ['watchdog-state','calls']:
                    if (self.base/name).exists():(self.base/name).unlink()
                self.uptime.write_text('100 0\n');self.assertEqual(run(running=False).returncode,0)
                for now in [160,460,1360,99999]:
                    self.uptime.write_text(str(now)+' 0\n');self.assertEqual(run(running=False).returncode,0)
                self.assertEqual(self.calls().count(call),3)
                self.config.write_text(self.config.read_text().replace('watchdog_revision='+'c'*32,'watchdog_revision='+'d'*32))
                self.assertEqual(run(running=False,stopped=True).returncode,0)
                self.assertEqual(self.calls().count(call),3)
                self.config.write_text(self.config.read_text().replace('watchdog_revision='+'d'*32,'watchdog_revision='+'c'*32))

    def test_explicit_asus_start_rearms_watchdog_even_if_core_is_already_running(self):
        self.config.write_text(self.config.read_text().replace('watchdog_enabled=0','watchdog_enabled=1'))
        state=self.base/'watchdog-state';state.write_text('c'*32+' 3 0 locked\n');state.chmod(0o600)
        script='. '+shlex.quote(str(self.lib))+'; . '+shlex.quote(str(ROOT/'asus/lifecycle.sh'))+'''
asus_running() { return 0; }
asus_start
'''
        p=subprocess.run(['sh','-c',script],capture_output=True,text=True,env={**os.environ,'RUN_DIR':str(self.base),'NFQWS_RESTART_CONFIG':str(self.config)})
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(state.read_text().split()[1:4],['0','0','ready'])


@unittest.skipUnless(PHP, 'PHP CLI fixture required')
class RestartScheduleStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name); self.base.chmod(0o700)

    def call(self, post, *, supported=True):
        source=PUBLIC/'restart-schedule.php'
        self.assertTrue(source.is_file(),'restart schedule API is missing')
        code='''require $argv[1];$p=json_decode($argv[3],true);try {
          NfqwsRestartSchedule::validate($p);
          $s=new NfqwsRestartSchedule($argv[2],(int)$argv[4],fn()=> $argv[5]==='1');
          echo json_encode($p['cmd']==='restartschedulesave'?$s->save($p['enabled']==='1',(int)$p['interval_hours'],$p['watchdog_enabled']==='1'):$s->read());
        }catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        p=subprocess.run([PHP,'-n','-r',code,str(source),str(self.base),json.dumps(post),str(os.getuid()),'1'if supported else'0'],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr); self.assertEqual(p.stderr,''); return json.loads(p.stdout)

    def post(self, enabled='1', hours='12'):
        return {'cmd':'restartschedulesave','csrf_token':'token','enabled':enabled,'interval_hours':hours,'watchdog_enabled':'0'}

    def test_default_off_and_saved_settings_survive_new_process_without_changing_strategy(self):
        strategy=self.base/'nfqws2.conf'; strategy.write_text('UNCHANGED_STRATEGY\n')
        self.assertEqual(self.call({'cmd':'restartschedule','csrf_token':'t'}),{'enabled':False,'interval_hours':24,'watchdog_enabled':False,'watchdog_state':'disabled','watchdog_attempts':0,'watchdog_next_seconds':None,'scheduler_available':True})
        self.assertEqual(self.call(self.post()),{'enabled':True,'interval_hours':12,'watchdog_enabled':False,'watchdog_state':'disabled','watchdog_attempts':0,'watchdog_next_seconds':None,'scheduler_available':True})
        self.assertEqual(self.call({'cmd':'restartschedule','csrf_token':'t'}),{'enabled':True,'interval_hours':12,'watchdog_enabled':False,'watchdog_state':'disabled','watchdog_attempts':0,'watchdog_next_seconds':None,'scheduler_available':True})
        self.assertEqual(strategy.read_text(),'UNCHANGED_STRATEGY\n')
        self.assertEqual((self.base/'restart-schedule.conf').stat().st_mode&0o777,0o600)

    def test_strict_integer_range_and_closed_request_fields(self):
        for hours in ['0','169','-1','01','1.5','4h',' 4','1e1','',[],12]:
            with self.subTest(hours=hours): self.assertEqual(self.call(self.post(hours=hours)),{'error':'invalid_request'})
        for enabled in ['true','2','',True,[]]:
            self.assertEqual(self.call(self.post(enabled=enabled)),{'error':'invalid_request'})
        p=self.post();p['filename']='anything'; self.assertEqual(self.call(p),{'error':'invalid_request'})
        for hours in ['1','4','12','24','168']:
            self.assertEqual(self.call(self.post(hours=hours))['interval_hours'],int(hours))

    def test_unsupported_scheduler_does_not_claim_enabled_or_destroy_previous_setting(self):
        self.assertEqual(self.call(self.post(),supported=False),{'error':'unsupported_scheduler'})
        self.assertFalse((self.base/'restart-schedule.conf').exists())
        self.assertEqual(self.call(self.post('0'),supported=False),{'enabled':False,'interval_hours':12,'watchdog_enabled':False,'watchdog_state':'disabled','watchdog_attempts':0,'watchdog_next_seconds':None,'scheduler_available':False})

    def test_symlinked_configuration_is_rejected(self):
        other=self.base/'other';other.write_text('private')
        (self.base/'restart-schedule.conf').symlink_to(other)
        self.assertEqual(self.call(self.post()),{'error':'invalid_state'})
        self.assertEqual(other.read_text(),'private')

    def test_native_cron_retains_foreign_jobs_registers_once_for_watchdog_and_refuses_stopped_cron(self):
        cron=self.base/'cron';cron.write_text('#!/bin/sh\n[ -f '+shlex.quote(str(self.base/'cron-running'))+' ]\n');cron.chmod(0o700)
        tables=self.base/'crontabs';tables.mkdir(mode=0o700);table=tables/'root';table.write_text('5 3 * * * /root/backup\n');table.chmod(0o600)
        crontab=self.base/'crontab';crontab.write_text('#!/bin/sh\ncp "$1" '+shlex.quote(str(table))+'\n');crontab.chmod(0o700)
        source=self.base/'native-schedule.php';source.write_text((PUBLIC/'restart-schedule.php').read_text().replace("__DIR__.'/platform.php'",repr(str(PUBLIC/'platform.php'))).replace('NfqwsPlatform::native()','true').replace('/etc/init.d/cron',str(cron)).replace('/usr/bin/crontab',str(crontab)).replace('/etc/crontabs',str(tables)).replace("guardFile($directory,'root')","guardFile($directory,'root',"+str(os.getuid())+")").replace("guardFile($directory,'.nfqws2-restart-'.bin2hex(random_bytes(12)))","guardFile($directory,'.nfqws2-restart-'.bin2hex(random_bytes(12)),"+str(os.getuid())+")").replace("$s['uid']!==0","$s['uid']!=="+str(os.getuid())))
        code='''require $argv[1];try{$s=new NfqwsRestartSchedule($argv[2],(int)$argv[3]);echo json_encode($argv[4]==='read'?$s->read():$s->save(false,12,$argv[4]==='1'));}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        def call(enabled):
            p=subprocess.run([PHP,'-n','-r',code,str(source),str(self.base),str(os.getuid()),'read'if enabled=='read'else('1'if enabled else'0')],capture_output=True,text=True);self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(p.stderr,'');return json.loads(p.stdout)
        self.assertEqual(call(True),{'error':'unsupported_scheduler'});self.assertEqual(table.read_text(),'5 3 * * * /root/backup\n')
        (self.base/'cron-running').touch();self.assertIs(call(True)['watchdog_enabled'],True)
        self.assertIs(call(True)['watchdog_enabled'],True)
        self.assertEqual(table.read_text().count('# nfqws2-periodic-restart'),1)
        self.assertIn('5 3 * * * /root/backup\n',table.read_text())
        (self.base/'cron-running').unlink();saved=call('read');self.assertIs(saved['watchdog_enabled'],True);self.assertIs(saved['scheduler_available'],False)
        self.assertIs(call(False)['watchdog_enabled'],False);self.assertEqual(table.read_text(),'5 3 * * * /root/backup\n')
        (self.base/'cron-running').touch();self.assertIs(call(True)['watchdog_enabled'],True)
        crontab.write_text('#!/bin/sh\nexit 1\n')
        self.assertIs(call(False)['watchdog_enabled'],False,'OFF must persist even when removal of the inert cron entry fails')


@unittest.skipUnless(PHP, 'PHP CLI fixture required')
class RestartScheduleHttpTests(unittest.TestCase):
    def setUp(self):
        self.fixture=auth.PasswordApiTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.base=self.fixture.base
        for path in PUBLIC.glob('*.php'):
            if not (self.base/path.name).exists():shutil.copyfile(path,self.base/path.name)
        self.config=self.base/'config';self.config.mkdir(mode=0o700)
        if (self.base/'restart-schedule.php').exists():
            path=self.base/'restart-schedule.php'
            path.write_text(path.read_text().replace("NfqwsPlatform::settings()['config']",repr(str(self.config))).replace('private int $owner=0','private int $owner='+str(os.getuid())))
        # Keep the real origin validator; only ambient request headers are fixture input.
        index=self.base/'index.php';index.write_text(index.read_text().replace("function main(): void\n{", "function main(): void\n{\n$_SERVER['HTTP_HOST']='router.lan';$_SERVER['HTTP_ORIGIN']=$_POST['origin_fixture']??'http://router.lan';unset($_POST['origin_fixture']);"))

    def test_auth_csrf_origin_and_strict_fields_are_required_before_settings_write(self):
        p={'cmd':'restartschedulesave','csrf_token':'invalid','enabled':'1','interval_hours':'4','watchdog_enabled':'0'}
        self.assertEqual(self.fixture.request(p)[0],401)
        token=self.fixture.login(); self.assertEqual(self.fixture.request(p)[0],403)
        p['csrf_token']=token;p['origin_fixture']='http://evil.test';self.assertEqual(self.fixture.request(p)[0],403)
        p.pop('origin_fixture');p['unexpected']='x';self.assertEqual(self.fixture.request(p)[0],400)
        self.assertFalse((self.config/'restart-schedule.conf').exists())

    def test_read_has_closed_response_and_save_defers_while_updater_owns_mutations(self):
        token=self.fixture.login()
        self.assertEqual(self.fixture.request({'cmd':'restartschedule','csrf_token':token}), (200,{'enabled':False,'interval_hours':24,'watchdog_enabled':False,'watchdog_state':'disabled','watchdog_attempts':0,'watchdog_next_seconds':None,'scheduler_available':False}))
        (self.base/'update-busy').touch()
        self.assertEqual(self.fixture.request({'cmd':'restartschedulesave','csrf_token':token,'enabled':'0','interval_hours':'12','watchdog_enabled':'0'}),(409,{'error':'busy'}))


@unittest.skipUnless(PHP, 'PHP CLI fixture required')
class RestartWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name)
        self.app=self.base/'app';self.app.mkdir(mode=0o700)
        for source in PUBLIC.glob('*.php'):shutil.copyfile(source,self.app/source.name)
        self.config=self.base/'config';self.config.mkdir(mode=0o700)
        (self.config/'restart-schedule.conf').write_text('enabled=1\ninterval_hours=4\nwatchdog_enabled=1\nrevision='+'a'*32+'\nwatchdog_revision='+'b'*32+'\n');(self.config/'restart-schedule.conf').chmod(0o600)
        self.imports=self.base/'import';self.imports.mkdir(mode=0o700);self.lock=self.imports/'writer.lock';self.lock.touch(mode=0o600)
        store=self.app/'import-store.php';store.write_text(store.read_text().replace('private int $owner=0','private int $owner='+str(os.getuid())).replace("AsusDpiStore::optPath('/var/lib/nfqws2-asus/import')",repr(str(self.imports))))
        (self.app/'update-guard.php').write_text('''<?php
class AsusUpdateStore{}
class AsusUpdateGuard{function __construct($s){}function mutationLease(){if(is_file(__DIR__.'/busy'))throw new RuntimeException('busy');$f=fopen(__DIR__.'/apply.lock','c+');flock($f,LOCK_SH);return $f;}}
''')
        service=self.base/'service';service.write_text('#!/bin/sh\necho "$1" >> '+shlex.quote(str(self.base/'calls'))+'\nsleep .4\n');service.chmod(0o700)
        (self.base/'status').write_text('Uid:\t0\t0\t0\t0\n')
        self.worker=self.base/'worker.php';self.worker.write_text((ROOT/'openwrt/restart-schedule-worker.php').read_text().replace('/proc/self/status',str(self.base/'status')).replace('/usr/share/nfqws2-web',str(self.app)).replace('new NfqwsRestartSchedule()', 'new NfqwsRestartSchedule('+repr(str(self.config))+','+str(os.getuid())+')').replace('new AsusImportStore()', 'new AsusImportStore('+repr(str(self.imports))+','+str(os.getuid())+')').replace('/etc/init.d/nfqws2-native',str(service)))

    def run_worker(self):
        p=subprocess.run([PHP,'-n',str(self.worker)],capture_output=True,text=True,timeout=3)
        self.assertEqual(p.stderr,'');return p

    def test_busy_import_update_or_parallel_tick_never_overlap_recovery(self):
        with self.lock.open('r+')as lock:
            fcntl.flock(lock,fcntl.LOCK_EX);self.assertEqual(self.run_worker().returncode,0)
        self.assertFalse((self.base/'calls').exists())
        (self.app/'busy').touch();self.assertEqual(self.run_worker().returncode,0);self.assertFalse((self.base/'calls').exists());(self.app/'busy').unlink()
        p=subprocess.Popen([PHP,'-n',str(self.worker)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            import time
            until=time.monotonic()+2
            while not (self.base/'calls').exists()and time.monotonic()<until:time.sleep(.01)
            self.assertTrue((self.base/'calls').exists())
            self.assertEqual(self.run_worker().returncode,0)
            stdout,stderr=p.communicate(timeout=3);self.assertEqual(p.returncode,0,stdout+stderr)
            self.assertEqual((self.base/'calls').read_text(),'scheduledrestart\n')
        finally:
            if p.poll()is None:p.kill();p.wait()
            p.stdout.close();p.stderr.close()


@unittest.skipUnless(PHP, 'PHP CLI fixture required')
class RestartPreservationTests(unittest.TestCase):
    def test_asus_package_update_treats_watchdog_latch_as_stopped_until_explicit_rearm(self):
        with tempfile.TemporaryDirectory()as td:
            root=Path(td);root.chmod(0o700);config=root/'config';config.mkdir(mode=0o700);run=root/'run';run.mkdir(mode=0o700)
            setting=config/'restart-schedule.conf';setting.write_text('enabled=1\ninterval_hours=4\nwatchdog_enabled=1\nrevision='+'a'*32+'\nwatchdog_revision='+'b'*32+'\n');setting.chmod(0o600)
            (run/'enabled').touch(mode=0o600);(run/'watchdog-state').write_text('b'*32+' 3 0 locked\n');(run/'watchdog-state').chmod(0o600)
            code='''require $argv[1].'/update-lifecycle.php';$l=new AsusUpdateLifecycle(['run'=>$argv[2].'/run','config'=>$argv[2].'/config','owner'=>(int)$argv[3]]);echo json_encode($l->intent());'''
            def intent():
                p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(root),str(os.getuid())],capture_output=True,text=True);self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'');return json.loads(p.stdout)
            for phase in ['locked','ready']:
                (run/'watchdog-state').write_text('b'*32+' 3 0 '+phase+'\n')
                self.assertEqual(intent()['mode'],'stopped','an exhausted process must stay stopped even before the next watchdog tick')
            # Saving a new timer interval retains the independent latch.
            setting.write_text(setting.read_text().replace('interval_hours=4','interval_hours=12'))
            self.assertEqual(intent()['mode'],'stopped')
            # A deliberate watchdog OFF/ON has its own fresh revision.
            setting.write_text(setting.read_text().replace('watchdog_revision='+'b'*32,'watchdog_revision='+'c'*32))
            self.assertEqual(intent()['mode'],'waiting_for_wan')

    def test_both_package_update_snapshots_back_up_schedule_and_reject_its_overwrite(self):
        with tempfile.TemporaryDirectory()as td:
            root=Path(td);config=root/'etc/nfqws2';config.mkdir(parents=True)
            settings=config/'restart-schedule.conf';settings.write_text('saved periodic and watchdog preferences\n');settings.chmod(0o600)
            code='''require $argv[1].'/update-prepare.php';require $argv[1].'/openwrt-update-snapshot.php';$root=$argv[2];$owner=(int)$argv[3];
            AsusUpdateSnapshot::capture($root,$root.'/asus-backup',$owner);
            NfqwsOpenWrtUpdateSnapshot::capture($root.'/native-backup',$root,$owner);
            echo json_encode([AsusUpdateSnapshot::verify($root,$root.'/asus-backup',$owner,true),NfqwsOpenWrtUpdateSnapshot::verify($root.'/native-backup',$root,$owner)]);'''
            p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(root),str(os.getuid())],capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'');self.assertEqual(json.loads(p.stdout),[True,True])
            for platform in ['asus','native']:
                self.assertEqual((root/(platform+'-backup/etc/nfqws2/restart-schedule.conf')).read_bytes(),settings.read_bytes())
            settings.write_text('overwritten')
            verify='''require $argv[1].'/update-prepare.php';require $argv[1].'/openwrt-update-snapshot.php';$r=[];foreach(['asus','native']as $kind){try{if($kind==='asus')AsusUpdateSnapshot::verify($argv[2],$argv[2].'/asus-backup',(int)$argv[3],true);else NfqwsOpenWrtUpdateSnapshot::verify($argv[2].'/native-backup',$argv[2],(int)$argv[3]);$r[]=false;}catch(Throwable $e){$r[]=$e->getMessage();}}echo json_encode($r);'''
            p=subprocess.run([PHP,'-n','-r',verify,str(PUBLIC),str(root),str(os.getuid())],capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(json.loads(p.stdout),['settings_changed','settings_changed'])


if __name__=='__main__': unittest.main()

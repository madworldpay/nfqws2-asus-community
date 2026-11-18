"""Full synthesis/library/artifact/export flow; network and service are fixtures."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import uuid
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
IMAGE='nfqws-openwrt-test:25.12.6-php'


@unittest.skipUnless(os.environ.get('NFQWS_TEST_GUARD_PHP_IMAGE')==IMAGE,
                     'Requires cached isolated root PHP image for synthesis flow')
class CustomSynthesisFlowTests(unittest.TestCase):
    def run_flow(self, platform, pool=None, recover=False, mixed=False, comparison=None, rounds='1', from_scratch=False, limited_storage=False):
        task='picker-synthesis-flow-'+uuid.uuid4().hex
        cid=None
        evidence={'task':task,'platform':platform,'pool':pool,'recover':recover,'mixed':mixed,'comparison':comparison,'from_scratch':from_scratch}
        engine=Path(os.environ['NFQWS_TEST_ENGINE_DIR'])/'lua'
        self.assertTrue(all((engine/name).is_file()for name in ['zapret-lib.lua','zapret-antidpi.lua']))
        with tempfile.TemporaryDirectory()as directory:
            web=Path(directory)/'web'
            shutil.copytree(ROOT/'webui/web/public',web)
            for source in (ROOT/'experimental/device-profiles').glob('device-profiles-*.php'):
                self.assertFalse((web/source.name).exists())
                shutil.copyfile(source,web/source.name)
            for path in web.rglob('*'):
                self.assertFalse(path.is_symlink())
                path.chmod(0o755 if path.is_dir()else 0o644)
            web.chmod(0o755)
            fixtures=ROOT/'tests/fixtures'
            mounts=['--mount',f'type=bind,src={web},dst=/fixture-web,readonly',
                    '--mount',f'type=bind,src={ROOT/"openwrt/config.php"},dst=/fixtures/config.php,readonly',
                    '--mount',f'type=bind,src={ROOT/"support"},dst=/fixture-support,readonly',
                    '--mount',f'type=bind,src={engine},dst=/fixture-lua,readonly']
            for name in ['master','worker','leaf','read','applied']:
                mounts+=['--mount',f'type=bind,src={fixtures/"picker-synthesis-"}{name}.php,dst=/fixtures/{name}.php,readonly']
            tmpfs=[]
            state_size='4m' if limited_storage else '96m'
            for path,size in [('/tmp','16m'),('/opt','32m'),('/etc/nfqws2','8m'),('/etc/nfqws2-web',state_size),
                              ('/etc/init.d','1m'),('/usr/share/nfqws2-web','32m'),('/usr/share/nfqws2','1m'),('/usr/lib/nfqws2','2m')]:
                tmpfs+=['--tmpfs',f'{path}:rw,exec,nosuid,nodev,mode=0755,size={size}']
            if platform=='asus-entware':
                # Measured reports outlive each round and share the panel state directory.
                # Keep that data separate from the program files in the small /opt mount.
                tmpfs+=['--tmpfs','/opt/etc/nfqws-asus-web:rw,nosuid,nodev,noexec,mode=0755,size=96m']
            try:
                # The real library stages AUTO as nobody, then package root
                # resets its own copy. Only these two filesystem capabilities
                # are needed; source mounts stay read-only and network is none.
                cid=subprocess.check_output(['docker','create','--init','--pull=never','--name','nfqws-'+task,
                    '--label','org.nfqws2.task='+task,'--network','none','--cap-drop','ALL','--cap-add','CHOWN',
                    '--cap-add','DAC_OVERRIDE','--security-opt','no-new-privileges:true','--read-only',
                    '--pids-limit','48','--memory','128m','--cpus','0.5',*tmpfs,*mounts,'--entrypoint','/usr/bin/php8-cgi',
                    IMAGE,'-n','-d','register_argc_argv=1','-d','max_execution_time=0','-d','max_input_time=0',
                    '-q','-f','/fixtures/master.php','--',platform,*([pool] if pool else []),
                    *(['from-scratch',rounds] if from_scratch else [comparison,rounds] if comparison else ['storage-limit'] if limited_storage else ['series-recover' if recover else 'series',rounds] if rounds!='1' else ['mixed-recover' if recover else 'mixed'] if mixed else ['recover'] if recover else [])],text=True).strip()
                result=subprocess.run(['docker','start','-a',cid],capture_output=True,text=True,timeout=120)
                evidence.update({'id':cid,'status':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
                self.assertEqual(result.stderr,'',result.stdout+result.stderr)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                row=json.loads(result.stdout.strip())
                inspection=json.loads(subprocess.check_output(['docker','inspect',cid],text=True))[0]
                self.assertFalse(inspection['State']['OOMKilled'])
                self.assertEqual(inspection['HostConfig']['NetworkMode'],'none')
                self.assertEqual({cap.removeprefix('CAP_') for cap in inspection['HostConfig']['CapAdd']},
                                 {'CHOWN','DAC_OVERRIDE'})
                if from_scratch:
                    self.assertEqual(row['state'],'completed')
                    for field in ['restored','winner','generated','original_config','source_resources','service_off','worker_gone','guard_gone','empty_original_without_strategy','isolated_new_user_no_previous_history','new_one_round_journal_and_config_unchanged','same_missing_count_request_id_preserved']:
                        self.assertIs(row[field],True,(field,row))
                    self.assertEqual(row['requested'],'1000000');self.assertEqual(row['effective'],1000000)
                    self.assertEqual(row['series']['completed'],2);self.assertEqual(row['round_reports'],[True,True])
                    self.assertEqual(row['new_default_preview_rounds'],2);self.assertEqual(row['new_one_round_result'],'invalid_request')
                    self.assertGreater(len(row['trace']),20)
                    self.assertEqual({'current_based_candidates':row['current_based_candidates'],'cold_trials':row['cold_trials']},{'current_based_candidates':0,'cold_trials':[]})
                    self.assertEqual(row['incomplete_variant'], {
                        'apply': 'synthesis_unverified', 'export': 'synthesis_unverified', 'unchanged': True,
                    })
                    return row
                if comparison=='strong-original':
                    self.assertEqual(row['state'],'completed')
                    self.assertFalse(row['generation']['verified'])
                    self.assertFalse(row['generation']['versus_current']['eligible'])
                    self.assertIsNone(row['generated'])
                    self.assertIsNone(row['winner'])
                    self.assertEqual(row['operations'],{'pickerapply':'stale_state','pickerexport':'synthesis_unverified','unchanged':True})
                    for field in ['restored','original_config','config_metadata','source_resources','service_off','worker_gone','guard_gone']:
                        self.assertIs(row[field],True,field)
                    return row
                if comparison=='improvement':
                    self.assertEqual(row['state'], 'completed')
                    for field in ['restored','winner','generated','original_config','source_resources',
                                  'service_off','worker_gone','guard_gone','selected_matches_empty_kit','complete_dependencies']:
                        self.assertIs(row[field], True, (field,row))
                    self.assertGreater(row['generation']['versus_current']['gain'],0)
                    self.assertEqual(row['requested'],'100000')
                    self.assertEqual(row['effective'],100000)
                    self.assertEqual(row['matrix']['current_basis_candidates'],0)
                    if rounds!='1':
                        self.assertEqual(row['series']['completed'],int(rounds))
                        self.assertEqual(len(row['series']['runs']),int(rounds))
                        self.assertEqual(row['series']['selected'],1)
                        self.assertEqual(row['round_reports'],[True]*int(rounds))
                    for operation in ['export','apply','apply_worker']:
                        self.assertEqual(row['current_variant_tamper'][operation],'synthesis_unverified',operation)
                        self.assertTrue(row['current_variant_tamper'][operation+'_unchanged'],operation)
                    lifecycle=row['applied_lifecycle']
                    self.assertNotIn('error',lifecycle,lifecycle)
                    for field in ['actually_applied','new_snapshot_is_applied','resources_preserved','service_preserved',
                                  'old_artifacts_retired','new_request_launched','foreign_edits_blocked','live_actor_blocked',
                                  'inadmissible_pool_retains_previous','plan_preview_read_only','stale_plan_retains_previous']:
                        self.assertIs(lifecycle[field],True,(field,lifecycle))
                    return row
                if recover or limited_storage:
                    self.assertEqual(row['state'],'failed')
                    self.assertEqual(row['code'],'insufficient_space' if limited_storage else 'invalid_request')
                    for field in ['restored','original_config','config_metadata','source_resources','service_off','worker_gone','guard_gone']:
                        self.assertIs(row[field],True,field)
                    if rounds!='1':
                        self.assertEqual(row['series']['completed'],1)
                        self.assertEqual(row['series']['current'],2)
                    return
                for field in ['restored','winner','generated','complete_dependencies','personal_file_not_exported','diagnostics_not_exported',
                              'original_config','config_metadata','source_resources','service_off','worker_gone','guard_gone']:
                    self.assertIs(row[field],True,field)
                self.assertEqual(row['state'],'completed')
                self.assertTrue(row['generation']['independent_of_catalog'])
                self.assertTrue(row['generation']['verified'])
                self.assertEqual(row['generation']['from_zero']['custom']['minimum']['root_ok'],{'ok':10,'total':10})
                self.assertEqual(row['generation']['versus_current']['custom']['gain'],10)
                self.assertGreater(row['profiles'],3)
                self.assertGreater(row['samples'],6)
                self.assertEqual(row['resource_count'],5)
                custom_hosts=['1.1.1.1','8.8.4.4','8.8.8.8','alpha.example.com','beta.example.com'] if mixed else [
                    'alpha.example.com','beta.example.com','delta.example.com','epsilon.example.com','gamma.example.com']
                defaults=json.loads((ROOT/'support/dpi-native-defaults.json').read_text())['files']['domains.txt']
                expected_hosts={urlsplit(line if '://' in line else '//'+line).hostname for line in
                                (s.strip() for s in defaults.splitlines()) if line and not line.startswith('#')}
                expected_hosts.update(['youtube.com','www.youtube.com','discord.com','gateway.discord.gg','media.discordapp.net',
                                       'instagram.com','www.instagram.com','nnmclub.to','rutracker.org','rutor.info','tapochek.net'])
                expected_hosts.update(f'cdn-{i}.example.net' for i in range(1,111))
                expected_hosts.update(h for h in custom_hosts if h.endswith('.com'))
                self.assertCountEqual(row['scope'],expected_hosts)
                for host in ['www.youtube.com','nnmclub.to','rutracker.org','rutor.info','tapochek.net',
                             *[h for h in custom_hosts if h.endswith('.com')],*[f'cdn-{i}.example.net'for i in range(1,111)]]:
                    self.assertIn(host,row['scope'])
                if mixed:
                    self.assertIs(row['mixed_dispatch_verified'],True)
                    for host in custom_hosts[:3]:self.assertNotIn(host,row['scope']);self.assertIn(host,row['export_context'])
                    self.assertIn('могут затронуть другие сайты',row['export_context'])
                    recipe=row['selected_components'];self.assertCountEqual(recipe['custom_scope']['protected_domains'],expected_hosts)
                    addresses=[ip for rule in recipe['overrides']for ip in rule.get('addresses',[])]
                    self.assertEqual(sorted(addresses),custom_hosts[:3])
                    self.assertEqual(row['generation']['scope_guard_rules'],2)
                    self.assertEqual(row['generation']['custom_profile_count'],row['generation']['overrides']+2)
                self.assertEqual(row['worker']['heap'],'64M')  # Existing trusted launcher limit.
                self.assertTrue(row['worker']['completed'])
                for read in row['fresh_requests']:
                    self.assertEqual(read['initial_heap'],'8M')  # Firmware CGI default.
                    self.assertEqual(read['heap'],'32M')  # Existing index.php bootstrap.
                    self.assertEqual(read['state'],'completed')
                    self.assertGreater(read['bytes'],0)
                    if read['visible_custom'] is not None:
                        self.assertEqual(read['visible_custom'],{'hosts':custom_hosts,
                            'only':platform=='asus-entware','can_apply':True,'can_export':True})
                self.assertEqual(len(row['tamper_checks']),16 if mixed else 12)
                for case,result in row['tamper_checks'].items():
                    self.assertEqual(result['export'],'synthesis_unverified',case)
                    self.assertEqual(result['apply'],'synthesis_unverified',case)
                    self.assertEqual(result['apply_worker'],'synthesis_unverified',case)
                    self.assertTrue(result['no_mutation'],case)
                    self.assertTrue(result['worker_no_mutation'],case)
                    self.assertTrue(result['status_blocked'],case)
                # This fixture deliberately has no Detector binary. Valid
                # evidence must reach that later preflight, without applying.
                self.assertEqual(row['valid_apply_gate'],{'admission':'not_installed','worker':'not_installed'})
                self.assertEqual(row['request_retries'],{'same':'same_job','host_change':'request_conflict',
                    'mode_change':'request_conflict','search_change':'invalid_request' if rounds!='1' else 'request_conflict','new_request':'not_installed'})
                if pool:
                    choice=row['public_status']['job']['concurrency_choice']
                    self.assertEqual(choice['requested'],pool)
                    self.assertEqual(choice['effective'],int(pool))
                    self.assertTrue(row['public_status']['job']['concurrency_valid'])
                    self.assertIn('requested='+pool+'; effective='+pool,row['export_context'])
                    self.assertEqual(row['concurrency_tamper'],dict(export='synthesis_unverified',
                        apply='synthesis_unverified',apply_worker='synthesis_unverified',no_mutation=True))
                lifecycle=row['applied_lifecycle']
                self.assertNotIn('error',lifecycle,lifecycle)
                for key in ['actually_applied','new_snapshot_is_applied','resources_preserved','service_preserved','old_artifacts_retired','new_request_launched','foreign_edits_blocked','live_actor_blocked','inadmissible_pool_retains_previous','plan_preview_read_only','stale_plan_retains_previous']:
                    self.assertIs(lifecycle[key],True,(key,lifecycle))
                return row
            finally:
                if cid:
                    info=json.loads(subprocess.check_output(['docker','inspect',cid],text=True))[0]
                    self.assertEqual(info['Config']['Labels']['org.nfqws2.task'],task)
                    self.assertEqual(info['Name'],'/nfqws-'+task)
                    subprocess.run(['docker','rm','-f',cid],check=True,stdout=subprocess.DEVNULL)
                    absent=subprocess.run(['docker','inspect',cid],capture_output=True).returncode!=0
                    self.assertTrue(absent)
                    evidence['container_removed_independently_verified']=absent
                if os.environ.get('NFQWS_TEST_CUSTOM_SYNTHESIS_EVIDENCE_DIR'):
                    path=Path(os.environ['NFQWS_TEST_CUSTOM_SYNTHESIS_EVIDENCE_DIR'])
                    self.assertTrue(path.is_absolute())
                    path.mkdir(parents=True,exist_ok=True)
                    label='from-scratch' if from_scratch else comparison or ('storage-limit' if limited_storage else '')
                    (path/(platform+('-pool'+pool if pool else '')+('-mixed' if mixed else '')+('-recovery' if recover else '')+('-'+label if label else '')+('-rounds'+rounds if rounds!='1' else '')+'.json')).write_text(json.dumps(evidence,indent=2)+'\n')

    def test_empty_kit_improves_controlled_tls_with_real_library_restore_and_export(self):
        self.run_flow('asus-entware','100000',comparison='improvement')

    def test_better_original_has_no_winner_apply_or_export(self):
        self.run_flow('asus-entware','100000',comparison='strong-original')

    def test_openwrt_insufficient_report_space_restores_without_selecting_a_winner(self):
        self.run_flow('openwrt','32',limited_storage=True)

    def test_two_preselected_rounds_restore_and_keep_the_better_first_result(self):
        self.run_flow('asus-entware','100000',comparison='improvement',rounds='2')

    def test_preselected_series_stops_at_the_second_round_failure_and_restores(self):
        self.run_flow('asus-entware','100000',recover=True,rounds='2')

    def test_two_custom_rounds_keep_separate_bounded_artifacts_and_export(self):
        row=self.run_flow('asus-entware','300',rounds='2')
        self.assertEqual(row['series']['completed'],2)
        self.assertEqual(len(row['round_sample_counts']),2)
        self.assertTrue(all(0<count<=32 for count in row['round_sample_counts']))
        self.assertEqual(row['round_sample_counts'][row['series']['selected']-1],row['samples'])
        self.assertLessEqual(row['samples'],32)

    def test_new_matrix_repeats_best_families_with_the_same_restoration_and_export_flow(self):
        row=self.run_flow('asus-entware','300')
        self.assertEqual(row['matrix']['knowledge_version'],'zapret2-1.0.7-v4')
        self.assertGreater(row['matrix'].get('best_retested',0),0)
        self.assertLessEqual(row['matrix']['tested'],14)

    def test_asus_custom_only_synthesizes_all_five_sites_and_exports_the_complete_kit(self):
        self.run_flow('asus-entware')

    def test_openwrt_joint_synthesizes_all_five_sites_and_exports_the_complete_kit(self):
        self.run_flow('openwrt')

    def test_asus_manual_pool_survives_custom_generation_export_and_recovery(self):
        self.run_flow('asus-entware','32')

    def test_openwrt_manual_pool_survives_joint_generation_export_and_recovery(self):
        self.run_flow('openwrt','32')

    def test_asus_manual_pool_metadata_failure_restores_the_switched_candidate(self):
        self.run_flow('asus-entware','32',recover=True)

    def test_openwrt_manual_pool_metadata_failure_restores_the_switched_candidate(self):
        self.run_flow('openwrt','32',recover=True)

    def test_asus_mixed_ip_custom_only_has_full_dependencies_and_apply_retirement(self):
        self.run_flow('asus-entware','10',mixed=True)

    def test_openwrt_mixed_ip_joint_has_full_dependencies_and_apply_retirement(self):
        self.run_flow('openwrt','10',mixed=True)

    def test_asus_mixed_ip_metadata_failure_restores_the_switched_candidate(self):
        self.run_flow('asus-entware','10',recover=True,mixed=True)

    def test_openwrt_mixed_ip_metadata_failure_restores_the_switched_candidate(self):
        self.run_flow('openwrt','10',recover=True,mixed=True)


    def test_asus_from_scratch_two_rounds_million_has_no_current_based_candidates_and_equal_warmups(self):
        self.run_flow('asus-entware',pool='1000000',rounds='2',from_scratch=True)


if __name__=='__main__':unittest.main()

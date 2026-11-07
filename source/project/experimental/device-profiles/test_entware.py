import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


class Entware(unittest.TestCase):
    def setUp(self):
        self.old_umask=os.umask(0o077)

    def tearDown(self):
        os.umask(self.old_umask)

    def overlay(self):
        path=HERE/'entware_overlay.py'
        self.assertTrue(path.exists(),'missing Entware adapter overlay')
        spec=importlib.util.spec_from_file_location('entware_overlay',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module

    def files(self):
        return {key:(ROOT/'asus'/name).read_text()for key,name in [
            ('init','S51nfqws2'),('lifecycle','lifecycle.sh'),('platform','platform.sh')]}

    def shell(self,code,env=None):
        if os.geteuid()!=0:self.skipTest('root ownership fixtures: run sudo -n python3 -m unittest discover -s experimental/device-profiles -p test_entware.py')
        self.assertTrue((HERE/'device-profiles-entware.sh').exists(),'missing Entware service helper')
        shell=[shutil.which('busybox'),'sh']if shutil.which('busybox')else['/bin/sh']
        return subprocess.run(shell+['-c','. "$1"; '+code,'test',str(HERE/'device-profiles-entware.sh')],
            env=os.environ|(env or {}),text=True,capture_output=True,timeout=20)

    def test_overlay_requires_exact_known_layout_and_parses(self):
        module=self.overlay();files=self.files();patched=module.patch_entware(files)
        with tempfile.TemporaryDirectory()as temp:
            for key,value in patched.items():
                path=Path(temp)/key;path.write_text(value)
                subprocess.run(['/bin/sh','-n',str(path)],check=True,capture_output=True)
        with self.assertRaises(ValueError):module.patch_entware(patched)
        bad=files|{'lifecycle':files['lifecycle'].replace('asus_kill() {','asus_kill_changed() {')}
        with self.assertRaises(ValueError):module.patch_entware(bad)

    def test_real_renderer_keeps_exclusions_and_normal_fallback(self):
        files=self.overlay().patch_entware(self.files())
        with tempfile.TemporaryDirectory()as temp:
            path=Path(temp);(path/'rules-entware4.restore').write_text(
                ':nfqa_dp_0_out - [0:0]\n-F nfqa_dp_0_out\n'
                '-A nfqa_dp_0_out -j RETURN\n'
                '-A nfqa_out -m conntrack --ctorigsrc 192.168.20.4 -g nfqa_dp_0_out\n')
            platform=path/'platform';platform.write_text(files['platform'])
            code='. "$PLATFORM"; asus_rules 4 mangle'
            p=self.shell(code,{'PLATFORM':str(platform),'NFQWS_LAB_RUN':temp,
                'ASUS_CLIENT_MODE':'exclude','ASUS_CLIENTS4':'192.168.20.5','ASUS_CLIENTS6':'',
                'ASUS_WAN':'wan0','TCP_PORTS':'80,443','UDP_PORTS':'443','NFQUEUE_NUM':'300'})
            self.assertEqual(p.returncode,0,p.stderr)
            self.assertLess(p.stdout.index('--ctorigsrc 192.168.20.5 -j RETURN'),p.stdout.index('-g nfqa_dp_0_out'))
            self.assertLess(p.stdout.index('-g nfqa_dp_0_out'),p.stdout.index('--queue-num 300'))
            self.assertEqual(p.stdout.count('*mangle'),1);self.assertEqual(p.stdout.count('COMMIT'),1)

    def test_common_mode_preserves_every_existing_family_and_client_mode_rule(self):
        original=self.files();patched=self.overlay().patch_entware(original)
        with tempfile.TemporaryDirectory()as temp:
            path=Path(temp);(path/'original').write_text(original['platform']);(path/'patched').write_text(patched['platform'])
            env={'NFQWS_LAB_RUN':temp,'ASUS_CLIENTS4':'192.168.20.5','ASUS_CLIENTS6':'fd42::5',
                'ASUS_WAN':'wan0 wan1','TCP_PORTS':'80,443','UDP_PORTS':'443','NFQUEUE_NUM':'300'}
            for family in [4,6]:
                for mode in ['all','include','exclude']:
                    for direction in ['normal','reverse']:
                        with self.subTest(family=family,mode=mode,direction=direction):
                            current=env|{'ASUS_CLIENT_MODE':mode,'ASUS_CT4':direction,'ASUS_CT6':direction}
                            code='. "$PLATFORM"; asus_rules '+str(family)+' mangle'
                            expected=self.shell(code,current|{'PLATFORM':str(path/'original')})
                            actual=self.shell(code,current|{'PLATFORM':str(path/'patched')})
                            self.assertEqual(expected.returncode,0,expected.stderr)
                            self.assertEqual(actual.returncode,0,actual.stderr)
                            self.assertEqual(actual.stdout,expected.stdout)

    def test_owned_chain_guard_refuses_a_foreign_name_collision(self):
        with tempfile.TemporaryDirectory()as temp:
            path=Path(temp);(path/'rules-entware4.restore').write_text(':nfqa_dp_0_out - [0:0]\n')
            p=self.shell('''iptables() { printf '%s\\n' '-N nfqa_dp_0_out' '-A nfqa_dp_0_out -j DROP'; }
nfqws_lab_entware_firewall_guard 4''',{'NFQWS_LAB_RUN':temp,'RUN_DIR':temp})
            self.assertNotEqual(p.returncode,0)
            self.assertNotIn('not found',p.stderr)

    def test_dynamic_mac_rule_changes_apply_with_service_globbing_disabled(self):
        with tempfile.TemporaryDirectory()as temp:
            path=Path(temp);(path/'rules-entware4.restore').write_text('old\n')
            p=self.shell('''set -f
nfqws_lab_entware_php() { printf 'new\\n' > "$NFQWS_LAB_RUN/rules-entware4.restore"; }
asus_firewall_apply() { printf 'applied\\n'; }
nfqws_lab_entware_reconcile''',{'NFQWS_LAB_RUN':temp,'RUN_DIR':temp})
            self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(p.stdout,'applied\n')

    def test_detached_validation_never_references_live_chains(self):
        with tempfile.TemporaryDirectory()as temp:
            path=Path(temp);(path/'rules-entware4.restore').write_text(
                ':nfqa_dp_0_out - [0:0]\n-F nfqa_dp_0_out\n'
                '-A nfqa_dp_0_out -p tcp -j NFQUEUE --queue-num 41000 --queue-bypass\n'
                '-A nfqa_out -m conntrack --ctorigsrc 192.168.20.4 -g nfqa_dp_0_out\n')
            code='''iptables() { case "$*" in *" -S "*) return 1;; esac; return 0; }
asus_restore_rules() { cat > "$CAPTURE"; }
nfqws_lab_entware_validate_fragment 4'''
            p=self.shell(code,{'NFQWS_LAB_RUN':temp,'RUN_DIR':temp,'CAPTURE':str(path/'capture')})
            self.assertEqual(p.returncode,0,p.stderr)
            raw=(path/'capture').read_text()
            self.assertNotIn('nfqa_in',raw);self.assertNotIn('nfqa_out',raw);self.assertNotIn('nfqa_dp_',raw)
            self.assertIn('nfqa_dpt_',raw);self.assertIn('--queue-num 41000',raw)
            self.assertFalse(list(path.glob('probe-*')))

    @unittest.skipUnless(shutil.which('cc'),'needs a tiny real test daemon')
    def test_stop_rejects_reused_identity_then_stops_only_owned_daemon(self):
        with tempfile.TemporaryDirectory()as temp:
            path=Path(temp);active=path/'device-profiles/active';active.mkdir(parents=True,mode=0o700)
            active.parent.chmod(0o700)
            source=path/'engine.c';binary=path/'engine'
            source.write_text('''#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <stdlib.h>
int main(int argc,char **argv){const char *pid=0;for(int i=1;i<argc;i++){
if(!strcmp(argv[i],"--dry-run"))return 0;if(!strncmp(argv[i],"--pidfile=",10))pid=argv[i]+10;}
if(!pid)return 2;pid_t child=fork();if(child<0)return 3;if(child)return 0;
FILE *f=fopen(pid,"w");if(!f)return 4;fprintf(f,"%d\\n",getpid());fclose(f);
close(0);close(1);close(2);while(1)pause();}''')
            subprocess.run(['cc',str(source),'-o',str(binary)],check=True,capture_output=True)
            (active/'args.0').write_text('--user=nobody --qnum=41000')
            env={'RUN_DIR':temp,'NFQWS_LAB_RUN':str(active),'NFQWS_BIN':str(binary)}
            p=self.shell('nfqws_lab_entware_php() { return 0; }; nfqws_lab_entware_start',env)
            self.assertEqual(p.returncode,0,p.stderr)
            pid=int((path/'device-profiles/engine-0.pid').read_text())
            identity=path/'device-profiles/engine-0.identity';saved=identity.read_text()
            try:
                fields=saved.splitlines();fields[1]='0';identity.write_text('\n'.join(fields)+'\n')
                p=self.shell('nfqws_lab_entware_stop',env)
                self.assertNotEqual(p.returncode,0);os.kill(pid,0)
                identity.write_text(saved)
                # A real daemon exit must allow an ordinary service restart.
                os.kill(pid,15)
                for _ in range(50):
                    stat=Path('/proc')/str(pid)/'stat'
                    if not stat.exists()or stat.read_text().split(') ')[-1].startswith('Z '):break
                    time.sleep(0.01)
                p=self.shell('nfqws_lab_entware_stop',env)
                self.assertEqual(p.returncode,0,p.stderr)
                self.assertFalse(identity.exists());self.assertFalse((path/'device-profiles/engine-0.pid').exists())
                p=self.shell('nfqws_lab_entware_php() { return 0; }; nfqws_lab_entware_start',env)
                self.assertEqual(p.returncode,0,p.stderr)
                pid=int((path/'device-profiles/engine-0.pid').read_text())
                p=self.shell('nfqws_lab_entware_stop',env)
                self.assertEqual(p.returncode,0,p.stderr)
                self.assertFalse(identity.exists())
                # Main-crash recovery detaches dispatch before reclaiming an
                # orphan profile engine and before starting any new work.
                p=self.shell('nfqws_lab_entware_php() { return 0; }; nfqws_lab_entware_start',env)
                self.assertEqual(p.returncode,0,p.stderr)
                pid=int((path/'device-profiles/engine-0.pid').read_text())
                lifecycle=path/'lifecycle'
                lifecycle.write_text(self.overlay().patch_entware(self.files())['lifecycle'])
                p=self.shell('''. "$LIFECYCLE"
asus_running() { return 1; }
asus_firewall_stop() { printf 'firewall\\n' >> "$EVENTS"; }
asus_check() { printf 'check\\n' >> "$EVENTS"; return 1; }
asus_start''',env|{'LIFECYCLE':str(lifecycle),'EVENTS':str(path/'events')})
                self.assertNotEqual(p.returncode,0)
                self.assertEqual((path/'events').read_text(),'firewall\ncheck\n')
                self.assertFalse(identity.exists())
            finally:
                try:os.kill(pid,15)
                except ProcessLookupError:pass


if __name__=='__main__':unittest.main()

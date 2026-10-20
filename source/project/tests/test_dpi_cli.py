"""The displayed Entware command must launch the installed native tool verbatim."""
import os, subprocess, tempfile, unittest
from pathlib import Path
from test_dpi_normalize import ROOT

class DpiCliTests(unittest.TestCase):
    def test_native_saved_report_is_private_even_from_permissive_shell(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);native=p/'native';native.write_text('#!/bin/sh\nprintf report > result.txt\n');native.chmod(0o755)
            resolver=p/'php';resolver.write_text('#!/bin/sh\nprintf "%s\\n" "'+str(native)+'"\n');resolver.chmod(0o755)
            helper=p/'cli';helper.write_text((ROOT/'asus/dpi/cli.sh').read_text().replace('/opt/bin/php-cgi',str(resolver)))
            r=subprocess.run(['sh','-c','umask 022; exec sh "$1"','sh',str(helper)],cwd=d,capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertEqual((p/'result.txt').stat().st_mode & 0o777,0o600)

    def test_command_forwards_arguments_and_exit_status_without_shell_evaluation(self):
        source=ROOT/'asus/dpi/cli.sh'
        self.assertTrue(source.exists(), 'standalone Entware command missing')
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); native=p/'native tool'
            native.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\nexit 7\n');native.chmod(0o755)
            resolver=p/'php-cgi';resolver.write_text('#!/bin/sh\nprintf "%s\\n" "'+str(native)+'"\n');resolver.chmod(0o755)
            helper=p/'cli';helper.write_text(source.read_text().replace('/opt/bin/php-cgi',str(resolver)))
            r=subprocess.run(['sh',str(helper),'--tests','12','$(touch NEVER)'],capture_output=True,text=True,cwd=d)
            self.assertEqual(r.returncode,7);self.assertEqual(r.stdout,'--tests\n12\n$(touch NEVER)\n');self.assertFalse((p/'NEVER').exists())

    def test_missing_component_does_not_run_a_different_binary(self):
        source=ROOT/'asus/dpi/cli.sh';self.assertTrue(source.exists(), 'standalone Entware command missing')
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);resolver=p/'php-cgi';resolver.write_text('#!/bin/sh\nexit 1\n');resolver.chmod(0o755)
            helper=p/'cli';helper.write_text(source.read_text().replace('/opt/bin/php-cgi',str(resolver)))
            r=subprocess.run(['sh',str(helper)],capture_output=True,text=True)
            self.assertNotEqual(r.returncode,0);self.assertIn('WebUI',r.stderr)

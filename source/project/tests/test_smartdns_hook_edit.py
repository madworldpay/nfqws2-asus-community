"""The native rollback filter preserves exact foreign bytes, including EOF."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_dpi_normalize import ROOT,PHP,PUBLIC

FILTER=ROOT/'asus/smartdns/hook-edit.awk'


class SmartDnsNativeHookEditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p=subprocess.run([PHP,'-n','-r',"require $argv[1].'/smartdns-connect.php';echo AsusSmartDnsHook::BLOCK;",str(PUBLIC)],capture_output=True,check=True)
        cls.block=p.stdout

    def remove(self,body):
        if not FILTER.is_file():return 2,b'missing_native_hook_filter'
        with tempfile.TemporaryDirectory() as d:
            block=Path(d)/'block';block.write_bytes(self.block)
            result=subprocess.run(['/bin/busybox','awk','-v','expected='+str(block),'-v','ending='+('1' if body.endswith(b'\n') else '0'),'-f',str(FILTER)],input=body,capture_output=True,timeout=3)
        self.assertEqual(result.stderr,b'');return result.returncode,result.stdout

    def test_prefix_suffix_and_original_missing_newline_are_byte_exact(self):
        for before in [b'',b'#!/bin/sh\n',b'#!/bin/sh\nprintf x',b'#!/bin/sh\n\nprintf x\n',"#!/bin/sh\n# Чужая настройка\nprintf '\\t'\r\n".encode()]:
            for after in [b'',b'\n# new foreign edit\n',b'printf suffix',b'\n\n# suffix\n']:
                with self.subTest(before=before,after=after):
                    code,value=self.remove(before+self.block+after)
                    self.assertEqual(code,0);self.assertEqual(value,before+after)

    def test_changed_duplicate_or_missing_block_is_never_accepted(self):
        for body in [b'#!/bin/sh\n',self.block.replace(b'postconf',b'CHANGED'),self.block+self.block,
                     self.block[:-1],self.block[1:],self.block+b'# NFQWS2 SMARTDNS MANAGED extra\n']:
            with self.subTest(body=body):self.assertNotEqual(self.remove(body)[0],0)


if __name__=='__main__':unittest.main()

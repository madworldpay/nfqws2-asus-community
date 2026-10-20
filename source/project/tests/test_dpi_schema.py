import json
import os
from pathlib import Path
import subprocess
import unittest
from test_dpi_normalize import PHP, PUBLIC, ROOT


class DpiSchemaTests(unittest.TestCase):
    def validate(self,raw,kind):
        p=subprocess.run([PHP,'-n','-r',
            "require $argv[1].'/support-json-schema.php';try{AsusSupportSchema::validate(stream_get_contents(STDIN),$argv[2]);echo 'valid';}catch(Throwable $e){echo $e->getMessage();}",str(PUBLIC),kind],input=raw,text=True,capture_output=True)
        self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(p.stderr,'')
        return p.stdout

    def test_existing_collector_schema_is_checked_on_router(self):
        raw=subprocess.check_output([PHP,'-n',str(ROOT/'tests/emit_support_report_fixture.php')]).decode()
        self.assertEqual(self.validate(raw,'report'),'valid')
        value=json.loads(raw);value['private']='PRIVATE_CANARY'
        self.assertEqual(self.validate(json.dumps(value),'report'),'invalid_report')
        self.assertEqual(self.validate(raw.replace('{','{"schema_version":1,',1),'report'),'invalid_report')

    def test_envelope_has_two_ordered_files_with_canonical_names_and_size_bounds(self):
        file=lambda kind,name,size:dict(type=kind,filename=name,byte_length=size,sha256='a'*64,data_base64='e30=')
        envelope={'version':2,'submission_id':'11111111-1111-4111-8111-111111111111','files':[
            file('report','NFQWS2_ASUS-unknown_2026-10-15_12-30-00Z.json',2),
            file('dpi','NFQWS2_DPI_2026-10-15_12-30-00Z.json',2)]}
        self.assertEqual(self.validate(json.dumps(envelope),'envelope'),'valid')
        envelope['files'].reverse()
        self.assertEqual(self.validate(json.dumps(envelope),'envelope'),'invalid_bundle')

    def test_numeric_strings_do_not_satisfy_integer_constants(self):
        raw=subprocess.check_output([PHP,'-n',str(ROOT/'tests/emit_support_report_fixture.php')]).decode()
        value=json.loads(raw);value['schema_version']='1'
        self.assertEqual(self.validate(json.dumps(value),'report'),'invalid_report')

    def test_schema_bounds_and_duplicate_keys_reject_data_before_projection(self):
        for raw in ['{"version":2,"version":2}', '{"x":'+('['*33)+'0'+(']'*33)+'}', '{"x":NaN}', '{"x":1e999}']:
            self.assertEqual(self.validate(raw,'envelope'),'invalid_bundle')

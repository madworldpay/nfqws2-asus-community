"""Packaging must not ship a valid loader with missing or stale Unicode data."""
from frontend_fixture import copy_public
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
PUBLIC=ROOT/'webui/web/public'


def module(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


class IdnaPayloadTests(unittest.TestCase):
    def test_both_platform_payloads_supply_exact_unicode_data_without_dist_copies(self):
        with tempfile.TemporaryDirectory()as directory:
            dist=copy_public(Path(directory),include_vendor=False)
            for family,prefix in [('asus','opt/share/nfqws-asus-web/'),('openwrt','usr/share/nfqws2-web/')]:
                with self.subTest(family=family):
                    builder=module('idna_'+family,ROOT/family/'build.py');payload=builder.web_payload(dist)
                    for name in ['idn/Idn.php','normalizer/Normalizer.php','idn/Resources/unidata/mapped.php',
                                 'normalizer/Resources/unidata/canonicalComposition.php','idn/LICENSE.txt','normalizer/LICENSE.txt']:
                        self.assertEqual(payload[prefix+'vendor-idna/'+name],((PUBLIC/'vendor-idna'/name).read_bytes(),0o644))

    def test_missing_or_tampered_vendor_file_refuses_packaging(self):
        path=ROOT/'webui/idna_payload.py'
        self.assertTrue(path.is_file(),'verified dependency packaging helper is missing')
        helper=module('idna_payload_test',path)
        with tempfile.TemporaryDirectory()as directory:
            public=Path(directory);shutil.copytree(PUBLIC/'vendor-idna',public/'vendor-idna')
            table=public/'vendor-idna/idn/Resources/unidata/mapped.php';original=table.read_bytes()
            table.write_bytes(original+b'\n')
            with self.assertRaisesRegex(RuntimeError,'IDNA dependency'):helper.payload(public)
            table.write_bytes(original);table.unlink()
            with self.assertRaisesRegex(RuntimeError,'IDNA dependency'):helper.payload(public)

    def test_a_symlinked_dependency_cannot_substitute_a_pinned_file(self):
        path=ROOT/'webui/idna_payload.py';self.assertTrue(path.is_file(),'verified dependency packaging helper is missing')
        helper=module('idna_payload_link_test',path)
        with tempfile.TemporaryDirectory()as directory:
            public=Path(directory);shutil.copytree(PUBLIC/'vendor-idna',public/'vendor-idna')
            table=public/'vendor-idna/idn/Idn.php';raw=table.read_bytes();table.unlink();outside=public/'same.php';outside.write_bytes(raw);table.symlink_to(outside)
            with self.assertRaisesRegex(RuntimeError,'IDNA dependency'):helper.payload(public)

    def test_the_provenance_manifest_itself_cannot_be_a_symlink(self):
        helper=module('idna_payload_manifest_link_test',ROOT/'webui/idna_payload.py')
        with tempfile.TemporaryDirectory()as directory:
            public=Path(directory);shutil.copytree(PUBLIC/'vendor-idna',public/'vendor-idna')
            manifest=public/'vendor-idna/provenance.json';outside=public/'manifest.json';manifest.rename(outside);manifest.symlink_to(outside)
            with self.assertRaisesRegex(RuntimeError,'IDNA dependency'):helper.payload(public)


if __name__=='__main__':unittest.main()

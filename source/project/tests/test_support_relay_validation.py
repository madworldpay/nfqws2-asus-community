import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "support-relay/src"))
from nfqws_support.validation import InvalidReport, validate_report

FILENAME = "NFQWS2_GT-BE19000AI_2026-10-15_12-30-45Z.json"


def fixture(mode="", header_root=""):
    php = os.environ.get("PHP_TEST_BINARY", str(ROOT / ".work/packaging-audit-20261012/aarch64-cli-wrapper"))
    return subprocess.check_output([php, "-n", str(ROOT / "tests/emit_support_report_fixture.php"), mode, str(header_root)])


class ValidationTests(unittest.TestCase):
    def assertInvalid(self, raw, filename=FILENAME):
        with self.assertRaises(InvalidReport) as caught:
            validate_report(raw, filename)
        self.assertNotIn("PRIVATE_CANARY", str(caught.exception))

    def test_actual_collector_and_truncated_report_preserve_digest(self):
        for mode in ("", "truncated"):
            raw = fixture(mode)
            info = validate_report(raw, FILENAME)
            self.assertEqual(info.sha256, hashlib.sha256(raw).hexdigest())
            self.assertEqual(info.size, len(raw))
            self.assertEqual(info.model, "GT-BE19000AI")
            self.assertFalse(info.complete)

    def test_accepts_combined_ipv4_and_ipv6_collector_client_limits(self):
        for mode, count in [('clients65',65), ('clients128',128)]:
            raw=fixture(mode)
            self.assertEqual(len(json.loads(raw)['sections']['network']['data']['clients']),count)
            self.assertEqual(validate_report(raw,FILENAME).size,len(raw))

    def test_accepts_corrupt_elf_class_bytes_read_from_engine_and_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for value in (3,255):
                header=b'\x7fELF'+bytes([value,1])+b'\0'*12+b'\xb7\0'
                for relative in ('usr/bin/nfqws2','libexec/nfqws2-asus/busybox'):
                    path=root/relative; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(header)
                raw=fixture('corrupt-elf',root); report=json.loads(raw)
                self.assertEqual(report['sections']['engine']['data']['elf_class'],value)
                self.assertEqual(report['sections']['package']['data']['runtime_components']['shell']['elf_class'],value)
                self.assertEqual(validate_report(raw,FILENAME).size,len(raw))

    def test_rejects_unknown_fields_at_every_object_boundary(self):
        report = json.loads(fixture())
        objects = []
        def visit(value, path):
            if isinstance(value, dict):
                objects.append(path)
                for key, item in value.items(): visit(item, path + [key])
            elif isinstance(value, list):
                for key, item in enumerate(value): visit(item, path + [key])
        visit(report, [])
        for path in objects:
            mutated = copy.deepcopy(report)
            obj = mutated
            for key in path: obj = obj[key]
            obj["PRIVATE_CANARY"] = "PRIVATE_CANARY"
            with self.subTest(path=path): self.assertInvalid(json.dumps(mutated).encode())

    def test_rejects_unredacted_values_and_missing_sections(self):
        base = json.loads(fixture())
        for path, value in ((["model"], "PRIVATE_CANARY"),
                            (["sections", "network", "data", "interfaces", 0, "id"], "192.0.2.1"),
                            (["sections", "platform", "data", "firmware", "firmver"], "PRIVATE_CANARY")):
            report = copy.deepcopy(base); obj = report
            for key in path[:-1]: obj = obj[key]
            obj[path[-1]] = value
            self.assertInvalid(json.dumps(report).encode())
        del base["sections"]["errors"]
        self.assertInvalid(json.dumps(base).encode())

    def test_rejects_duplicate_keys_invalid_utf8_nonfinite_depth_and_size(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":{"b":1,"b":2}}', b'{"a":NaN}',
                    b'{"a":Infinity}', b'\xff', b'['*33+b'0'+b']'*33, b' '*1048577):
            self.assertInvalid(raw)

    def test_rejects_filename_injection_and_timestamp_mismatch(self):
        raw = fixture()
        for name in (FILENAME+"\r\nX: PRIVATE_CANARY", FILENAME.replace("12-30", "12-31"),
                     FILENAME.replace("GT-BE19000AI", "RT-AX88U"), "../"+FILENAME):
            self.assertInvalid(raw, name)

    def test_exponent_overflow_is_not_a_finite_json_number(self):
        raw = fixture().replace(b'"age_seconds": null', b'"age_seconds": 1e309')
        self.assertInvalid(raw)

    def test_schema_refs_are_local_and_schema_is_closed(self):
        schema = json.loads((ROOT / "support/report.schema.json").read_text())
        def visit(value):
            if isinstance(value, dict):
                if "$ref" in value: self.assertTrue(value["$ref"].startswith("#/"))
                if value.get("type") == "object": self.assertIs(value["additionalProperties"], False)
                for item in value.values(): visit(item)
            elif isinstance(value, list):
                for item in value: visit(item)
        visit(schema)

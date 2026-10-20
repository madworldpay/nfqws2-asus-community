"""Validate a closed, anonymized collector format without echoing input."""

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import math
from pathlib import Path

from jsonschema import Draft202012Validator

MAX_BYTES = 1048576
SCHEMA_PATH = Path(__file__).resolve().parents[3] / "support/report.schema.json"


class InvalidReport(ValueError):
    def __init__(self, code="invalid_report"):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ReportInfo:
    model: str
    captured_at: str
    complete: bool
    sha256: str
    size: int


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidReport()
        result[key] = value
    return result


def _constant(_value):
    raise InvalidReport()


def _float(value):
    number = float(value)
    if not math.isfinite(number):
        raise InvalidReport()
    return number


def _bounded_depth(text):
    depth = 0
    quoted = escaped = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > 32:
                raise InvalidReport()
        elif char in "]}":
            depth -= 1


def _local_schema(value):
    if isinstance(value, dict):
        if "$ref" in value and not value["$ref"].startswith("#/"):
            raise RuntimeError("invalid_schema")
        for item in value.values():
            _local_schema(item)
    elif isinstance(value, list):
        for item in value:
            _local_schema(item)


_schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
_local_schema(_schema)
Draft202012Validator.check_schema(_schema)
_validator = Draft202012Validator(_schema)


def validate_report(raw: bytes, filename: str) -> ReportInfo:
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_BYTES:
        raise InvalidReport()
    try:
        text = raw.decode("utf-8", errors="strict")
        _bounded_depth(text)
        value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant, parse_float=_float)
        if not _validator.is_valid(value):
            raise InvalidReport()
        captured = datetime.strptime(value["captured_at"], "%Y-%m-%dT%H:%M:%SZ")
        expected = f'NFQWS2_{value["model"]}_{captured:%Y-%m-%d_%H-%M-%S}Z.json'
        if filename != expected:
            raise InvalidReport("invalid_filename")
        platform = value["sections"]["platform"]["data"]
        if isinstance(platform, dict) and platform["model"] != value["model"]:
            raise InvalidReport()
    except (UnicodeError, ValueError, TypeError, KeyError, RecursionError, OverflowError):
        raise InvalidReport() from None
    return ReportInfo(value["model"], value["captured_at"], value["complete"], sha256(raw).hexdigest(), len(raw))

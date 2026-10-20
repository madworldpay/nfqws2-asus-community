"""Closed, identity-free projection of a pinned detector result."""
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
from jsonschema import Draft202012Validator
from .validation import InvalidReport,SCHEMA_PATH,_pairs,_constant,_float,_bounded_depth

@dataclass(frozen=True)
class DpiReportInfo:
    sha256:str
    size:int
    started_at:str
    complete:bool

_validators={v:Draft202012Validator(json.loads((SCHEMA_PATH.parent/name).read_text())) for v,name in [(1,'dpi-report.schema.json'),(2,'dpi-analysis-v2.schema.json')]}
def validate_dpi_report(raw:bytes,filename:str)->DpiReportInfo:
    try:
        if not isinstance(raw,bytes) or not 0<len(raw)<=262144:raise InvalidReport()
        text=raw.decode('utf-8','strict');_bounded_depth(text);value=json.loads(text,object_pairs_hook=_pairs,parse_constant=_constant,parse_float=_float)
        version=value.get('schema_version') if isinstance(value,dict) else None
        if type(version) is not int or version not in _validators or not _validators[version].is_valid(value):raise InvalidReport()
        started=datetime.strptime(value['started_at'],'%Y-%m-%dT%H:%M:%SZ');finished=datetime.strptime(value['finished_at'],'%Y-%m-%dT%H:%M:%SZ')
        if finished<started or filename!=f'NFQWS2_DPI_{started:%Y-%m-%d_%H-%M-%S}Z.json':raise InvalidReport()
        groups=[g['group'] for g in value['groups']]
        if not groups or len(set(groups))!=len(groups) or not set(groups)<=set(value['selected_tests']):raise InvalidReport()
        if value['state']=='completed' and set(groups)!=set(value['selected_tests']):raise InvalidReport()
        return DpiReportInfo(sha256(raw).hexdigest(),len(raw),value['started_at'],value['state']=='completed')
    except (ValueError,TypeError,KeyError,UnicodeError,RecursionError,OverflowError):raise InvalidReport() from None

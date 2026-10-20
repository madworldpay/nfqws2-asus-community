"""Two bounded immutable files. No body persistence or network-selected headers."""
from dataclasses import dataclass
from hashlib import sha256
import base64,binascii,hmac,json
from jsonschema import Draft202012Validator
from .validation import InvalidReport,SCHEMA_PATH,_pairs,_constant,_float,_bounded_depth,validate_report
from .dpi_validation import validate_dpi_report
from .store import valid_submission_id

@dataclass(frozen=True)
class BundleFile:
    type:str
    filename:str
    raw:bytes
    sha256:str
@dataclass(frozen=True)
class ReportBundle:
    files:tuple[BundleFile,...]
    sha256:str

_validator=Draft202012Validator(json.loads((SCHEMA_PATH.parent/'dpi-envelope.schema.json').read_text()))
def validate_bundle(raw:bytes,submission_id:str)->ReportBundle:
    try:
        if not isinstance(raw,bytes) or not 0<len(raw)<=2097152 or not valid_submission_id(submission_id):raise InvalidReport()
        text=raw.decode('utf-8','strict');_bounded_depth(text);v=json.loads(text,object_pairs_hook=_pairs,parse_constant=_constant,parse_float=_float)
        if not _validator.is_valid(v) or v['submission_id']!=submission_id:raise InvalidReport()
        files=[];manifest=[]
        for f,kind,limit in zip(v['files'],('report','dpi'),(1048576,262144)):
            if len(f['data_base64'])>4*((limit+2)//3):raise InvalidReport()
            data=base64.b64decode(f['data_base64'],validate=True)
            if not 0<len(data)<=limit or len(data)!=f['byte_length'] or base64.b64encode(data).decode()!=f['data_base64']:raise InvalidReport()
            digest=sha256(data).hexdigest()
            if not hmac.compare_digest(digest,f['sha256']):raise InvalidReport()
            (validate_report if kind=='report' else validate_dpi_report)(data,f['filename'])
            files.append(BundleFile(kind,f['filename'],data,digest));manifest.append({'type':kind,'filename':f['filename'],'byte_length':len(data),'sha256':digest})
        digest=sha256(b'NFQWS2-BUNDLE\0v2\0'+json.dumps(manifest,sort_keys=True,separators=(',',':')).encode('ascii')).hexdigest()
        return ReportBundle(tuple(files),digest)
    except (ValueError,TypeError,KeyError,UnicodeError,RecursionError,OverflowError,binascii.Error):raise InvalidReport() from None

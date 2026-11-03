"""Closed v3 submissions; category labels and optional installation linkage."""
from dataclasses import dataclass
from hashlib import sha256
import base64,binascii,hmac,json,unicodedata
from jsonschema import Draft202012Validator
from .bundle import BundleFile
from .validation import InvalidReport,SCHEMA_PATH,_pairs,_constant,_float,_bounded_depth,validate_report
from .dpi_validation import validate_dpi_report
from .store import valid_submission_id

def _schema(name):
    return Draft202012Validator(json.loads((SCHEMA_PATH.parent/name).read_text()))
_envelope=_schema('share-envelope.schema.json')
_strategy=_schema('strategy.schema.json')
_saved=_schema('dpi-saved.schema.json')

@dataclass(frozen=True)
class ShareBundle:
    files:tuple[BundleFile,...]
    sha256:str
    submission_id:str
    source_json:str|None
    version:int=3

def _decode(raw):
    text=raw.decode('utf-8','strict');_bounded_depth(text)
    return json.loads(text,object_pairs_hook=_pairs,parse_constant=_constant,parse_float=_float)

def validate_share(raw:bytes,submission_id:str)->ShareBundle:
    try:
        if not isinstance(raw,bytes) or not 0<len(raw)<=4194304 or not valid_submission_id(submission_id):raise InvalidReport()
        value=_decode(raw)
        if isinstance(value,dict) and value.get('version')==4:
            from .share_v4 import validate_v4
            return validate_v4(raw,value,submission_id)
        if len(raw)>2097152:raise InvalidReport()
        if not _envelope.is_valid(value) or value['submission_id']!=submission_id:raise InvalidReport()
        order={'report':0,'dpi':1,'strategy':2};limits={'report':1048576,'dpi':262144,'strategy':65536};last=-1;files=[];manifest=[]
        for f in value['files']:
            kind=f['type'];at=order[kind];limit=limits[kind]
            if at<=last or len(f['data_base64'])>4*((limit+2)//3):raise InvalidReport()
            data=base64.b64decode(f['data_base64'],validate=True)
            if not 0<len(data)<=limit or len(data)!=f['byte_length'] or base64.b64encode(data).decode('ascii')!=f['data_base64']:raise InvalidReport()
            digest=sha256(data).hexdigest()
            if not hmac.compare_digest(digest,f['sha256']):raise InvalidReport()
            if kind=='report':validate_report(data,f['filename'])
            else:
                if not f['filename'].startswith('NFQWS2_DPI_' if kind=='dpi' else 'NFQWS2_STRATEGY_'):raise InvalidReport()
                content=_decode(data)
                if kind=='strategy':
                    if not _strategy.is_valid(content) or not content['operator'].strip() or not content['purpose'].strip():raise InvalidReport()
                elif isinstance(content,dict) and content.get('type')=='nfqws2_dpi_saved':
                    if not _saved.is_valid(content):raise InvalidReport()
                else:validate_dpi_report(data,f['filename'])
            files.append(BundleFile(kind,f['filename'],data,digest));last=at
            manifest.append({'type':kind,'filename':f['filename'],'byte_length':len(data),'sha256':digest})
        source=value.get('source');source_json=json.dumps(source,sort_keys=True,separators=(',',':')) if source is not None else None
        digest=sha256(b'NFQWS2-SHARE\0v3\0'+json.dumps({'files':manifest,'source':source},sort_keys=True,separators=(',',':')).encode('ascii')).hexdigest()
        return ShareBundle(tuple(files),digest,submission_id,source_json)
    except (ValueError,TypeError,KeyError,UnicodeError,RecursionError,OverflowError,binascii.Error):raise InvalidReport() from None

def share_subject(files)->str:
    kinds={f.type for f in files}
    diagnostics=bool(kinds&{'report','dpi'});strategies=bool(kinds&{'strategy','resources','dns'})
    return 'NFQWS2 community'+(' [diagnostics]' if diagnostics else '')+(' [strategies]' if strategies else '')

def _preview_value(value):
    # Validated export headers are at most 120 characters. Keep each value on
    # one visible line, including when it contains bidi/zero-width controls.
    return ' '.join(''.join(' ' if unicodedata.category(c) in ('Cc','Cf','Cs') else c for c in value).split())[:120]

def _preview_field(entries):
    entries=[(label,_preview_value(value)) for label,value in entries]
    entries=[(label,value) for label,value in entries if value]
    values={value for _,value in entries}
    if not values:return 'нет данных в экспорте'
    if len(values)==1:return entries[0][1]
    return 'различаются: '+'; '.join(label+': '+value for label,value in entries)

def _share_preview(bundle,source):
    fields={'model':[],'operator':[],'purpose':[]}
    if source is not None:fields['model'].append(('источник',source['model']))
    for f in bundle.files:
        if f.type not in ('report','strategy','resources','dns'):continue
        content=json.loads(f.raw)
        if f.type=='report':fields['model'].append(('диагностика',content['model']))
        else:
            context=content if f.type=='strategy' else content['context']
            label={'strategy':'стратегия','resources':'ресурсы','dns':'DNS'}[f.type]
            for name in ('operator','purpose'):fields[name].append((label,context[name]))
    return '\n'.join(label+': '+_preview_field(fields[name]) for name,label in
                     (('model','Модель'),('operator','Оператор'),('purpose','Сервисы / назначение')))

def share_body(bundle:ShareBundle)->str:
    value={'type':'nfqws2_submission','schema_version':1,'submission_id':bundle.submission_id,
           'categories':(['diagnostics'] if any(f.type in ('report','dpi') for f in bundle.files) else [])+(['strategies'] if any(f.type in ('strategy','resources','dns') for f in bundle.files) else [])}
    source=json.loads(bundle.source_json) if bundle.source_json is not None else None
    if source is not None:value['source']=source
    return _share_preview(bundle,source)+'\n\n'+json.dumps(value,ensure_ascii=False,indent=2)+'\n'

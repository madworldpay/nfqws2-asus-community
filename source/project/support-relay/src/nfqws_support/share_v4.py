"""Selected resource bytes/DNS cards; validation never executes submitted data."""
import base64,binascii,datetime,hmac,ipaddress,json,re
from hashlib import sha256
from urllib.parse import urlsplit,parse_qsl
from .share import ShareBundle,_schema,_decode
from .bundle import BundleFile
from .validation import InvalidReport,validate_report
from .dpi_validation import validate_dpi_report

_envelope=_schema('share-v4.schema.json')
_strategy=_schema('strategy-v2.schema.json')
_resources=_schema('resources.schema.json')
_dns=_schema('dns-share.schema.json')
_saved=_schema('dpi-saved.schema.json')
_LIMITS={'report':1048576,'dpi':262144,'strategy':65536,'resources':786432,'dns':131072}
_ORDER={k:i for i,k in enumerate(_LIMITS)}

def _canonical(encoded,limit):
    data=base64.b64decode(encoded,validate=True)
    if len(data)>limit or base64.b64encode(data).decode('ascii')!=encoded:raise InvalidReport()
    return data

def _domain(value):
    name=value[:-1] if value.endswith('.') else value
    try:ipaddress.ip_address(name)
    except ValueError:pass
    else:raise InvalidReport()
    if len(name)>253 or not re.fullmatch(r'[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*',name):raise InvalidReport()
    return name.lower()

def _private_dns_parameter(key):
    normalized=re.sub('[^a-z0-9]','',key.lower())
    return normalized in ('key','auth','code','sig','signature') or re.search('token|secret|password|passwd|credential|apikey|authorization|authentication',normalized) is not None

def _dns_profile(profile):
    if not profile['upstreams'] and not profile['records']:raise InvalidReport()
    ids=set();assignments=0
    for s in profile['upstreams']:
        if s['id'] in ids or re.search(r'[\x00-\x1f\x7f]',s['label']):raise InvalidReport()
        ids.add(s['id'])
        try:ipaddress.ip_address(s['address'])
        except ValueError:_domain(s['address'])
        for ip in s['bootstrap']:ipaddress.ip_address(ip)
        secure=s['protocol'] in ('dot','doh')
        if secure:_domain(s['tls_name'])
        elif s['tls_name']:raise InvalidReport()
        if s['protocol']=='doh':
            url=s['url'];url.encode('ascii','strict');parts=urlsplit(url)
            if re.search(r'''[\x00-\x20\x7f"'\\#]''',url) or parts.scheme!='https' or not parts.hostname or parts.username is not None or parts.password is not None or parts.fragment or (parts.port or 443)!=s['port']:raise InvalidReport()
            if any(_private_dns_parameter(k) for k,_ in parse_qsl(parts.query,keep_blank_values=True)):raise InvalidReport()
            try:ipaddress.ip_address(parts.hostname)
            except ValueError:_domain(parts.hostname)
        elif s['url']:raise InvalidReport()
        for d in s['domains']:_domain(d['name'])
        assignments+=len(s['domains'])
    if assignments>256:raise InvalidReport()
    seen=set()
    for r in profile['records']:
        key=(_domain(r['name']),r['include_subdomains'])
        if key in seen:raise InvalidReport()
        seen.add(key)
        for ip in r['addresses']:ipaddress.ip_address(ip)
        if r['checked_at'] is not None:datetime.date.fromisoformat(r['checked_at'])

def _context(value):
    if not value['operator'].strip() or not value['purpose'].strip():raise InvalidReport()

def _check_resources(value):
    if not _resources.is_valid(value):raise InvalidReport()
    _context(value['context']);ids=set();aliases={};total=0
    for f in value['files']:
        if f['name'] in ('.','..') or f['id'] in ids:raise InvalidReport()
        ids.add(f['id']);data=_canonical(f['data_base64'],262144)
        if len(data)!=f['byte_length'] or not hmac.compare_digest(sha256(data).hexdigest(),f['sha256']):raise InvalidReport()
        if f['encoding']=='utf8':
            if f['kind']=='blobs' or b'\0' in data:raise InvalidReport()
            data.decode('utf-8','strict')
        total+=len(data)
        if total>524288:raise InvalidReport()
        for alias in f['aliases']:
            if alias in aliases:raise InvalidReport()
            aliases[alias]=f['id']
    refs=set();missing=False
    for r in value['audit']['references']:
        if r['id'] in refs or len(set(r['aliases']))!=len(r['aliases']):raise InvalidReport()
        refs.add(r['id'])
        if r['state']=='included':
            if r['resource_id'] not in ids or any(aliases.get(a)!=r['resource_id'] for a in r['aliases']):raise InvalidReport()
        else:
            if r['resource_id'] is not None:raise InvalidReport()
            missing=True
    incomplete=missing or bool(value['audit']['unresolved'])
    if value['audit']['complete']!= (not incomplete):raise InvalidReport()
    if value['audit']['scope']=='files_only' and (value['audit']['references'] or value['audit']['unresolved']):raise InvalidReport()

def _cross(documents):
    resources=documents.get('resources',{});strategy=documents.get('strategy',{})
    aliases={a:f['id'] for f in resources.get('files',[]) for a in f['aliases']};deps={}
    for d in strategy.get('dependencies',[]):
        prefix={'file':'RESOURCE','blob':'BLOB','network':'NETWORK','variable':'VARIABLE'}[d['kind']]
        if d['id'] in deps or not d['id'].startswith(prefix+'_') or d['included']!=(d['id'] in aliases):raise InvalidReport()
        deps[d['id']]=d
    if any(a not in deps or deps[a]['kind'] not in ('file','blob') for a in aliases):raise InvalidReport()
    if any(a not in deps for r in resources.get('audit',{}).get('references',[]) for a in r['aliases']):raise InvalidReport()

def validate_v4(raw,value,submission_id):
    try:
        if not 0<len(raw)<=4194304 or not _envelope.is_valid(value) or value['submission_id']!=submission_id:raise InvalidReport()
        files=[];manifest=[];documents={};last=-1
        for f in value['files']:
            kind=f['type'];at=_ORDER[kind]
            if at<=last or not re.fullmatch(r'NFQWS2_[A-Za-z0-9_-]+_[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{2}-[0-9]{2}-[0-9]{2}Z\.json',f['filename']):raise InvalidReport()
            data=_canonical(f['data_base64'],_LIMITS[kind]);digest=sha256(data).hexdigest()
            if not data or len(data)!=f['byte_length'] or not hmac.compare_digest(digest,f['sha256']):raise InvalidReport()
            if kind=='report':validate_report(data,f['filename'])
            else:
                if not f['filename'].startswith('NFQWS2_'+kind.upper()+'_'):raise InvalidReport()
                content=_decode(data);documents[kind]=content
                if kind=='strategy':
                    if not _strategy.is_valid(content) or not content['purpose'].strip() or not content['operator'].strip():raise InvalidReport()
                elif kind=='resources':_check_resources(content)
                elif kind=='dns':
                    if not _dns.is_valid(content):raise InvalidReport()
                    _context(content['context']);seen=set()
                    for s in content['sources']:
                        if s['id']!=s['origin'] or s['id'] in seen or s['complete']!=(not s['warnings']):raise InvalidReport()
                        seen.add(s['id']);_dns_profile(s['profile'])
                elif isinstance(content,dict) and content.get('type')=='nfqws2_dpi_saved':
                    if not _saved.is_valid(content):raise InvalidReport()
                else:validate_dpi_report(data,f['filename'])
            files.append(BundleFile(kind,f['filename'],data,digest));last=at
            manifest.append({'type':kind,'filename':f['filename'],'byte_length':len(data),'sha256':digest})
        _cross(documents)
        source=value.get('source');source_json=json.dumps(source,sort_keys=True,separators=(',',':')) if source is not None else None
        digest=sha256(b'NFQWS2-SHARE\0v4\0'+json.dumps({'files':manifest,'source':source},sort_keys=True,separators=(',',':')).encode('ascii')).hexdigest()
        return ShareBundle(tuple(files),digest,submission_id,source_json,4)
    except (ValueError,TypeError,KeyError,UnicodeError,RecursionError,OverflowError,binascii.Error):raise InvalidReport() from None

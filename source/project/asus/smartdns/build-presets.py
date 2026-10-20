#!/usr/bin/env python3
"""Generate editable choices from pinned DPI profiles; never use system DNS."""
from pathlib import Path
import hashlib,ipaddress,json
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parents[2]
def generate():
    source=ROOT/'support/dpi-catalog.json';raw=source.read_bytes();catalog=json.loads(raw);rows=catalog['profile']['dns'];presets=[]
    for row in rows:
        if row['protocol'] not in ['dot','doh_wire']:continue
        bootstrap=[x['endpoint'] for x in rows if x['provider']==row['provider'] and x['protocol']=='udp']
        for ip in bootstrap:ipaddress.ip_address(ip)
        if not bootstrap:continue
        protocol='doh' if row['protocol']=='doh_wire' else 'dot';url=row['endpoint'] if protocol=='doh' else '';name=urlsplit(url).hostname if url else row['endpoint']
        presets.append({'id':row['id'],'label':row['provider']+' — '+('DoH' if protocol=='doh' else 'DoT'),'protocol':protocol,'address':name,'port':443 if protocol=='doh' else 853,'tls_name':name,'url':url,'bootstrap':bootstrap})
    native_raw=(ROOT/'support/dpi-native-defaults.json').read_bytes()
    native=json.loads(native_raw)
    if native['commit'] != catalog['commit']:
        raise ValueError('DPI catalogs must describe the same pinned version')
    config=native['config']
    hints_raw=(ROOT/'support/smartdns-preset-bootstrap.json').read_bytes()
    hints=json.loads(hints_raw)
    udp={}
    for endpoint,provider,protocol in config['DNS_AVAILABILITY_SERVERS']:
        if protocol=='udp':
            ipaddress.ip_address(endpoint)
            udp.setdefault(provider,[]).append(endpoint)
    for endpoint,provider in config['DNS_UDP_SERVERS']:
        if provider not in udp:udp[provider]=[endpoint]
    seen={(p['protocol'],p['url'] or p['address']) for p in presets}
    extra=[]
    for endpoint,provider,protocol in config['DNS_AVAILABILITY_SERVERS']:
        if protocol not in ['dot','doh_wire']:continue
        protocol='doh' if protocol=='doh_wire' else 'dot'
        if (protocol,endpoint) in seen:continue
        url=endpoint if protocol=='doh' else ''
        parsed=urlsplit(url) if url else None
        name=parsed.hostname if parsed else endpoint
        if not name or (parsed and (parsed.scheme!='https' or parsed.username or parsed.password or parsed.query or parsed.fragment)):
            raise ValueError('Public presets cannot contain credentials or query strings')
        try:
            ipaddress.ip_address(name)
            bootstrap=[name]
            tls_name=hints['ip_tls_names'][name]
        except ValueError:
            tls_name=name
            bootstrap=hints['hosts'].get(name,{}).get('addresses')
            if not bootstrap:
                alias=hints['provider_aliases'].get(provider,provider)
                bootstrap=udp.get(alias)
        if not bootstrap:
            raise ValueError('Missing explicit bootstrap for '+endpoint)
        bootstrap=list(dict.fromkeys(bootstrap))
        for ip in bootstrap:
            if not ipaddress.ip_address(ip).is_global:raise ValueError('Nonpublic bootstrap')
        identity=protocol+'\0'+endpoint
        extra.append({'id':'dpi-'+protocol+'-'+hashlib.sha256(identity.encode()).hexdigest()[:12],
            'label':provider+' — '+protocol.upper()+' · '+name,
            'protocol':protocol,'address':name,'port':(parsed.port or 443) if parsed else 853,
            'tls_name':tls_name,'url':url,'bootstrap':bootstrap})
        seen.add((protocol,endpoint))
    presets.extend(sorted(extra,key=lambda p:p['label'].casefold()))
    # Paths can distinguish two public DoH services at the same hostname.
    labels={}
    for p in presets:labels[p['label']]=labels.get(p['label'],0)+1
    for p in presets:
        if labels[p['label']]>1:p['label']+=' '+urlsplit(p['url']).path
    return {'schema_version':1,'source':'DPI Detector '+catalog['version'],
        'source_commit':catalog['commit'],'source_sha256':hashlib.sha256(raw).hexdigest(),
        'native_source_sha256':hashlib.sha256(native_raw).hexdigest(),
        'bootstrap_source_sha256':hashlib.sha256(hints_raw).hexdigest(),'presets':presets}
if __name__=='__main__':
    (ROOT/'webui/web/src/api/smartDnsPresets.json').write_text(json.dumps(generate(),ensure_ascii=False,indent=2)+'\n')

"""Offline compiler experiment, never called by the HTTP API or package runtime.

Inputs are trusted already-installed parsed configurations. This does not apply
firewall marks, migrate settings, import dependencies or start any process.
"""
import re


def blocks(tokens):
    result=[]
    for token in tokens:
        if token=='--new' or token.startswith('--new='):
            result.append([token])
        else:
            if not result:result.append([])
            result[-1].append(token)
    return [b for b in result if any(not x.startswith('--new') for x in b)]


def _tokens(text):
    # Exactly the whitespace splitting used by native args.sh, never shell eval.
    tokens='\n'.join(line for line in text.splitlines() if not line.lstrip().startswith('#')).split()
    for token in tokens:
        if not token.startswith('--'):raise ValueError('unsupported_argument')
        key=token[2:].split('=',1)[0]
        if any(reserved.startswith(key) for reserved in ['daemon','pidfile','qnum','user','uid','dry-run','version','help','intercept','chdir','debug']):
            raise ValueError('reserved_argument')
        if any(full.startswith(key) and key!=full for full in ['filter-mark','new','name','blob','lua-init']):
            raise ValueError('abbreviated_structural_option')
        if key=='name':raise ValueError('existing_profile_name')
        if key=='filter-mark':raise ValueError('existing_mark')
        if key=='lua-init' and not token.startswith('--lua-init=@/'):
            raise ValueError('inline_lua_not_supported')
    return tokens


def _strategy(config):
    segments=[]
    def add(text):
        if text.strip():segments.extend(blocks(_tokens(text)))
    add(config.get('NFQWS_ARGS_CUSTOM',''))
    add(config.get('NFQWS_ARGS_UDP',''))
    for key in ['NFQWS_ARGS_QUIC','NFQWS_ARGS']:
        text=config.get(key,'')
        if not text.strip():continue
        ipset=config.get('NFQWS_ARGS_IPSET','')
        if ipset.strip():add(text+' '+ipset+' --ipset-ip=0.0.0.0')
        add(text+' '+config.get('NFQWS_EXTRA_ARGS',''))
    return segments


def compile_probe(profiles, fallback):
    if not profiles or len(profiles)>8:raise ValueError('probe_profile_limit')
    global_options=[];global_defs={};segments=[]
    for index,(name,config) in enumerate([*profiles,('fallback',fallback)]):
        if not re.fullmatch('[a-z][a-z0-9-]{0,24}',name):raise ValueError('invalid_name')
        common=_tokens(config.get('NFQWS_BASE_ARGS',''))
        source=_strategy(config)
        for options in [common,*source]:
            for token in options:
                if token.startswith('--lua-init='):
                    if token not in global_options:global_options.append(token)
                elif token.startswith('--blob='):
                    key=token.split('=',1)[1].split(':',1)[0]
                    if not key or ':' not in token:raise ValueError('invalid_blob')
                    old=global_defs.get('blob:'+key)
                    if old is not None and old!=token:raise ValueError('conflicting_global_blob')
                    global_defs['blob:'+key]=token
                    if token not in global_options:global_options.append(token)
                elif options is common:
                    key=token.split('=',1)[0]
                    old=global_defs.get(key)
                    if old is not None and old!=token:raise ValueError('conflicting_global_option')
                    global_defs[key]=token
                    if token not in global_options:global_options.append(token)
        for number,segment in enumerate(source,1):
            parts=[f"{'--name' if not segments else '--new'}={name}-{number}"]
            if index<len(profiles):
                mark=1<<(16+index)
                parts.append(f'--filter-mark=0x{mark:08x}/0x{mark:08x}')
            parts.extend(x for x in segment if not (x=='--new' or x.startswith('--new=') or x.startswith('--lua-init=') or x.startswith('--blob=')))
            segments.extend(parts)
    if not any(x.startswith('--fastpath-workaround=') for x in global_options):
        global_options.insert(0,'--fastpath-workaround=auto')
    return global_options+segments

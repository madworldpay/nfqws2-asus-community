"""Extract complete, replayable action chains from verified package inputs."""
import base64
import hashlib
import json
import re
import shlex


PROTOCOLS = {
    'http': ('--filter-tcp', '80', 'http_req'),
    'tls': ('--filter-tcp', '443', 'tls_client_hello'),
    'quic': ('--filter-udp', '443', 'quic_initial'),
}
BLOCKS = ('NFQWS_ARGS', 'NFQWS_ARGS_QUIC', 'NFQWS_ARGS_UDP', 'NFQWS_ARGS_CUSTOM')
STOCK_LUA = ('zapret-lib.lua', 'zapret-antidpi.lua', 'zapret-auto.lua')
SPLIT = {'multisplit', 'multidisorder'}
FAKE_SPLIT = {'fakedsplit', 'fakeddisorder'}
HTTP = {'http_hostcase', 'http_methodeol', 'http_domcase'}
POSITIONS = {
    '2', '1,midsld', 'midsld', 'host+1', 'sniext+1',
    '1,sniext+1,host+1,midsld-2,midsld,midsld+2,endhost-1',
    '1', '1,27', '1,host+2,midsld+2,endsld-2', '2,sniext+1', '1,sniext-2',
    '100,midsld-2,endhost-4', 'sld+1', '2,midsld-2', '1,host+1,midsld',
    '3', 'sniext+1,midsld', '1,method+2,host+1,sld+1', 'host+1,method+2',
    '1,host+2,sld+2,sld+5,sniext+1,sniext+2,endhost-2',
}
OVERLAPS = {1, 2, 4, 211, 417, 480, 568, 652, 664, 679, 680, 681, 700, 740}
FOOLING = {
    'seq': {'tcp_seq': '10000'}, 'seq1000': {'tcp_seq': '1000'},
    'seq2': {'tcp_seq': '2'}, 'seqnegative': {'tcp_seq': '-10000'},
    'seqlarge': {'tcp_seq': '10000000'}, 'ack': {'tcp_ack': '-66000'},
    'badsum': {'badsum': ''}, 'md5': {'tcp_md5': ''},
    'ts': {'tcp_ts': '-600000', 'tcp_ts_up': ''},
    'ts1500': {'tcp_ts': '-1500', 'tcp_ts_up': ''},
    'ts5000': {'tcp_ts': '-5000', 'tcp_ts_up': ''},
    'autottl': {'ip_autottl': '-2,3-20', 'ip6_autottl': '-2,3-20'},
}
TLS_MODS = {
    'rnd,dupsid': 'random', 'rnd,dupsid,sni=www.google.com': 'google',
    'rnd,dupsid,sni=ozon.ru': 'ozon', 'rnd,dupsid,sni=ya.ru': 'ya',
    'rnd,dupsid,sni=rzd.ru': 'rzd',
}
HOSTS = {'www.google.com', 'mail.ru', 'ozon.ru', 'ya.ru'}
ZERO64 = '0x' + '00' * 64


def digest(data):
    return hashlib.sha256(data).hexdigest()


def action(token):
    if not re.fullmatch(r'--lua-desync=[A-Za-z0-9_.,:+<>=!-]+', token):
        raise ValueError('nonliteral action')
    name, *parts = token.removeprefix('--lua-desync=').split(':')
    args = {key: value for key, _, value in (part.partition('=') for part in parts)}
    if len(parts) != len(args):
        raise ValueError('ambiguous action parameters')
    return name, args


def fooling(args, protocol):
    if not args:
        return {}
    for name, values in FOOLING.items():
        if values == args and (protocol != 'quic' or name == 'autottl'):
            return {'fooling': name}
    raise ValueError('unrepresented fooling')


def repeats(args):
    value = args.pop('repeats', '1')
    if value not in '1 2 3 4 5 6'.split():
        raise ValueError('unrepresented repeat count')
    return int(value)


def fake(protocol, args, blobs):
    blob = args.pop('blob')
    if blob == ZERO64 and protocol != 'quic':
        payload = {'payload': 'zero64'}
    elif blob == 'fake_default_' + protocol:
        payload = {}
    else:
        sample = blobs[blob]
        if protocol == 'http' or not sample.startswith(protocol+'_'):
            raise ValueError('wrong payload format')
        payload = {'payload': sample}
    modifier = args.pop('tls_mod', None)
    if modifier is not None:
        if protocol != 'tls':
            raise ValueError('wrong modifier protocol')
        payload['tls_mod'] = TLS_MODS[modifier]
    return payload | {'repeats': repeats(args)} | fooling(args, protocol)


def component(protocol, steps, blobs):
    """Return the typed form only when every nondefault action argument fits."""
    if not 1 <= len(steps) <= 2:
        return None
    try:
        method, args = action(steps[-1])
        prefix = {}
        pattern = 'fake_default_' + protocol
        if len(steps) == 2:
            first, first_args = action(steps[0])
            if first == 'tls_client_hello_clone' and protocol == 'tls' and method == 'fake':
                if first_args != {'blob': pattern, 'fallback': pattern} or args.pop('blob', None) != pattern:
                    return None
                return {'method': first, 'repeats': repeats(args)} | fooling(args, protocol)
            if first != 'fake' or protocol == 'quic' or method not in SPLIT | HTTP:
                return None
            pattern = first_args.get('blob')
            prefix = {'fake': True} | fake(protocol, first_args, blobs)
        base = {'method': method}
        if method == 'fake':
            return base | fake(protocol, args, blobs)
        if method in SPLIT | FAKE_SPLIT and protocol != 'quic':
            if method in FAKE_SPLIT and protocol != 'tls':
                return None
            position = args.pop('pos')
            if position not in POSITIONS or ('method' in position and protocol != 'http') or (
                    'sniext' in position and protocol != 'tls'):
                return None
            base['pos'] = position
            if 'seqovl' in args:
                overlap = args.pop('seqovl')
                if method not in SPLIT or overlap not in {str(n) for n in OVERLAPS}:
                    return None
                operand = args.pop('seqovl_pattern')
                same_bytes = operand in blobs and pattern in blobs and blobs[operand] == blobs[pattern]
                if operand != pattern and not same_bytes:
                    return None
                base['seqovl'] = int(overlap)
            if method in FAKE_SPLIT:
                return base | fooling(args, protocol)
            return base | prefix if not args else None
        if method == 'hostfakesplit' and protocol != 'quic':
            host = args.pop('host')
            if host not in HOSTS or args.pop('midhost') != 'midsld':
                return None
            return base | {'host': host, 'repeats': repeats(args)} | fooling(args, protocol)
        if method in HTTP and protocol == 'http' and not args:
            return base | prefix
        if method == 'syndata' and protocol != 'quic' and not args:
            return base
        if method == 'send' and protocol == 'quic' and args == {'ipfrag': '', 'ipfrag_pos_udp': '8'}:
            return base
    except (KeyError, ValueError):
        return None
    return None


def words(value):
    tokens = shlex.split(value)
    if any(not token.startswith('--') or any(c.isspace() for c in token) for token in tokens):
        raise ValueError('nonliteral argument')
    return tokens


def config_values(config):
    if any(c in config for c in ('$', '`', '\0')):
        raise ValueError('nonliteral configuration')
    result = {}
    for token in shlex.split(config.replace('\\\n', ''), comments=True):
        key, separator, value = token.partition('=')
        if not separator or key in result or not re.fullmatch('[A-Z_][A-Z_0-9]*', key):
            raise ValueError('invalid assignment')
        result[key] = value
    return result


def bind_assets(rows):
    aliases = {}
    for row in rows:
        identity = (row['kind'], row['name'], row['sha256'])
        if 'data_base64' in row:
            raw = base64.b64decode(row['data_base64'], validate=True)
            if digest(raw) != identity[2] or len(raw) != row['byte_length']:
                raise ValueError('source resource mismatch')
        for alias in row['aliases']:
            if alias in aliases and aliases[alias] != identity:
                raise ValueError('ambiguous resource alias')
            aliases[alias] = identity
    return aliases


def blob_definition(token, definitions, resources, available_blobs):
    name, separator, source = token.removeprefix('--blob=').partition(':')
    if (not separator or name in definitions or name.startswith('fake_default_') or
            not re.fullmatch('[a-zA-Z_][a-zA-Z0-9_]*', name)):
        raise ValueError('ambiguous blob definition')
    kind, _, sha = resources.get(source.removeprefix('@'), ('', '', ''))
    definitions[name] = available_blobs.get(sha) if source.startswith('@') and kind == 'blobs' else None


def protocol_matches(options, protocol, collection, syn):
    flag, port, payload = PROTOCOLS[protocol]
    expected = {flag: port, '--filter-l7': protocol, '--payload': payload}
    if syn:
        expected = {flag: port, '--payload': 'all'}
    scope = dict(options)
    if len(scope) != len(options):
        return False
    extras = {'--filter-l3': 'ipv4', '--out-range': '-d8'}
    for key, value in extras.items():
        if key in scope and scope.pop(key) != value:
            return False
    if scope == expected:
        return True
    # A Magisk single-port TCP rule without a narrower predicate supplies only
    # an action example for the generator's narrower protocol/payload scope.
    return collection == 'magisk' and protocol != 'quic' and scope == {flag: port}


def port_is_queued(values, protocol):
    flag, port, _ = PROTOCOLS[protocol]
    key = 'UDP_PORTS' if flag == '--filter-udp' else 'TCP_PORTS'
    if key not in values:
        return True
    selected = False
    for raw in values[key].split(','):
        match = re.fullmatch(r'([0-9]{1,5})(?::([0-9]{1,5}))?', raw)
        if not match:
            return False
        first = int(match[1])
        last = int(match[2] or match[1])
        if not 1 <= first <= last <= 65535:
            return False
        selected |= first <= int(port) <= last
    return selected


def rule_components(values, resources, lua_hashes, available_blobs, collection):
    definitions = {}
    initializers = []
    try:
        for word in words(values.get('NFQWS_BASE_ARGS', '')):
            if word.startswith('--lua-init=@'):
                path = word.removeprefix('--lua-init=@')
                if path.startswith('/opt/etc/nfqws2/lua/'):
                    name = path.removeprefix('/opt/etc/nfqws2/lua/')
                    if not lua_hashes.get(name):
                        return
                else:
                    kind, name, sha = resources[path]
                    if kind != 'lua' or lua_hashes.get(name) != sha:
                        return
                initializers.append(name)
            elif word.startswith('--blob='):
                blob_definition(word, definitions, resources, available_blobs)
            elif word != '--ctrack-disable=0':
                return
        if initializers and tuple(initializers) not in (STOCK_LUA[:2], STOCK_LUA):
            return
        # These options affect the entire engine even in a different profile.
        # Portable candidates require declarations in the reviewed base above.
        global_options = {'--blob', '--lua-init', '--lua-exec'}
        for key in (*BLOCKS, 'NFQWS_EXTRA_ARGS', 'NFQWS_ARGS_IPSET'):
            if any(word.partition('=')[0] in global_options for word in words(values.get(key, ''))):
                return
        blobs = {name: ident for name, ident in definitions.items() if ident}
        for key in BLOCKS:
            if key in ('NFQWS_ARGS', 'NFQWS_ARGS_QUIC') and (
                    values.get('NFQWS_EXTRA_ARGS', '').strip() or values.get('NFQWS_ARGS_IPSET', '').strip()):
                continue
            groups = [[]]
            for word in words(values.get(key, '')):
                if word == '--new':
                    groups.append([])
                else:
                    groups[-1].append(word)
            for group in groups:
                options = []
                steps = []
                for word in group:
                    if word.startswith('--lua-desync='):
                        steps.append(word)
                    elif not word.startswith('--name='):
                        if steps:
                            break  # Profile options can change the scope of later actions.
                        flag, _, operand = word.partition('=')
                        options.append((flag, operand))
                else:
                    for protocol in PROTOCOLS:
                        if not port_is_queued(values, protocol) or not protocol_matches(
                                options, protocol, collection, steps == ['--lua-desync=syndata']):
                            continue
                        seed = component(protocol, steps, blobs)
                        if seed is not None:
                            yield protocol, seed
    except (KeyError, ValueError):
        return


def packed_records(files):
    catalog = json.loads(files['catalog.json'][0])
    additions = json.loads(files['collections.json'][0])
    assets = json.loads(files['resources.json'][0]) | additions['resources']
    templates = {}
    for group in ('presets', 'tcp', 'http80', 'udp', 'voice'):
        if group+'.json' in files:
            templates.update(json.loads(files[group+'.json'][0]))
    templates.update(additions['templates'])
    for collection, entries in (('magisk', catalog['entries']), ('avatar', additions['entries'])):
        for row in entries:
            if row.get('unavailable'):
                continue
            data = templates[row['id']]
            resources = [assets[key] | {'aliases': [f'RESOURCE_{i}']}
                         for i, key in enumerate(data['resources'], 1)]
            yield (collection, row, config_values(data['config']), bind_assets(resources))
    if 'zemidala-offline.json' in files:
        # public_payload verified the full roster and its ordered steps first.
        offline = json.loads(files['zemidala-offline.json'][0])
        for row in json.loads(files['zemidala-index.json'][0])['entries']:
            record = offline[row['id']]
            protocol = record['proto']
            flag, port, payload = PROTOCOLS[protocol]
            prefix = f'{flag}={port} --filter-l7={protocol} --payload={payload} '
            values = {'NFQWS_ARGS_CUSTOM': prefix + ' '.join(record['steps'])}
            resources = {}
            # Resolve the same reviewed stock fixture as the import reader.
            if any(re.search(r':(?:blob|pattern|seqovl_pattern)=tls_clienthello(?=:|$)', step) for step in record['steps']):
                values['NFQWS_BASE_ARGS'] = '--blob=tls_clienthello:@RESOURCE_1'
                resources = bind_assets([assets['9be6fbcee6bf3f6cd6274d99d8a4bf39'] | {'aliases': ['RESOURCE_1']}])
            yield ('zemidala', row, values, resources)


def signed_records(files, build_number):
    if not files:
        return
    root = 'profile-catalog/v1/'
    envelope = json.loads(files[root+'catalog.json'][0])
    catalog = json.loads(base64.b64decode(envelope['manifest'], validate=True))
    for row in catalog['profiles']:
        if build_number is not None and row['min_build'] > build_number:
            continue
        bundle_raw = files[root+'files/'+row['sha256']+'.json'][0]
        if len(bundle_raw) != row['size'] or digest(bundle_raw) != row['sha256']:
            raise ValueError('signed source document mismatch')
        documents = {}
        for file in json.loads(bundle_raw)['files']:
            if file['type'] not in ('strategy', 'resources'):
                continue
            raw = base64.b64decode(file['data_base64'], validate=True)
            if digest(raw) != file['sha256'] or len(raw) != file['byte_length'] or file['type'] in documents:
                raise ValueError('signed source attachment mismatch')
            documents[file['type']] = json.loads(raw)
        profile = documents.get('strategy')
        if profile is None:
            continue
        if profile['mode'] == 'blocks':
            values = profile['shared'] | {block['key']: block['value'] for block in profile['blocks']}
        elif profile['mode'] == 'config':
            values = config_values(profile['config'])
        else:
            continue
        resources = documents.get('resources', {})
        yield ('cloud', row, values, bind_assets(resources.get('files', []) + resources.get('package_files', [])))


def compile_seeds(files, signed, lua_hashes, available_blobs, build_number=None):
    seeds = {protocol: {} for protocol in PROTOCOLS}
    for records in (packed_records(files), signed_records(signed, build_number)):
        for collection, row, values, resources in records:
            for protocol, seed in rule_components(values, resources, lua_hashes, available_blobs, collection):
                key = json.dumps(seed, sort_keys=True)
                match = seeds[protocol].setdefault(key, {'component': seed, 'sources': {}})
                source = {'id': row['id'], 'collection': collection, 'attribution': row['attribution']}
                match['sources'][collection, row['id']] = source

    result = {'schema_version': 1}
    for protocol, entries in seeds.items():
        result[protocol] = [
            {'component': entry['component'], 'sources': [entry['sources'][key] for key in sorted(entry['sources'])]}
            for _, entry in sorted(entries.items())
        ]
    return result

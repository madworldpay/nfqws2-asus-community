"""Compile the pinned Zapret2 Android data library for the ASUS panel, offline."""
import argparse
import base64
import collections
import gzip
import hashlib
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import quote
from zipfile import ZipFile


ZIP_SHA = 'd18cce3864ff72fd19117e85833bd4d8f5b93f19d5cb62006cc44a8522d862ed'
PROJECT = Path(__file__).resolve().parents[1]
REPO = 'https://git2.zapret.moe/zapretdiscordyoutube/magisk-zapret2'
COLLECTION = 'zapretdiscordyoutube/magisk-zapret2'
COMMIT = '7a05a2267df82dfa765cc7ff68cefd57fb45086a'
GROUPS = ('presets', 'http80', 'tcp', 'udp', 'voice')
STOCK = ('zapret-lib.lua', 'zapret-antidpi.lua', 'zapret-auto.lua')
BUILTINS = {'fake_default_http', 'fake_default_tls', 'fake_default_quic'}
EXTRA = {
    'custom_funcs.lua': ('tls_multisplit_sni', 'discord_urgent_sni', 'tls_split_gentle',
                         'tls_disorder_gentle', 'http_multidisorder', 'http_host_bytesplit',
                         'http_seqovl_host', 'http_hostmod', 'http_header_shuffle', 'http_methodeol_safe'),
    'zapret-multishake.lua': ('hostfakesplit_multi',),
}
STOCK_METHODS = {'pass', 'fake', 'send', 'syndata', 'multisplit', 'multidisorder',
                 'multidisorder_legacy', 'hostfakesplit', 'fakedsplit', 'fakeddisorder',
                 'udplen', 'pktmod', 'http_hostcase', 'http_methodeol', 'wssize', 'dht_dn', 'drop'}
LIST_OPTIONS = {'--ipset', '--ipset-exclude', '--hostlist', '--hostlist-exclude'}
RULE_OPTIONS = LIST_OPTIONS | {'--name', '--new', '--filter-tcp', '--filter-udp', '--payload',
                              '--out-range', '--filter-l7', '--hostlist-domains', '--lua-desync'}
RESOURCE_ARGS = {'blob', 'seqovl_pattern', 'pattern', 'fallback'}
NEW_POSITIONS = ('sld+1', '2,midsld-2', '1,host+1,midsld', '3', 'sniext+1,midsld',
                 '1,method+2,host+1,sld+1', 'host+1,method+2',
                 '1,host+2,sld+2,sld+5,sniext+1,sniext+2,endhost-2')
POSITIONS = set(NEW_POSITIONS) | {'1', '2', 'host+1', '1,midsld', 'midsld', 'sniext+1', '2,sniext+1'}
OVERLAPS = {1, 2, 4, 211, 417, 480, 568, 652, 664, 679, 680, 681, 700, 740}
NATIVE_SAMPLES = {'tls14': ('tls_module_hello', 'tls_clienthello_14.bin'),
                  'tls_deepseek': ('tls_module_deepseek', 'tls_clienthello_chat_deepseek_com.bin'),
                  'quic2': ('quic_module_short', 'quic_2.bin'), 'quic4': ('quic_module_alt', 'quic_4.bin'),
                  'fake_dbankcloud': ('quic_module_dbank', 'quic_initial_dbankcloud_ru.bin')}
STOCK_SAMPLES = {'tls_google':'tls_clienthello.bin','tls_iana':'tls_clienthello_iana_org.bin',
                 'tls_gosuslugi':'tls_clienthello_gosuslugi_ru.bin','tls_sberbank':'tls_clienthello_sberbank_ru.bin',
                 'tls_vk':'tls_clienthello_vk_com.bin','tls_vk_kyber':'tls_clienthello_vk_com_kyber.bin',
                 'quic_google':'quic_initial.bin','quic_vk':'quic_initial_vk_com.bin',
                 'quic_facebook':'quic_initial_facebook_com.bin','quic_rutracker':'quic_initial_rutracker_org.bin',
                 'quic_googlevideo':'quic_initial_googlevideo.bin'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def source_link(path, line=None):
    link = REPO + '/src/commit/' + COMMIT + '/' + quote(path, safe='/')
    return link + (f'#L{line}' if line is not None else '')


def attribution(author):
    author = author.strip()
    if author.casefold() in {'', '...', 'builtin', 'custom', 'community', 'я :)'}:
        return COLLECTION
    if author == 'https://github.com/Flowseal/zapret-discord-youtube/issues/2361':
        return 'Flowseal/zapret-discord-youtube'
    return author


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')


def catalog_entries(raw):
    for match in re.finditer(rb'^\[([^\]\r\n]+)\][ \t]*\r?\n(.*?)(?=^\[|\Z)', raw, re.M | re.S):
        body = match.group(2).decode('utf-8-sig').splitlines()
        meta = dict(line.split(' = ', 1) for line in body if ' = ' in line and not line.startswith('--'))
        yield (match.group(1).decode(), meta, [line.strip() for line in body if line.startswith('--')],
               match.group(0), raw.count(b'\n', 0, match.start()) + 1)


def ports(rules, protocol):
    spans = []
    for line in rules:
        if not line.startswith('--filter-' + protocol + '='):
            continue
        for spec in line.partition('=')[2].split(','):
            if spec == '*':
                spans.append((1, 65535))
                continue
            first, sep, last = spec.partition('-')
            left, right = int(first), int(last if sep else first)
            if not 1 <= left <= right <= 65535:
                raise ValueError('invalid port ' + spec)
            spans.append((left, right))
    merged = []
    for left, right in sorted(spans):
        if merged and left <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], right))
        else:
            merged.append((left, right))
    return ','.join(str(a) if a == b else f'{a}:{b}' for a, b in merged)


class Library:
    def __init__(self, archive, out, chunks):
        self.archive, self.out, self.chunks = archive, out, chunks
        self.rows, self.assets, self.templates = [], {}, collections.defaultdict(dict)
        self.paths, self.lua, self.definitions, self.inventory = {}, {}, {}, []
        self.examples = {p: {} for p in ('http','tls','quic')}
        self.samples, self.sample_ids = {}, {}

    def asset(self, kind, name, raw, *, packaged=False):
        digest = sha(raw)
        key = sha((kind + '/' + name).encode())[:32]
        row = {'kind': kind, 'name': name, 'sha256': digest, 'byte_length': len(raw)}
        if not packaged:
            row['encoding'] = 'base64' if kind == 'blobs' or name.endswith('.gz') else 'utf8'
            row['data_base64'] = base64.b64encode(raw).decode('ascii')
        if key in self.assets and self.assets[key] != row:
            raise ValueError('resource collision ' + name)
        self.assets[key] = row
        return key

    def collect_assets(self):
        for path in sorted(self.archive.namelist()):
            match = re.fullmatch(r'zapret2/(lists|bin)/([a-zA-Z0-9_.-]+)', path)
            if not match:
                continue
            directory, name = match.groups()
            if directory == 'bin' and not name.endswith('.bin'):
                continue
            raw = self.archive.read(path)
            original_digest = sha(raw)
            if directory == 'bin':
                ids = [self.asset('blobs', name, raw)]
            elif len(raw) > 262144:
                # Split on complete records before compression. nfqws2 unions repeated
                # hostlist options inside the same filter, preserving exact entries.
                ids, part = [], bytearray()
                for line in raw.splitlines(keepends=True):
                    if part and len(part) + len(line) > 420000:
                        ids.append(self.chunk(part))
                        part.clear()
                    part.extend(line)
                if part:
                    ids.append(self.chunk(part))
            else:
                name = 'z2-' + name
                if len(raw) >= 8192:
                    raw, name = gzip.compress(raw, mtime=0), name + '.gz'
                ids = [self.asset('lists', name, raw)]
            self.paths[path[8:]] = ids
            self.inventory.append({'id': sha(path.encode())[:24], 'title': match[2], 'group': 'assets',
                                   'kind': 'lists' if directory == 'lists' else 'blobs', 'sha256': original_digest,
                                   'parts': ids, 'resident': all('data_base64' not in self.assets[k] for k in ids),
                                   'source_url': source_link(path)})
        for name in STOCK:
            raw = self.archive.read('zapret2/lua/' + name)
            self.lua[name] = self.asset('lua', name, raw, packaged=True)
        for name, functions in EXTRA.items():
            raw = self.archive.read('zapret2/lua/' + name).decode('utf-8-sig')
            for function in functions:
                # These explicitly reviewed top-level declarations close at column 1.
                found = re.findall(r'^function ' + function + r'\(.*?^end[ \t]*\r?$', raw, re.S | re.M)
                # The exact pinned module redefines this name. Lua uses the last body.
                if len(found) != (2 if function == 'http_methodeol_safe' else 1):
                    raise ValueError('ambiguous Lua declaration ' + function)
                data = ('-- Zapret2 Magisk v2.3.10, ' + source_link('zapret2/lua/' + name) + '\n' + found[-1] + '\n').encode()
                self.lua[function] = self.asset('lua', 'z2-' + function + '.lua', data)
        for name in ('fakemultisplit', 'fakemultidisorder'):
            raw = self.archive.read('zapret2/lua/' + name + '.lua')
            self.lua[name] = self.asset('lua', 'z2-' + name + '.lua', raw)
        for name, key in self.lua.items():
            item = self.assets[key]
            supplier = next((file for file, names in EXTRA.items() if name in names), name + '.lua')
            url = REPO + '/releases/tag/v2.3.10' if name in STOCK else source_link('zapret2/lua/' + supplier)
            self.inventory.append({'id': sha(('lua/' + name).encode())[:24], 'title': item['name'],
                                   'group': 'assets', 'kind': 'lua', 'sha256': item['sha256'],
                                   'parts': [key], 'resident': 'data_base64' not in item, 'source_url': url})

    def chunk(self, data):
        raw = gzip.compress(data, mtime=0)
        if len(raw) > 262144:
            raise ValueError('compressed list exceeds native per-file limit')
        name = 'z2-pack-' + sha(raw) + '.list.gz'
        (self.chunks / name).write_bytes(raw)
        return self.asset('lists', name, raw, packaged=True)

    def native_samples(self):
        # The file called tls_clienthello_6.bin is actually an HTTP response.
        # Use the record bytes, deduplicate synonyms and reuse exact stock blobs.
        known = {sha((PROJECT/'asus/blobs/files'/name).read_bytes()):ident for ident,name in STOCK_SAMPLES.items()}
        preferred = {name:ident for ident,name in NATIVE_SAMPLES.values()}
        binary = [path for path in self.paths if path.startswith('bin/')]
        for path in sorted(binary, key=lambda p:(Path(p).name not in preferred, p)):
            name = Path(path).name
            key, = self.paths[path]
            raw = self.archive.read('zapret2/'+path)
            if raw[:2] == b'\x16\x03' and raw[5:6] == b'\x01' and len(raw) == 5 + int.from_bytes(raw[3:5],'big'):
                protocol = 'tls'
            elif len(raw)>=6 and raw[0]&0xf0==0xc0 and raw[1:5]==b'\0\0\0\1':
                protocol = 'quic'
            else:
                continue
            digest = sha(raw)
            if digest not in known:
                ident = preferred.get(name, protocol+'_module_'+digest[:12])
                known[digest] = ident
                self.samples[ident] = {'key':key, 'name':'z2-'+name}
            self.sample_ids[path] = known[digest]

    def learn(self, rules, entry_id, source_url, credit):
        """Collect typed examples from each filter. Imported programs never enter the picker."""
        block = []
        for line in [*rules, '--new']:
            if line != '--new':
                block.append(line)
                continue
            scopes = set()
            for option, protocol, port in (('--filter-tcp=', 'http', 80), ('--filter-tcp=', 'tls', 443),
                                           ('--filter-udp=', 'quic', 443)):
                for token in block:
                    if not token.startswith(option):
                        continue
                    for span in token[len(option):].split(','):
                        if span == '*':
                            scopes.add(protocol)
                        else:
                            ends = [int(x) for x in span.split('-')]
                            if ends[0] <= port <= ends[-1]:
                                scopes.add(protocol)
            previous = {}
            for token in block:
                if not token.startswith('--lua-desync='):
                    previous.clear()
                    continue
                method, *parts = token.partition('=')[2].split(':')
                args = {key: val for key, _, val in (part.partition('=') for part in parts)}
                if len(args) != len(parts):
                    previous.clear()
                    continue
                for protocol in scopes:
                    c = self.example(protocol, method, args)
                    prefix = previous.pop(protocol, None)
                    if c is None:
                        continue
                    candidates = [c]
                    if c['method'] == 'fake':
                        previous[protocol] = c
                    elif prefix and c['method'] in ('multisplit', 'multidisorder'):
                        candidates.append({**prefix, **c, 'fake':True})
                    for candidate in candidates:
                        key = json.dumps(candidate, sort_keys=True)
                        item = self.examples[protocol].setdefault(key, {'component':candidate,'example':entry_id,
                                                                       'source_url':source_url,'attribution':credit,'occurrences':0})
                        item['occurrences'] += 1
            block = []

    def example(self, protocol, method, args):
        if method in {'multisplit','multidisorder'} and protocol != 'quic':
            pos = args.get('pos')
            if pos not in POSITIONS or ('method' in pos and protocol != 'http') or ('sniext' in pos and protocol != 'tls'):
                return None
            c = {'method':method,'pos':pos}
            overlap = args.get('seqovl')
            if overlap and overlap.isdecimal() and int(overlap) in OVERLAPS:
                c['seqovl'] = int(overlap)
            return c
        if method == 'fake':
            blob = args.get('blob', 'fake_default_' + protocol)
            repeats = args.get('repeats','1')
            if not repeats.isdecimal() or not 1 <= int(repeats) <= 6:
                return None
            c = {'method':'fake','repeats':int(repeats)}
            path = self.definitions.get(blob, '').removeprefix('@')
            if path in self.sample_ids:
                payload = self.sample_ids[path]
                if not payload.startswith(protocol + '_'):
                    return None
                c['payload'] = payload
            elif blob == 'zero64':
                c['payload'] = 'zero64'
            elif blob != 'fake_default_' + protocol:
                return None
            if args.get('ip_autottl') == args.get('ip6_autottl') == '-2,3-20':
                c['fooling'] = 'autottl'
            return c
        return None

    def add(self, group, title, raw, rules, *, source_url, source_id, author='', updated_at=None, declared=()):
        # Published source identifiers also bind private browser notes. Keep the
        # original identifier when a display name or a source filename changes.
        entry_id = sha((group + '/' + source_id).encode())[:24]
        methods, tokens, unsupported, adapted = set(), [], set(), []
        # Some fragment metadata lists Android app categories, not blob names.
        # A literal command operand always has to resolve.
        names = set(declared) & self.definitions.keys()
        for line in rules:
            option, sep, value = line.partition('=')
            if option not in RULE_OPTIONS or option != '--name' and re.search(r'[\s\x00-\x1f$;\x60|&\\"]', line):
                unsupported.add('nonliteral_argument')
            if option == '--lua-desync':
                method, *arguments = value.split(':')
                if group == 'presets' and method in {'tls_fake_flood', 'tls_aggressive'}:
                    adapted.append(method)
                    method, arguments = 'multisplit', ['pos=1,midsld']
                    line = '--lua-desync=multisplit:pos=1,midsld'
                methods.add(method)
                for item in arguments:
                    key, eq, arg = item.partition('=')
                    if eq and key in RESOURCE_ARGS and not arg.startswith('0x') and not arg.isnumeric():
                        names.add(arg)
            tokens.append(line)
        missing = sorted(unsupported | (methods - STOCK_METHODS - self.lua.keys()) | (names - self.definitions.keys() - BUILTINS))
        row = {'id': entry_id, 'title': title, 'group': group, 'sha256': sha(raw),
               'attribution': attribution(author), 'methods': sorted(methods), 'unavailable': missing, 'adapted': sorted(set(adapted)),
               'source_url': source_url}
        if updated_at:
            row['updated_at'] = updated_at
        self.rows.append(row)
        if missing:
            return
        resources = []

        def alias(key):
            if key not in resources:
                resources.append(key)
            return 'RESOURCE_' + str(resources.index(key) + 1)

        base = ['--lua-init=@' + alias(self.lua[n]) for n in STOCK]
        for name in self.lua:
            if name in methods:
                base.append('--lua-init=@' + alias(self.lua[name]))
        base.append('--ctrack-disable=0')
        for name, value in self.definitions.items():
            if name not in names:
                continue
            if value.startswith('@'):
                key, = self.paths[value[1:]]
                value = '@' + alias(key)
            base.append('--blob=' + name + ':' + value)
        output, labels = [], []
        for line in tokens:
            option, sep, value = line.partition('=')
            if option == '--name':
                labels.append(value)
                output.append('--name=z2-' + str(len(labels)))
            elif option in LIST_OPTIONS:
                for key in self.paths[value]:
                    output.append(option + '=' + alias(key))
            else:
                output.append(line)
        values = {'NFQWS_ARGS_CUSTOM': ' '.join(output), 'NFQWS_ARGS': '', 'NFQWS_ARGS_QUIC': '',
                  'NFQWS_ARGS_UDP': '', 'NFQWS_BASE_ARGS': ' '.join(base), 'NFQWS_EXTRA_ARGS': '',
                  'NFQWS_ARGS_IPSET': '', 'TCP_PORTS': ports(tokens, 'tcp'), 'UDP_PORTS': ports(tokens, 'udp')}
        config = ''.join(f'{key}="{value}"\n' for key, value in values.items())
        if len(resources) > 128 or sum(self.assets[k]['byte_length'] for k in resources if 'data_base64' in self.assets[k]) > 524288:
            raise ValueError('import bounds exceeded for ' + title)
        self.templates[group][entry_id] = {'config': config, 'resources': resources}
        if group != 'voice':
            self.learn(rules, entry_id, source_url, row['attribution'])

    def compile(self):
        self.collect_assets()
        self.native_samples()
        files = sorted(n for n in self.archive.namelist() if re.fullmatch(r'zapret2/presets/[^/]+\.txt', n))
        for path in files:
            raw = self.archive.read(path)
            lines = [l.strip() for l in raw.decode('utf-8-sig').splitlines() if l.strip().startswith('--')]
            pivot = next(i for i, line in enumerate(lines) if line.startswith('--name='))
            defs = dict(line[7:].split(':', 1) for line in lines[:pivot] if line.startswith('--blob='))
            if self.definitions and defs != self.definitions:
                raise ValueError('per-preset blob definitions differ')
            self.definitions = defs
            modified = re.search(rb'^# Modified: (\d{4}-\d{2}-\d{2})T', raw, re.M)
            updated_at = date.fromisoformat(modified[1].decode()).isoformat() if modified else None
            source_id = Path(path).stem
            self.add('presets', source_id, raw, lines[pivot:], source_url=source_link(path),
                     source_id=source_id, updated_at=updated_at)
        for group in GROUPS[1:]:
            raw = self.archive.read(f'zapret2/strategy-catalogs/{group}.txt')
            for ident, meta, commands, exact, lineno in catalog_entries(raw):
                if not commands:
                    raise ValueError('missing commands for ' + ident)
                # Fragment imports have an explicit scope. Voice follows the Discord
                # UDP filter and address list found in the source's complete presets.
                scope = {'http80':['--filter-tcp=80'], 'tcp':['--filter-tcp=443'],
                         'udp':['--filter-udp=443'], 'voice':['--filter-udp=443-65535','--ipset=lists/ipset-discord.txt']}[group]
                self.add(group, meta['name'], exact, scope + commands, source_id=ident,
                         source_url=source_link(f'zapret2/strategy-catalogs/{group}.txt', lineno),
                         author=meta.get('author', ''), declared=re.findall(r'[A-Za-z0-9_]+', meta.get('blobs', '')))
        self.rows.sort(key=lambda row: (GROUPS.index(row['group']), row['title'].casefold(), row['id']))
        if len({r['id'] for r in self.rows}) != len(self.rows):
            raise ValueError('duplicate catalog ID')
        archive_date = date(*self.archive.getinfo('module.prop').date_time[:3]).isoformat()
        save(self.out/'catalog.json', {'version':'2.3.10','source_sha256':ZIP_SHA,'entries':self.rows,
                                      'attribution':COLLECTION, 'archive_date':archive_date,
                                      'assets': sorted(self.inventory, key=lambda r: (r['kind'], r['title']))})
        save(self.out/'resources.json', self.assets)
        for group, entries in self.templates.items():
            save(self.out/(group + '.json'), entries)
        def order(item):
            c = item['component']
            new = c.get('pos') in NEW_POSITIONS or '_module_' in c.get('payload','')
            return (not new, -item['occurrences'], item['example'])
        save(self.out/'priors.json', {p:sorted(items.values(), key=order) for p,items in self.examples.items()})
        save(self.out/'samples.json', self.samples)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('zip', type=Path)
    parser.add_argument('--out', type=Path, default=PROJECT/'webui/web/public/zapret2-pack')
    parser.add_argument('--chunks', type=Path, default=PROJECT/'asus/zapret2-pack-lists')
    args = parser.parse_args()
    if sha(args.zip.read_bytes()) != ZIP_SHA:
        raise SystemExit('Unexpected archive SHA-256')
    args.out.mkdir(parents=True, exist_ok=True)
    args.chunks.mkdir(parents=True, exist_ok=True)
    with ZipFile(args.zip) as archive:
        Library(archive, args.out, args.chunks).compile()

import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { parseConfig, formatConfig } from '../webui/web/src/utils/configParser.ts';

assert.equal(parseConfig('').NFQWS_EXTRA_ARGS, 'MODE_AUTO');
assert.equal(parseConfig('NFQWS_EXTRA_ARGS="$MODE_AUTO"\n').NFQWS_EXTRA_ARGS, 'MODE_AUTO');
assert.equal(parseConfig('NFQWS_EXTRA_ARGS="$MODE_ALL"\n').NFQWS_EXTRA_ARGS, 'MODE_ALL');

const original = 'ASUS_CLIENT_MODE="include"\nASUS_CLIENTS4="192.0.2.10 198.51.100.0/24"\nASUS_CLIENTS6="2001:db8::/64"\n# retain comment\n';
const parsed = parseConfig(original);
assert.equal(parsed.ASUS_CLIENT_MODE, 'include');
assert.equal(parsed.ASUS_CLIENTS4, '192.0.2.10 198.51.100.0/24');
assert.equal(parsed.ASUS_CLIENTS6, '2001:db8::/64');
assert.equal(parseConfig('IPV6_ENABLED=1\n').IPV6_ENABLED, true);
assert.equal(parseConfig('IPV6_ENABLED=0\n').IPV6_ENABLED, false);
const output = formatConfig(original, {...parsed, ASUS_CLIENT_MODE:'exclude', ASUS_CLIENTS4:'203.0.113.7', ASUS_CLIENTS6:'2001:db8:1::/64', IPV6_ENABLED:true});
const reparsed = parseConfig(output);
assert.equal(reparsed.ASUS_CLIENT_MODE, 'exclude');
assert.equal(reparsed.ASUS_CLIENTS4, '203.0.113.7');
assert.equal(reparsed.ASUS_CLIENTS6, '2001:db8:1::/64');
assert.equal(reparsed.IPV6_ENABLED, true);
const legacy = 'ASUS_CLIENT_MODE="all"\n# retain legacy comment\n';
const updated = formatConfig(legacy, {...parseConfig(legacy), IPV6_ENABLED:true, ASUS_CLIENTS6:'2001:db8::10'});
assert.equal(parseConfig(updated).IPV6_ENABLED, true);
assert.equal(parseConfig(updated).ASUS_CLIENTS6, '2001:db8::10');
assert.match(updated, /# retain legacy comment/);
assert.match(output, /# retain comment/);
const quotedStartup = String.raw`NFQWS_BASE_ARGS="--debug=0 --blob=\"tls:@/opt/etc/nfqws2/blobs/old.bin\" --lua-init=@/keep.lua"
NFQWS_ARGS="--filter-tcp=443 --lua-desync=fake:blob=tls"
UNRELATED="keep this"
`;
const quotedValue = '--debug=0 --blob="tls:@/opt/etc/nfqws2/blobs/old.bin" --lua-init=@/keep.lua';
const quotedParsed = parseConfig(quotedStartup);
assert.equal(quotedParsed.NFQWS_BASE_ARGS, quotedValue, 'Escaped inner quotes must not end persisted startup arguments');
const selectedValue = quotedValue.replace('/old.bin', '/new.bin');
const quotedSaved = formatConfig(quotedStartup, { ...quotedParsed, NFQWS_BASE_ARGS: selectedValue }, ['NFQWS_BASE_ARGS']);
assert.equal(quotedSaved, quotedStartup.replace('/old.bin', '/new.bin'), 'Saving quoted blob selection preserves valid outer quoting and other assignments');
assert.equal(parseConfig(quotedSaved).NFQWS_BASE_ARGS, selectedValue);
const multilineStartup = String.raw`NFQWS_BASE_ARGS="--blob \"tls:@/etc/nfqws2/blobs/old.bin\"
  --debug=0 --lua-init=@/keep.lua"
NFQWS_ARGS="keep"
`;
const multilineParsed = parseConfig(multilineStartup);
assert.equal(multilineParsed.NFQWS_BASE_ARGS, '--blob "tls:@/etc/nfqws2/blobs/old.bin"\n--debug=0 --lua-init=@/keep.lua');
const multilineSaved = formatConfig(multilineStartup, { ...multilineParsed, NFQWS_BASE_ARGS: multilineParsed.NFQWS_BASE_ARGS.replace('/old.bin', '/new.bin') }, ['NFQWS_BASE_ARGS']);
assert.equal(multilineSaved, multilineStartup.replace('/old.bin', '/new.bin'));
const literalSlashes = String.raw`NFQWS_BASE_ARGS="--blob=tls:@/etc/nfqws2/blobs/old.bin --name=\\\"quoted\\\""`;
assert.equal(parseConfig(literalSlashes).NFQWS_BASE_ARGS, String.raw`--blob=tls:@/etc/nfqws2/blobs/old.bin --name=\"quoted\"`);
const shellDir = mkdtempSync(join(tmpdir(), 'blob-config-shell-'));
try {
  for (const count of [1, 2, 3, 4]) {
    const continued = ['NFQWS_BASE_ARGS="--debug=0 ' + '\\'.repeat(count), '  --blob=tls:@/etc/nfqws2/blobs/old.bin"', 'UNRELATED="keep"', ''].join('\n');
    const before = parseConfig(continued);
    const saved = formatConfig(continued, { ...before, NFQWS_BASE_ARGS: before.NFQWS_BASE_ARGS.replace('/old.bin', '/new.bin') }, ['NFQWS_BASE_ARGS']);
    assert.equal(saved, continued.replace('/old.bin', '/new.bin'), `Preserve ${count} source backslashes before a newline`);
    const values = [continued, saved].map((text, i) => {
      const path = join(shellDir, String(i)); writeFileSync(path, text);
      const result = spawnSync('/bin/sh', ['-c', 'set -f; . "$1"; printf "%s" "$NFQWS_BASE_ARGS"', 'fixture', path], { encoding: 'utf8' });
      assert.equal(result.status, 0, result.stderr); return result.stdout;
    });
    assert.equal(values[1], values[0].replace('/old.bin', '/new.bin'), 'Save must retain actual shell startup arguments');
  }
} finally { rmSync(shellDir, { recursive: true, force: true }); }
console.log('PASS: ASUS client selection config round trip');

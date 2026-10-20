import assert from 'node:assert/strict';
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
console.log('PASS: ASUS client selection config round trip');

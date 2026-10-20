import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const path='../webui/web/src/api/dpiOptions.ts';
let lib;try {lib=await import(path);} catch {lib={};}
assert.equal(typeof lib.effectiveDpiSettings,'function','settings summary is missing');
const metadata=JSON.parse(readFileSync(new URL('../support/dpi-native-defaults.json',import.meta.url)));
const value=lib.effectiveDpiSettings({},metadata);
assert.equal(value.coverage.domains,35);assert.equal(value.coverage.tcp,110);assert.equal(value.concurrency,50);
assert.equal(lib.effectiveDpiSettings({targets:{domains:[]}},metadata).coverage.domains,35);
assert.equal(lib.effectiveDpiSettings({config:{TIMEOUT:2,MAX_CONCURRENT:5}},metadata).timeout,2);
assert.throws(()=>lib.parseDpiOptions('[]'));
assert.throws(()=>lib.parseDpiOptions('{'));
assert.equal(lib.parseDpiOptions('{"profile":"global"}').profile,'global');
console.log('PASS original coverage, explicit empty targets and editable options');

for (const [input,field] of [[{profile:123},'profile'],[{limits:{total_seconds:{x:1}}},'limits.total_seconds'],[{limits:{group_seconds:'slow'}},'limits.group_seconds'],[{targets:'wrong'},'targets'],[{interface:{}},'interface'],[{burst:{trace:'yes'}},'burst.trace']]) {
  assert.throws(()=>lib.parseDpiOptions(JSON.stringify(input)),new RegExp('invalid_options:'+field.replaceAll('.','\\.')));
}
const confirmed=lib.effectiveDpiSettings(lib.parseDpiOptions('{"profile":"global","limits":{"total_seconds":900}}'),metadata);
assert.equal(confirmed.profile.toUpperCase(),'GLOBAL');assert.equal(confirmed.limits.total_seconds,900);
const malformed=lib.effectiveDpiSettings({profile:123,limits:{total_seconds:{x:1}}},metadata);
assert.equal(typeof malformed.profile,'string');assert.equal(typeof malformed.limits.total_seconds,'number');
assert.deepEqual(lib.parseDpiOptions('{"config":[],"targets":[],"burst":[]}'),{config:{},targets:{},burst:{}});

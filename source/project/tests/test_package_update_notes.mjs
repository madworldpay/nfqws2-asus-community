import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';

const source = new URL('../webui/web/src/api/packageUpdateNotes.ts', import.meta.url);
assert.ok(existsSync(source), 'cumulative release notes loader is missing');
const { getPackageUpdateNotes } = await import(source.href);
const release = (build, body = `Changes ${build}`, extra = {}) => ({
  tag_name: `build${build}`, body, draft: false, prerelease: false,
  published_at: '2026-10-25T00:00:00Z', ...extra,
});
let calls = [];
function pages(values) {
  calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    return Response.json(values[calls.length - 1] ?? []);
  };
}
// Exclude the installed release and future/draft/prerelease entries; sort by
// global Build, not API ordering or the engine's semantic version.
pages([
  [release(62), release(71), release(65), release(64), release(69),
   release(68), release(67), release(66), release(70), release(72),
   release(63, 'unpublished', { draft: true }),
   release(74, 'preview', { prerelease: true })],
]);
const notes = await getPackageUpdateNotes('1.3.1-asus6+b62', 71);
assert.equal(notes.complete, true);
assert.deepEqual(notes.releases.map(r => r.build), [64,65,66,67,68,69,70,71]);
assert.equal(notes.releases.at(-1).notes, 'Changes 71');
assert.equal(calls.length, 1);
assert.match(calls[0].url, /^https:\/\/api.github.com\/repos\/madworldpay\/nfqws2-asus-community\/releases\?per_page=30&page=1$/);
assert.equal(calls[0].options.credentials, 'omit');
assert.equal(calls[0].options.referrerPolicy, 'no-referrer');
assert.equal(calls[0].options.redirect, 'error');
assert.deepEqual(Object.keys(calls[0].options.headers), ['Accept']);

// Pagination must not assume that a numerically older release ends the range.
pages([Array.from({length:30}, (_, i) => release(i + 1)), [release(71), release(70)]]);
assert.deepEqual((await getPackageUpdateNotes('1.3.2-asus6+b69',71)).releases.map(r=>r.build), [70,71]);
assert.equal(calls.length,2);

// Do not claim a complete changelog when target/middle text is missing or the
// fetch is bounded before the last page. Never invent a missing Build.
pages([[release(70)]]);
assert.equal((await getPackageUpdateNotes('1.3.2-asus6+b69',71)).complete,false);
pages([[release(70,null),release(71)]]);
const empty = await getPackageUpdateNotes('1.3.2-asus6+b69',71);
assert.equal(empty.complete,false);
assert.deepEqual(empty.releases.map(r=>r.build),[70,71]);
assert.equal(empty.releases[0].notes,'');
pages(Array.from({length:4},(_,page)=>Array.from({length:30},(_,i)=>release(page*30+i+1))));
assert.equal((await getPackageUpdateNotes('1.3.1-asus6+b62',71)).complete,false);
assert.equal(calls.length,4);

pages([[release(71)]]);
await assert.rejects(getPackageUpdateNotes('unknown',71));
await assert.rejects(getPackageUpdateNotes('1.3.2-asus6+b71',71));
assert.equal(calls.length,0,'invalid ranges must not contact GitHub');
pages([[release(71)]]);
const abort = new AbortController();abort.abort();
await assert.rejects(getPackageUpdateNotes('1.3.2-asus6+b70',71,abort.signal));
assert.equal(calls.length,0);
for (const response of [
  () => Response.json({message:'rate limit'}, {status:403}),
  () => Response.json({bad:'not a list'}),
  () => new Response('<html>bad</html>', {headers:{'Content-Type':'text/html'}}),
  () => new Response(' '.repeat(1048577), {headers:{'Content-Type':'application/json'}}),
]) {
  globalThis.fetch = async () => response();
  await assert.rejects(getPackageUpdateNotes('1.3.2-asus6+b70',71));
}
console.log('PASS cumulative range, sparse releases, pagination, partial history, anonymous bounded transport');

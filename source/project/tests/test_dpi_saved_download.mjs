import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync } from 'node:fs';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const entry = new URL('../webui/web/src/utils/dpiSavedDownload.ts', import.meta.url);
assert.ok(existsSync(entry), 'DPI window needs a verified original TXT download');
const { build } = await import('../webui/web/node_modules/esbuild/lib/main.js');
const dir = await mkdtemp(join(tmpdir(), 'dpi-saved-download-'));
const original = {
  fetch: globalThis.fetch,
  document: globalThis.document,
  window: globalThis.window,
  timeout: globalThis.setTimeout,
  crypto: Object.getOwnPropertyDescriptor(globalThis, 'crypto'),
  create: URL.createObjectURL,
  revoke: URL.revokeObjectURL,
};
try {
  const root = fileURLToPath(new URL('../webui/web/src/', import.meta.url));
  const outfile = join(dir, 'download.mjs');
  await build({ entryPoints: [fileURLToPath(entry)], outfile, bundle: true, alias: { '@': root }, platform: 'node', format: 'esm', logLevel: 'silent' });
  const { downloadDpiSavedReport } = await import(pathToFileURL(outfile));
  // Literal UTF-8 fixture includes a BOM, CRLF, Unicode and a final LF. No text normalization is permitted.
  const raw = '\uFEFFОтчёт DPI ✓\r\nDNS: OK\r\nTLS: OK\n';
  const bytes = Buffer.from(raw, 'utf8');
  const hash = createHash('sha256').update(bytes).digest('hex');
  const filename = 'dpi_detector_results-20261106-120000.txt';
  const row = { id: 'a'.repeat(32), filename, bytes: bytes.length, sha256: hash };
  const response = { raw, sha256: hash, filename };
  const calls = [];
  const urls = [];
  const revoked = [];
  const timers = [];
  const links = [];
  let clickError = false;
  let appendError = false;
  globalThis.window = { isSecureContext: false, location: { protocol: 'http:' } };
  Object.defineProperty(globalThis, 'crypto', { value: {}, configurable: true });
  globalThis.setTimeout = (fn, delay) => { timers.push({ fn, delay }); return timers.length; };
  URL.createObjectURL = blob => { const url = original.create(blob); urls.push({ url, blob }); return url; };
  URL.revokeObjectURL = url => { revoked.push(url); original.revoke(url); };
  globalThis.document = {
    createElement(tag) {
      assert.equal(tag, 'a');
      const link = { href: '', download: '', clicked: false, removed: false, click() { if (clickError) throw Error('download blocked'); this.clicked = true; }, remove() { this.removed = true; } };
      links.push(link);
      return link;
    },
    body: { append(link) { assert.ok(links.includes(link)); if (appendError) throw Error('append failed'); } },
  };
  const respond = (body = response, status = 200) => {
    globalThis.fetch = async (url, options) => {
      calls.push({ url, options });
      return Response.json(body, { status });
    };
  };
  respond();
  await downloadDpiSavedReport('csrf-for-dpi', row);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, '/index.php');
  assert.equal(calls[0].options.method, 'POST');
  assert.equal(calls[0].options.credentials, 'same-origin');
  assert.equal(calls[0].options.redirect, 'error');
  assert.deepEqual(Object.fromEntries(calls[0].options.body), { cmd: 'sharesavedread', csrf_token: 'csrf-for-dpi', id: row.id });
  assert.deepEqual(Buffer.from(await urls[0].blob.arrayBuffer()), bytes, 'download preserves every original UTF-8 byte');
  assert.equal(links[0].download, filename);
  assert.equal(links[0].href, urls[0].url);
  assert.ok(links[0].clicked && links[0].removed);
  assert.deepEqual(revoked, [], 'URL survives anchor removal and dialog unmount until browser starts its download');
  assert.equal(timers.length, 1);
  assert.ok(timers[0].delay >= 1000 && timers[0].delay <= 60000, 'URL cleanup is bounded and deferred');
  timers.shift().fn();
  assert.deepEqual(revoked, [urls[0].url]);

  for (const invalid of [
    { ...response, filename: '../../router.txt' },
    { ...response, sha256: '0'.repeat(64) },
    { ...response, raw: raw.replace('OK', 'NO') },
    { ...response, raw: 'x'.repeat(1048577) },
    { ...response, filename: 'dpi_detector_results-20261106-130000.txt' },
  ]) {
    respond(invalid);
    await assert.rejects(downloadDpiSavedReport('csrf-for-dpi', row), error => error.code === 'invalid_response');
  }
  for (const invalidRow of [{ ...row, sha256: '0'.repeat(64) }, { ...row, bytes: row.bytes + 1 }]) {
    respond();
    await assert.rejects(downloadDpiSavedReport('csrf-for-dpi', invalidRow), error => error.code === 'invalid_response');
  }
  const largeRaw = 'x'.repeat(1048577);
  const largeHash = createHash('sha256').update(largeRaw).digest('hex');
  respond({ ...response, raw: largeRaw, sha256: largeHash });
  await assert.rejects(downloadDpiSavedReport('csrf-for-dpi', { ...row, bytes: 1048577, sha256: largeHash }), error => error.code === 'invalid_response');
  respond({ ...response, filename: '../../router.txt' });
  await assert.rejects(downloadDpiSavedReport('csrf-for-dpi', { ...row, filename: '../../router.txt' }), error => error.code === 'invalid_response');
  const requestsBeforeInvalidId = calls.length;
  await assert.rejects(downloadDpiSavedReport('csrf-for-dpi', { ...row, id: '../router' }), error => error.code === 'invalid_request');
  assert.equal(calls.length, requestsBeforeInvalidId, 'invalid report IDs never reach the server');
  assert.equal(urls.length, 1, 'invalid content is never offered as a download');
  respond({ error: 'forbidden' }, 403);
  await assert.rejects(downloadDpiSavedReport('expired-csrf', row), error => error.code === 'forbidden');
  assert.equal(urls.length, 1);

  for (const failure of ['click', 'append']) {
    clickError = failure === 'click';
    appendError = failure === 'append';
    respond();
    await assert.rejects(downloadDpiSavedReport('csrf-for-dpi', row), /blocked|append failed/);
    assert.ok(links.at(-1).removed, 'failed download removes its temporary anchor');
    for (const timer of timers.splice(0)) timer.fn();
    assert.ok(revoked.includes(urls.at(-1).url), 'failed download releases its blob URL');
  }
  console.log('PASS DPI original TXT: exact bytes on LAN HTTP, CSRF, bounds/hash/name/list integrity, authorization errors and blob URL cleanup on success/failure');
} finally {
  globalThis.fetch = original.fetch;
  globalThis.document = original.document;
  globalThis.window = original.window;
  globalThis.setTimeout = original.timeout;
  if (original.crypto) Object.defineProperty(globalThis, 'crypto', original.crypto);
  else delete globalThis.crypto;
  URL.createObjectURL = original.create;
  URL.revokeObjectURL = original.revoke;
  await rm(dir, { recursive: true, force: true });
}

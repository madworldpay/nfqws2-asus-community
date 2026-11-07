import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { build } from '../webui/web/node_modules/esbuild/lib/main.js';

// Catches accepting HTTP 400 as service success, mismatched target replies,
// invented context and a TXT export that drops server observations.
const src = fileURLToPath(new URL('../webui/web/src/', import.meta.url));
assert.ok(existsSync(join(src, 'api/dpiSiteCheckClient.ts')), 'service check client must validate control observations');
const dir = await mkdtemp(join(tmpdir(), 'dpi-site-client-'));
const oldFetch = globalThis.fetch;
try {
  await build({ entryPoints: [join(src, 'api/dpiSiteCheckClient.ts')], outfile: join(dir, 'client.mjs'), bundle: true, alias: { '@': src }, format: 'esm', platform: 'node', logLevel: 'silent' });
  await build({ entryPoints: [join(src, 'utils/dpiSiteCheckDownload.ts')], outfile: join(dir, 'download.mjs'), bundle: true, alias: { '@': src }, format: 'esm', platform: 'node', logLevel: 'silent' });
  const { checkDpiSite, validateDpiSiteCheck } = await import(pathToFileURL(join(dir, 'client.mjs')));
  const { buildDpiSiteCheckText, dpiSiteResponseLabel } = await import(pathToFileURL(join(dir, 'download.mjs')));
  const context = { nfqws: 'running', mode: 'auto', config_sha256: 'a'.repeat(64) };
  const fixture = () => ({ type: 'nfqws2_dpi_site_check', schema_version: 1, target: 'facebook-main', url: 'https://www.facebook.com/', started_at: 1793952000, finished_at: 1793952001, context: { before: { ...context }, after: { ...context }, changed: false }, response: { outcome: 'response', http_status: 400, bytes_read: 125, body_limited: false, redirect: null, elapsed_ms: 451, error_code: null }, full_service_verified: false, dns_scope: 'system_resolver' });
  let sent;
  globalThis.fetch = async (url, options) => {
    sent = { url, options };
    return Response.json(fixture());
  };
  const report = await checkDpiSite('csrf-fixture', 'facebook-main');
  assert.equal(report.response.http_status, 400);
  assert.equal(report.full_service_verified, false);
  assert.equal(sent.url, '/index.php');
  assert.equal(sent.options.credentials, 'same-origin');
  assert.deepEqual(Object.fromEntries(sent.options.body), { cmd: 'dpisitecheck', csrf_token: 'csrf-fixture', target: 'facebook-main' });
  await assert.rejects(checkDpiSite('csrf', 'https://127.0.0.1/'), error => error.code === 'invalid_request');
  const local = {...fixture(), dns_scope:'local_resolver'};
  assert.deepEqual(validateDpiSiteCheck(local, 'facebook-main'), local);
  globalThis.fetch = async (url, options) => { sent={url,options}; return Response.json(local); };
  await checkDpiSite('csrf-fixture', 'facebook-main', 'local_resolver');
  assert.equal(sent.options.body.get('dns_scope'), 'local_resolver');
  globalThis.fetch = async () => Response.json(fixture());
  await assert.rejects(checkDpiSite('csrf-fixture','facebook-main','local_resolver'), error => error.code==='invalid_response');
  await assert.rejects(checkDpiSite('csrf-fixture','facebook-main','8.8.8.8'), error => error.code==='invalid_request');
  const rollback = fixture();
  rollback.finished_at = rollback.started_at - 30;
  const valid = [fixture(), rollback];
  for (const outcome of ['timeout', 'tls_error', 'connection_error', 'unavailable', 'blocked_address']) {
    const value = fixture();
    value.response = { ...value.response, outcome, http_status: null, bytes_read: 0, elapsed_ms: null, error_code: 'probe_error' };
    valid.push(value);
  }
  const limited = fixture();
  limited.response = { ...limited.response, outcome: 'read_limited', http_status: 200, bytes_read: 262144, body_limited: true };
  valid.push(limited);
  const unknown = fixture();
  unknown.context.before = { nfqws: 'unknown', mode: 'unknown', config_sha256: null };
  unknown.context.changed = null;
  valid.push(unknown);
  const changed = fixture();
  changed.context.after = { nfqws: 'stopped', mode: 'list', config_sha256: 'b'.repeat(64) };
  changed.context.changed = true;
  valid.push(changed);
  const partiallyKnownChange = structuredClone(unknown);
  partiallyKnownChange.context.before.nfqws = 'stopped';
  partiallyKnownChange.context.changed = true;
  valid.push(partiallyKnownChange);
  valid.forEach(value => assert.deepEqual(validateDpiSiteCheck(value, 'facebook-main'), value));

  const mutations = [
    value => { value.target = 'youtube-main'; },
    value => { value.url = 'https://m.facebook.com/'; },
    value => { value.url = 'http://127.0.0.1/'; },
    value => { value.full_service_verified = true; },
    value => { value.dns_scope = 'configured_chain_verified'; },
    value => { value.dns_scope = ['local_resolver']; },
    value => { value.schema_version = 2; },
    value => { value.started_at = '1793952000'; },
    value => { value.response.http_status = 600; },
    value => { value.response.http_status = 400.5; },
    value => { value.response.bytes_read = 262145; },
    value => { value.response.elapsed_ms = -1; },
    value => { value.response.redirect = 'x'.repeat(2049); },
    value => { value.response.redirect = 'https://example.com/\nforged'; },
    value => { value.response.error_code = 'x'.repeat(65); },
    value => { value.response.error_code = '<html>'; },
    value => { value.response.body_limited = 'false'; },
    value => { value.response.http_status = null; },
    value => { value.response.body_limited = true; },
    value => { value.response.outcome = 'read_limited'; },
    value => { value.response.outcome = 'read_limited'; value.response.body_limited = true; value.response.http_status = null; },
    value => { value.context.before.config_sha256 = 'garbage'; },
    value => { value.context.before.mode = 'shell command'; },
    value => { value.context.before.nfqws = true; },
    value => { value.context.before.nfqws = ['running']; },
    value => { value.context.before.mode = ['auto']; },
    value => { value.response.outcome = ['response']; },
    value => { value.context.changed = true; },
    value => { value.context.before.config_sha256 = null; },
    value => { value.context.after.mode = 'all'; },
    value => { value.response.html = '<script>bad()</script>'; },
    value => { delete value.context.after; },
  ];
  for (const mutate of mutations) {
    const value = fixture(); mutate(value);
    assert.throws(() => validateDpiSiteCheck(value, 'facebook-main'), error => error.code === 'invalid_response');
  }
  globalThis.fetch = async () => Response.json({ error: 'terminal_busy' }, { status: 409 });
  await assert.rejects(checkDpiSite('csrf', 'facebook-main'), error => error.code === 'terminal_busy');
  globalThis.fetch = async () => new Response('x'.repeat(16385), { headers: { 'Content-Type': 'application/json' } });
  await assert.rejects(checkDpiSite('csrf', 'facebook-main'), error => error.code === 'invalid_response');
  for (const lang of ['ru', 'en']) {
    const pack = JSON.parse(await readFile(join(src, `translations/${lang}.json`), 'utf8'));
    const t = key => key.split('.').reduce((v, part) => v[part], pack);
    const cdn={...fixture(),target:'facebook-cdn',url:'https://static.xx.fbcdn.net/'};
    cdn.response={...cdn.response,http_status:403};
    assert.equal(dpiSiteResponseLabel(cdn,t),t('dpi_site_check.endpoint_response'));
    const dns={...fixture(),response:{...fixture().response,outcome:'connection_error',http_status:null,error_code:'dns_failed'}};
    assert.equal(dpiSiteResponseLabel(dns,t),t('dpi_site_check.dns_failed'));
    const localText=buildDpiSiteCheckText('facebook',[local],t);
    assert.ok(localText.includes(t('dpi_site_check.dns_local_resolver')));
    const text = buildDpiSiteCheckText('facebook', [report, changed, unknown, rollback], t);
    for (const value of [report, changed, unknown, rollback]) {
      assert.ok(text.includes(JSON.stringify(value, null, 2)), 'TXT contains each exact validated server observation');
    }
    assert.ok(text.includes(t('dpi_site_check.clock_changed')), 'clock rollback warning survives TXT export');
    assert.ok(t('dpi_site_check.clock_changed'), 'localized clock warning exists');
    assert.ok(text.includes(t('dpi_site_check.http_error')), 'HTTP 400 has an error label in TXT');
    assert.ok(text.includes(t('dpi_site_check.changed')));
    assert.ok(text.includes(t('dpi_site_check.unknown')));
    assert.ok(text.includes(t('dpi_site_check.incomplete')));
    assert.ok(!text.includes('__MISSING__'));
  }
  console.log('PASS DPI service client: HTTP 400, bounded strict replies, request target/context coherence, busy recovery and RU/EN honest TXT');
} finally {
  globalThis.fetch = oldFetch;
  await rm(dir, { recursive: true, force: true });
}

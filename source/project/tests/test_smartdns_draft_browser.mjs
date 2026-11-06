import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { after, before, test } from 'node:test';
import { build } from '../webui/web/node_modules/esbuild/lib/main.js';

const { chromium } = await import(process.env.NFQWS_PLAYWRIGHT_MODULE || 'playwright');
const web = fileURLToPath(new URL('../webui/web/', import.meta.url));
const dir = await mkdtemp(join(tmpdir(), 'nfqws-smartdns-draft-'));
const en = JSON.parse(await readFile(join(web, 'src/translations/en.json'), 'utf8'));
let browser, server;

// Handwritten server snapshots stand in for authenticated HTTP on a router.
// The real configurator, form, preset mapping, state, and request client run here.
const profile = (label = 'Original DNS') => ({
  schema_version: 1,
  upstreams: [{
    id: 'household', label, protocol: 'dot', address: '9.9.9.9', port: 853,
    tls_name: 'dns.quad9.net', url: '', bootstrap: [], default: true,
    domains: [{ name: 'image.example.org', include_subdomains: true }],
  }],
  records: [{ name: 'fixed.example.org', include_subdomains: false,
    addresses: ['192.0.2.10'], checked_at: '2026-11-01' }],
});
const status = (state = 'idle') => ({
  schema_version: 1, state, request_id: null, preview_id: null, code: null,
  active_profile_hash: null, deadline_remaining_s: null, checks: [], conflicts: [],
});

before(async () => {
  await build({
    stdin: { resolveDir: web, loader: 'tsx', contents: `
      import React from 'react';import {createRoot} from 'react-dom/client';
      import {SmartDnsConfigurator} from './src/components/SmartDnsConfigurator';
      import {TranslationContext} from './src/context/TranslationContext';
      import en from './src/translations/en.json';
      const t=k=>k.split('.').reduce((v,p)=>v?.[p],en)||k;
      createRoot(document.getElementById('root')).render(
        <TranslationContext.Provider value={{t,langcode:'en'}}>
          <SmartDnsConfigurator csrf="session" external={false}/>
        </TranslationContext.Provider>);
    ` },
    bundle: true, platform: 'browser', format: 'iife', outfile: join(dir, 'fixture.js'),
    jsx: 'automatic', logLevel: 'silent', tsconfig: join(web, 'tsconfig.app.json'),
  });
  const script = await readFile(join(dir, 'fixture.js'));
  server = createServer((req, res) => {
    res.setHeader('Content-Type', req.url === '/fixture.js' ? 'text/javascript' : 'text/html');
    res.end(req.url === '/fixture.js' ? script : '<!doctype html><html><body><div id="root"></div><script src="/fixture.js"></script></body></html>');
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  browser = await chromium.launch({ headless: true, ...(process.env.NFQWS_CHROMIUM_EXECUTABLE ? { executablePath: process.env.NFQWS_CHROMIUM_EXECUTABLE } : {}) });
});
after(async () => {
  await browser?.close();
  if (server) await new Promise(resolve => server.close(resolve));
  await rm(dir, { recursive: true, force: true });
});

async function fixture(t, delayInitial = false) {
  const page = await browser.newPage();
  page.setDefaultTimeout(5000);
  t.after(() => page.close());
  const model = { draft: profile(), polls: 0, saves: [], checks: 0, state: status(), normalize: null, preview: null };
  let release;
  const initial = new Promise(resolve => { release = resolve; });
  await page.route('**/index.php', async route => {
    const body = new URLSearchParams(route.request().postData());
    assert.equal(body.get('csrf_token'), 'session');
    let data;
    switch (body.get('cmd')) {
      case 'smartdnsconfigstatus': {
        model.polls++;
        const draft = structuredClone(model.draft);
        if (delayInitial && model.polls === 1) await initial;
        data = { status: model.state, draft, active_profile: null, confirmed_profile: null, routing: 'inactive', resume_code: null };
        break;
      }
      case 'smartdnsdraft':
        model.draft = JSON.parse(body.get('profile'));
        model.saves.push(structuredClone(model.draft));
        if (model.normalize) model.draft = model.normalize(model.draft);
        data = { profile_hash: 'a'.repeat(64) };
        break;
      case 'smartdnsvalidate':
        model.checks++;
        model.state = model.preview
          ? { ...status('preview_ready'), request_id: 'b'.repeat(32), preview_id: 'c'.repeat(32) }
          : status('failed');
        data = model.state;
        break;
      case 'smartdnspreview':
        data = model.preview;
        break;
      default: throw Error('Unexpected DNS mutation: ' + body.get('cmd'));
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) });
  });
  const firstRequest = page.waitForRequest(r => r.url().endsWith('/index.php'));
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  await firstRequest;
  return { page, model, release };
}
const card = (page, label) => page.getByRole('button', { name: new RegExp(label + ' · DOT') });

// Enabling editing before the initial GET lets its late snapshot erase a choice.
test('the initial draft loads before profile editing becomes available', async t => {
  const { page, release } = await fixture(t, true);
  assert.equal(await page.getByRole('button', { name: en.smartdns.form.add_dns, exact: true }).isDisabled(), true,
    'a late initial snapshot must not overwrite an already editable profile');
  assert.equal(await page.getByRole('button', { name: en.smartdns.reload_draft, exact: true }).isDisabled(), true);
  release();
  await card(page, 'Original DNS').waitFor();
  assert.equal(await page.getByRole('button', { name: en.smartdns.form.add_dns, exact: true }).isEnabled(), true);
});

// Import/undo writes the server draft while this page remains mounted.
test('polling adopts an imported draft while the editor is clean', async t => {
  const { page, model } = await fixture(t);
  await card(page, 'Original DNS').waitFor();
  model.draft = profile('Imported DNS');
  await card(page, 'Imported DNS').waitFor();
  assert.equal(await card(page, 'Original DNS').count(), 0);
  assert.equal(model.saves.length, 0, 'reading an import must not save or apply DNS');
  assert.equal(model.checks, 0);
});

test('polling preserves a locally selected preset and saves it on the first check', async t => {
  const { page, model } = await fixture(t);
  await card(page, 'Original DNS').click();
  await page.getByRole('combobox').first().click();
  await page.getByRole('option', { name: 'Cloudflare — DoH', exact: true }).click();
  const nextPoll = page.waitForResponse(r => r.url().endsWith('/index.php') && new URLSearchParams(r.request().postData()).get('cmd') === 'smartdnsconfigstatus');
  model.draft = profile('Imported elsewhere');
  await (await nextPoll).finished();
  assert.equal(await card(page, 'Imported elsewhere').count(), 0, 'dirty input belongs to the user');
  const checked = page.waitForResponse(r => r.url().endsWith('/index.php') && new URLSearchParams(r.request().postData()).get('cmd') === 'smartdnsvalidate');
  await page.getByRole('button', { name: en.smartdns.validate, exact: true }).click();
  await (await checked).finished();
  assert.equal(model.saves.length, 1);
  const saved = model.saves[0];
  assert.equal(saved.upstreams[0].protocol, 'doh');
  assert.equal(saved.upstreams[0].url, 'https://cloudflare-dns.com/dns-query');
  assert.equal(saved.upstreams[0].id, 'household');
  assert.equal(saved.upstreams[0].default, true);
  assert.deepEqual(saved.upstreams[0].domains, [{ name: 'image.example.org', include_subdomains: true }]);
  assert.deepEqual(saved.records, [{ name: 'fixed.example.org', include_subdomains: false, addresses: ['192.0.2.10'], checked_at: '2026-11-01' }]);
});


test('server normalization after a successful check keeps its matching preview usable', async t => {
  const { page, model } = await fixture(t);
  await card(page, 'Original DNS').click();
  await page.getByRole('textbox', { name: en.smartdns.form.domain, exact: true }).first().fill('IMAGE.EXAMPLE.ORG.');
  model.normalize = p => ({ ...p, upstreams: p.upstreams.map(s => ({ ...s,
    domains: s.domains.map(d => ({ ...d, name: d.name.toLowerCase().replace(/\.$/, '') })),
  })) });
  model.preview = {
    schema_version: 1, id: 'c'.repeat(32), profile_hash: 'a'.repeat(64), baseline_hash: 'd'.repeat(64),
    config: '# checked configuration', groups: [], overlaps: [], checks: [], expires_uptime: 600,
    scope: 'configuration_only', service_success_tested: false,
  };
  await page.getByRole('button', { name: en.smartdns.validate, exact: true }).click();
  await page.getByRole('button', { name: en.smartdns.connect, exact: true }).waitFor();
  assert.equal(model.saves.length, 1);
  assert.equal(model.saves[0].upstreams[0].domains[0].name, 'IMAGE.EXAMPLE.ORG.');
  assert.equal(await page.getByRole('textbox', { name: en.smartdns.form.domain, exact: true }).first().inputValue(), 'image.example.org');
});

test('a preview from another saved hash cannot cross a replaced draft revision', async t => {
  const { page, model } = await fixture(t);
  await card(page, 'Original DNS').click();
  await page.getByRole('textbox', { name: en.smartdns.form.label, exact: true }).fill('My draft');
  model.normalize = () => profile('Another saved draft');
  model.preview = {
    schema_version: 1, id: 'c'.repeat(32), profile_hash: 'e'.repeat(64), baseline_hash: 'd'.repeat(64),
    config: '# another configuration', groups: [], overlaps: [], checks: [], expires_uptime: 600,
    scope: 'configuration_only', service_success_tested: false,
  };
  const previewResponse = page.waitForResponse(r => r.url().endsWith('/index.php') && new URLSearchParams(r.request().postData()).get('cmd') === 'smartdnspreview');
  await page.getByRole('button', { name: en.smartdns.validate, exact: true }).click();
  await (await previewResponse).finished();
  await card(page, 'Another saved draft').waitFor();
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  assert.equal(await page.getByRole('button', { name: en.smartdns.connect, exact: true }).count(), 0);
});

test('loading an imported draft leaves confirmed DNS behind the explicit restore guard', async t => {
  const { page, model } = await fixture(t);
  await card(page, 'Original DNS').waitFor();
  model.state = { ...status('confirmed'), request_id: 'b'.repeat(32), active_profile_hash: 'f'.repeat(64) };
  model.draft = profile('Imported while connected');
  await card(page, 'Imported while connected').waitFor();
  assert.equal(await page.getByRole('button', { name: en.smartdns.validate, exact: true }).isDisabled(), true);
  assert.equal(await page.getByRole('button', { name: en.smartdns.reload_draft, exact: true }).isDisabled(), true);
  assert.equal(await page.getByRole('button', { name: en.smartdns.restore, exact: true }).isEnabled(), true);
  assert.equal(model.saves.length, 0);
  assert.equal(model.checks, 0);
});

test('a known saved hash rejects a mismatched preview at the same revision', async t => {
  const { page, model } = await fixture(t);
  await card(page, 'Original DNS').click();
  await page.getByRole('textbox', { name: en.smartdns.form.label, exact: true }).fill('My unchanged draft');
  // No normalization or external draft replacement: the editor revision stays
  // the one submitted by Check, while the returned preview belongs elsewhere.
  model.preview = {
    schema_version: 1, id: 'c'.repeat(32), profile_hash: 'e'.repeat(64), baseline_hash: 'd'.repeat(64),
    config: '# another configuration', groups: [], overlaps: [], checks: [], expires_uptime: 600,
    scope: 'configuration_only', service_success_tested: false,
  };
  const previewResponse = page.waitForResponse(r => r.url().endsWith('/index.php') && new URLSearchParams(r.request().postData()).get('cmd') === 'smartdnspreview');
  await page.getByRole('button', { name: en.smartdns.validate, exact: true }).click();
  await (await previewResponse).finished();
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  assert.equal(model.saves.length, 1);
  assert.equal(model.draft.upstreams[0].label, 'My unchanged draft');
  assert.equal(await page.getByRole('button', { name: en.smartdns.connect, exact: true }).count(), 0,
    'a matching editor revision cannot override the known submitted profile hash');
});

test('an initial saved preview can resume before this editor has submitted a hash', async t => {
  const { page, model, release } = await fixture(t, true);
  model.state = { ...status('preview_ready'), request_id: 'b'.repeat(32), preview_id: 'c'.repeat(32) };
  model.preview = {
    schema_version: 1, id: 'c'.repeat(32), profile_hash: 'e'.repeat(64), baseline_hash: 'd'.repeat(64),
    config: '# saved configuration', groups: [], overlaps: [], checks: [], expires_uptime: 600,
    scope: 'configuration_only', service_success_tested: false,
  };
  release();
  await page.getByRole('button', { name: en.smartdns.connect, exact: true }).waitFor();
  assert.equal(model.saves.length, 0);
  assert.equal(model.checks, 0);
});

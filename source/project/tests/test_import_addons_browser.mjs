import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from '../webui/web/node_modules/esbuild/lib/main.js';
const { chromium } = await import(process.env.NFQWS_PLAYWRIGHT_MODULE || 'playwright');
const web = fileURLToPath(new URL('../webui/web/', import.meta.url));
const dir = await mkdtemp(join(tmpdir(), 'import-addons-ui-'));
let browser, server;
try {
  await build({ stdin: { resolveDir: web, loader: 'tsx', contents: `
    import React from 'react';import{createRoot}from'react-dom/client';
    import{ImportDialog}from'./src/components/ImportDialog';
    import{TranslationContext}from'./src/context/TranslationContext';
    import ru from'./src/translations/ru.json';import en from'./src/translations/en.json';
    const lang=new URLSearchParams(location.search).get('lang')||'ru',p=lang==='en'?en:ru;
    const t=k=>k.split('.').reduce((v,x)=>v?.[x],p)||k;
    createRoot(document.getElementById('root')).render(<TranslationContext.Provider value={{t,langcode:lang}}><ImportDialog onClose={()=>{}}/></TranslationContext.Provider>);
  ` }, bundle: true, platform: 'browser', format: 'iife', outfile: join(dir, 'fixture.js'), jsx: 'automatic',
  tsconfig: join(web, 'tsconfig.app.json'), logLevel: 'silent', plugins: [{ name: 'external-boundaries', setup(b) {
    b.onLoad({ filter: /hooks\/useStatus\.tsx$/ }, () => ({ contents: 'export const useStatus=()=>({csrfToken:"fixture"});', loader: 'tsx' }));
    b.onLoad({ filter: /components\/Editor\.tsx$/ }, () => ({ contents: 'import React from"react";export const Editor=({value})=><textarea readOnly value={value}/>;', loader: 'tsx' }));
  } }] });
  const script = await readFile(join(dir, 'fixture.js'));
  server = createServer((req, res) => { res.setHeader('Content-Type', req.url === '/fixture.js' ? 'text/javascript' : 'text/html'); res.end(req.url === '/fixture.js' ? script : '<!doctype html><html><body><div id="root"></div><script src="/fixture.js"></script></body></html>'); });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  browser = await chromium.launch({ headless: true, ...(process.env.NFQWS_CHROMIUM_EXECUTABLE ? { executablePath: process.env.NFQWS_CHROMIUM_EXECUTABLE } : {}) });
  const addon = { id: 'riot-web', title: 'Riot web', description: 'Riot web domains use the selected base strategy. Game UDP bypass is not promised. <img src=x onerror=alert(1)>', attribution: 'Public fixture', updated_at: '2026-11-06T00:00:00Z', revision: 1, min_build: 92, size: 320, sha256: 'd'.repeat(64) };
  const doc = { values: { NFQWS_ARGS: '--filter-tcp=443 --lua-desync=multisplit:pos=1' }, ports: {}, resources: [], dns_sources: [], context: { purpose: 'Loaded base fixture' }, source: null, ignored: [], input_sha256: 'b'.repeat(64) };
  const profiles = ['provider', 'global'].map(category => ({ id: category, title: category === 'global' ? 'General fixture' : 'Provider fixture', category, provider: '', region: '', description: 'Base fixture', attribution: '', updated_at: '2026-11-05T00:00:00Z', revision: 1, min_build: 68, size: 2, sha256: 'a'.repeat(64) }));
  const catalog = (addons = [addon]) => ({ schema_version: 1, revision: 1, build: 92, addons });
  const attach = async (page, addonResponse = () => ({ body: catalog() }), action = 'scope_extended') => {
    const selections = [], calls = [], rawDocuments = [];
    await page.route('**/index.php', async route => {
      const post = new URLSearchParams(route.request().postData()), cmd = post.get('cmd'); calls.push(cmd);
      let body, status = 200;
      if (cmd === 'importstatus') body = { state: 'idle', id: null, can_undo: false, config_saved: false, dns_draft_saved: false };
      else if (cmd === 'importcatalog') body = { schema_version: 1, revision: 1, build: 92, profiles };
      else if (cmd === 'importcatalogload') body = { document: '{}' };
      else if (cmd === 'importinspect') body = doc;
      else if (cmd === 'importaddoncatalog') ({ body, status = 200 } = await addonResponse());
      else if (cmd === 'importprepare') {
        const selection = JSON.parse(post.get('selection')); selections.push(selection); rawDocuments.push(JSON.parse(post.get('documents')));
        body = { ready: true, problems: [], warnings: [], required: { files: [], shared: [] }, affected_blocks: [], config: 'fixture', changes: action === 'already_covered' ? [] : [{ key: 'NFQWS_EXTRA_ARGS', before: '--hostlist=base.txt', after: '--hostlist=base.txt --hostlist-domains=riotgames.com,riotcdn.net' }], files: [], draft: null, old_draft: null, digest: 'c'.repeat(64), proof: 'fixture-proof' };
        if (selection.addons) body.addons = selection.addons.map(p => ({ id: p.id, title: 'Riot web', kind: 'scope_domains_v1', domains: action === 'already_covered' ? [] : ['riotgames.com', 'riotcdn.net'], action, note: 'Existing exclusions take priority.' }));
      } else throw Error('Unexpected mutation or request: ' + cmd);
      await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    });
    return { selections, calls, rawDocuments };
  };
  const local = page => page.locator('input[type="file"]').setInputFiles({ name: 'base.json', mimeType: 'application/json', buffer: Buffer.from('{}') });
  const open = (page, lang) => page.goto(`http://127.0.0.1:${server.address().port}/?lang=${lang}`);
  for (const lang of ['ru', 'en']) for (const width of [1280, 390]) {
    const page = await browser.newPage({ viewport: { width, height: 900 } }); page.setDefaultTimeout(5000);
    const texts = JSON.parse(await readFile(join(web, 'src/translations', lang + '.json'), 'utf8'));
    const { selections, calls, rawDocuments } = await attach(page, () => ({ body: catalog([addon, { ...addon, id: 'future', title: 'Future module', min_build: 93 }]) }));
    await open(page, lang);
    await page.getByRole('button', { name: texts.import.catalog.choose, exact: true }).click();
    await page.getByRole('button', { name: /Provider fixture/ }).click();
    const group = page.getByRole('region', { name: lang === 'ru' ? 'Дополнения · Бета' : 'Add-ons · Beta', exact: true });
    await group.waitFor();
    const choice = group.getByRole('checkbox', { name: 'Riot web', exact: true });
    await choice.waitFor(); assert.equal(await choice.isChecked(), false, 'cloud add-ons start unselected');
    await group.getByText(addon.description, { exact: true }).first().waitFor();
    assert.equal(await group.locator('img').count(), 0, 'catalog prose remains escaped text');
    assert.equal(await group.getByRole('checkbox', { name: 'Future module', exact: true }).isDisabled(), true, 'new kinds/builds need a package update');
    assert.equal(await page.getByRole('checkbox', { name: /torrent|торрент/i }).count(), 0, 'specialized torrent condition stays global-only');
    const base = page.getByRole('checkbox', { name: texts.form.NFQWS_ARGS, exact: true });
    assert.equal(await base.isChecked(), true, 'base selection is unchanged');
    assert.equal(calls.includes('importprepare') || calls.includes('importapply'), false, 'catalog display does not preview or save');
    await choice.check();
    assert.equal(calls.includes('importprepare') || calls.includes('importapply'), false, 'checkbox only changes the selection');
    await page.getByRole('button', { name: texts.import.preview, exact: true }).first().click();
    await page.getByText(lang === 'ru' ? 'Область базовой стратегии расширена' : 'Base strategy scope extended', { exact: true }).waitFor();
    await page.getByText('riotgames.com, riotcdn.net', { exact: true }).waitFor();
    await page.getByText('Existing exclusions take priority.', { exact: true }).waitFor();
    await page.getByRole('button', { name: texts.form.NFQWS_EXTRA_ARGS, exact: true }).click();
    await page.getByText('--hostlist=base.txt --hostlist-domains=riotgames.com,riotcdn.net', { exact: true }).waitFor();
    assert.deepEqual(selections.at(-1).addons, [{ id: 'riot-web', sha256: 'd'.repeat(64) }]);
    assert.deepEqual(selections.at(-1).blocks, [{ key: 'NFQWS_ARGS', value: doc.values.NFQWS_ARGS }]);
    assert.deepEqual(rawDocuments.at(-1), ['{}'], 'base bytes are passed unchanged');
    const apply = page.getByRole('button', { name: texts.import.apply, exact: true }); assert.equal(await apply.isEnabled(), true);
    await choice.uncheck(); assert.equal(await apply.isDisabled(), true, 'changing an add-on invalidates the combined proof');
    assert.equal(await page.getByText('riotgames.com, riotcdn.net', { exact: true }).count(), 0);
    await choice.check();
    await page.getByRole('button', { name: /General fixture/ }).click();
    await group.getByRole('checkbox', { name: 'Riot web', exact: true }).waitFor();
    assert.equal(await choice.isChecked(), false, 'changing the base clears generic selections');
    const torrent = group.getByRole('checkbox', { name: texts.import.torrent_sites.label, exact: true });
    assert.equal(await torrent.isChecked(), false);
    assert.equal(await page.getByRole('checkbox', { name: texts.import.torrent_sites.label, exact: true }).count(), 1, 'torrent option appears once within Beta');
    await torrent.check(); await choice.check();
    await local(page);
    await choice.waitFor(); assert.equal(await choice.isChecked(), false, 'local source clears cloud selections');
    assert.equal(await page.getByRole('checkbox', { name: texts.import.torrent_sites.label, exact: true }).count(), 0);
    await choice.check(); await page.getByRole('button', { name: texts.import.preview, exact: true }).first().click();
    await page.getByText('riotgames.com, riotcdn.net', { exact: true }).waitFor();
    assert.deepEqual(selections.at(-1).addons, [{ id: 'riot-web', sha256: 'd'.repeat(64) }], 'local JSON supports signed cloud scopes');
    assert.equal(Object.hasOwn(selections.at(-1), 'torrent_sites'), false);
    assert.equal(calls.includes('importapply'), false);
    await page.close();
  }
  {
    const page = await browser.newPage(); page.setDefaultTimeout(5000);
    await attach(page, () => ({ body: catalog() }), 'already_covered');
    await open(page, 'en'); await local(page);
    await page.getByRole('checkbox', { name: 'Riot web', exact: true }).check();
    await page.getByRole('button', { name: 'Preview', exact: true }).first().click();
    await page.getByText('The base strategy already covers these domains; no change', { exact: true }).waitFor();
    assert.equal(await page.getByText('Domains to add', { exact: true }).count(), 0, 'already covered scopes do not claim to add domains');
    assert.equal(await page.getByRole('button', { name: 'Save selection', exact: true }).isEnabled(), true);
    await page.close();
  }
  {
    const page = await browser.newPage(); page.setDefaultTimeout(5000);
    let next = addon;
    const { selections } = await attach(page, () => ({ body: catalog([next]) }));
    await open(page, 'en'); await local(page);
    const group = page.getByRole('region', { name: 'Add-ons · Beta', exact: true });
    const choice = group.getByRole('checkbox', { name: 'Riot web', exact: true }); await choice.check();
    const preview = page.getByRole('button', { name: 'Preview', exact: true }).first();
    await preview.click(); await page.getByText('riotgames.com, riotcdn.net', { exact: true }).waitFor();
    next = { ...addon, revision: 2, sha256: 'e'.repeat(64) };
    await group.getByRole('button', { name: 'Refresh add-ons', exact: true }).click();
    await group.getByText('The catalog changed: outdated add-ons were deselected. Select their current versions and preview again.', { exact: true }).waitFor();
    assert.equal(await choice.isChecked(), false, 'changed content is never silently selected by ID');
    assert.equal(await page.getByRole('button', { name: 'Save selection', exact: true }).isDisabled(), true, 'a changed signed source invalidates the old proof');
    await choice.check(); await preview.click(); await page.getByText('riotgames.com, riotcdn.net', { exact: true }).waitFor();
    assert.deepEqual(selections.at(-1).addons, [{ id: 'riot-web', sha256: 'e'.repeat(64) }]);
    await page.close();
  }
  {
    const page = await browser.newPage(); page.setDefaultTimeout(5000);
    const { selections } = await attach(page, () => ({ body: catalog(Array.from({ length: 9 }, (_, n) => ({ ...addon, id: 'service-' + n, title: 'Service ' + n }))) }));
    await open(page, 'en'); await local(page);
    for (let n = 0; n < 8; n++) await page.getByRole('checkbox', { name: 'Service ' + n, exact: true }).check();
    assert.equal(await page.getByRole('checkbox', { name: 'Service 8', exact: true }).isDisabled(), true, 'selection limit matches the server contract');
    await page.getByRole('checkbox', { name: 'Service 0', exact: true }).uncheck();
    await page.getByRole('checkbox', { name: 'Service 8', exact: true }).check();
    await page.getByRole('button', { name: 'Preview', exact: true }).first().click();
    await page.getByRole('button', { name: 'Save selection', exact: true }).waitFor();
    assert.deepEqual(selections.at(-1).addons.map(entry => entry.id), ['service-1', 'service-2', 'service-3', 'service-4', 'service-5', 'service-6', 'service-7', 'service-8']);
    await page.close();
  }
  {
    const page = await browser.newPage(); page.setDefaultTimeout(5000);
    let index = catalog();
    const { selections } = await attach(page, () => ({ body: index }));
    await open(page, 'en'); await local(page);
    const group = page.getByRole('region', { name: 'Add-ons · Beta', exact: true });
    const choice = group.getByRole('checkbox', { name: 'Riot web', exact: true }); await choice.check();
    const preview = page.getByRole('button', { name: 'Preview', exact: true }).first();
    const save = page.getByRole('button', { name: 'Save selection', exact: true });
    const refresh = async () => {
      await Promise.all([
        page.waitForResponse(response => response.url().endsWith('/index.php') && new URLSearchParams(response.request().postData()).get('cmd') === 'importaddoncatalog'),
        group.getByRole('button', { name: 'Refresh add-ons', exact: true }).click(),
      ]);
      await group.getByRole('progressbar').waitFor({ state: 'hidden' });
    };
    await preview.click(); await page.getByText('riotgames.com, riotcdn.net', { exact: true }).waitFor();
    await refresh();
    assert.equal(await save.isEnabled(), true, 'an unchanged successful catalog refresh keeps a current proof');
    assert.equal(await choice.isChecked(), true);
    for (const next of [
      { ...index, revision: 2 },
      { ...index, revision: 2, addons: [{ ...addon, attribution: 'Updated public attribution', revision: 2 }] },
    ]) {
      index = next;
      await refresh();
      assert.equal(await save.isDisabled(), true, 'revision or selected metadata drift invalidates the old proof even with the same document SHA');
      assert.equal(await page.getByText('riotgames.com, riotcdn.net', { exact: true }).count(), 0, 'stale combined preview is removed');
      assert.equal(await choice.isChecked(), true, 'metadata changes retain the explicit selection');
      await group.getByText('Catalog details changed. Your add-on selection is retained; the previous preview was cleared.', { exact: true }).waitFor();
      await preview.click(); await page.getByText('riotgames.com, riotcdn.net', { exact: true }).waitFor();
      assert.equal(await save.isEnabled(), true, 'a new combined preview permits saving again');
      assert.deepEqual(selections.at(-1).addons, [{ id: 'riot-web', sha256: 'd'.repeat(64) }]);
    }
    await page.close();
  }
  {
    const page = await browser.newPage(); page.setDefaultTimeout(5000);
    let unavailable = true;
    const { selections } = await attach(page, () => unavailable ? { status: 503, body: { error: 'addon_catalog_unavailable' } } : { body: catalog() });
    await open(page, 'en'); await local(page);
    const group = page.getByRole('region', { name: 'Add-ons · Beta', exact: true });
    await group.getByRole('alert').waitFor();
    const preview = page.getByRole('button', { name: 'Preview', exact: true }).first(); assert.equal(await preview.isEnabled(), true, 'catalog failure does not block base import');
    await preview.click(); await page.getByRole('button', { name: 'Save selection', exact: true }).waitFor();
    assert.equal(Object.hasOwn(selections.at(-1), 'addons'), false);
    unavailable = false; await group.getByRole('button', { name: 'Refresh add-ons', exact: true }).click();
    const choice = group.getByRole('checkbox', { name: 'Riot web', exact: true }); await choice.check();
    unavailable = true; await group.getByRole('button', { name: 'Refresh add-ons', exact: true }).click();
    await group.getByRole('alert').waitFor(); assert.equal(await choice.isChecked(), true, 'failed refresh preserves the explicit selection');
    await preview.click(); await page.getByText('riotgames.com, riotcdn.net', { exact: true }).waitFor();
    assert.deepEqual(selections.at(-1).addons, [{ id: 'riot-web', sha256: 'd'.repeat(64) }]);
    await page.close();
  }
  {
    const page = await browser.newPage(); page.setDefaultTimeout(5000);
    let releaseOld, catalogCalls = 0;
    const old = new Promise(resolve => { releaseOld = resolve; });
    await attach(page, async () => ++catalogCalls === 1 ? await old : { body: catalog([{ ...addon, id: 'fresh', title: 'Fresh module' }]) });
    await open(page, 'en'); await local(page);
    await page.waitForFunction(() => document.querySelector('[role="region"] [role="progressbar"]'));
    await local(page);
    const group = page.getByRole('region', { name: 'Add-ons · Beta', exact: true });
    await group.getByRole('checkbox', { name: 'Fresh module', exact: true }).waitFor();
    releaseOld({ body: catalog([{ ...addon, id: 'old', title: 'Stale module' }]) });
    await page.waitForLoadState('networkidle');
    assert.equal(await group.getByRole('checkbox', { name: 'Stale module', exact: true }).count(), 0, 'old source catalog reply is ignored');
    assert.equal(await group.getByRole('checkbox', { name: 'Fresh module', exact: true }).isChecked(), false);
    await page.close();
  }
  console.log('PASS import add-ons RU/EN desktop/mobile: Beta, unchecked defaults, combined preview, source reset, escaped text, build gate, local JSON, failure isolation and stale reply');
} finally { await browser?.close(); if (server) await new Promise(resolve => server.close(resolve)); await rm(dir, { recursive: true, force: true }); }

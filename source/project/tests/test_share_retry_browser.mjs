import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { createServer } from 'node:http';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from '../webui/web/node_modules/esbuild/lib/main.js';

const { chromium } = await import(process.env.NFQWS_PLAYWRIGHT_MODULE || 'playwright');
const web = fileURLToPath(new URL('../webui/web/', import.meta.url));
const dir = await mkdtemp(join(tmpdir(), 'nfqws-share-retry-'));
let server, browser;
let prepared = 0;
let previewFailures = [];
const sends = [], previews = [], errors = [];
const source = { model: 'GT-BE19000AI', firmware: { firmver: '3006.102', buildno: '9', extendno: '0' }, kernel: '4.19.294', versions: { core: '1.3.2-asus6+b79', web: '0.1.4' } };
const initial = await readFile(new URL('../core/etc/nfqws2/nfqws2.conf', import.meta.url), 'utf8');
try {
  await build({ stdin: { resolveDir: web, loader: 'tsx', contents: `
    import React from 'react'; import {createRoot} from 'react-dom/client';
    import {TranslationContext} from './src/context/TranslationContext';
    import ru from './src/translations/ru.json'; import en from './src/translations/en.json';
    import {ShareDialog} from './src/components/ShareDialog';
    const pack=location.search.includes('en')?en:ru;
    const t=(key)=>key.split('.').reduce((v,k)=>v?.[k],pack)||key;
    createRoot(document.getElementById('root')).render(<TranslationContext.Provider value={{t}}><ShareDialog onClose={()=>{}} onSent={()=>document.body.dataset.accepted='yes'}/></TranslationContext.Provider>);
  ` }, bundle: true, platform: 'browser', format: 'iife', jsx: 'automatic', outfile: join(dir, 'fixture.js'),
    tsconfig: join(web, 'tsconfig.app.json'), logLevel: 'silent', define: { 'process.env.APP_VERSION': '"0.1.4"' },
    plugins: [{ name: 'status-fixture', setup(b) {
      b.onResolve({ filter: /hooks\/useStatus$/ }, () => ({ path: 'status', namespace: 'fixture' }));
      b.onLoad({ filter: /.*/, namespace: 'fixture' }, () => ({ contents: `export const useStatus=()=>({csrfToken:'fixture',platform:'asus-entware'});` }));
    } }] });
  const js = await readFile(join(dir, 'fixture.js'));
  server = createServer(async (req, res) => {
    if (req.method !== 'POST') {
      res.setHeader('Content-Type', req.url.startsWith('/fixture.js') ? 'text/javascript' : 'text/html');
      res.end(req.url.startsWith('/fixture.js') ? js : '<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"></head><body><div id="root"></div><script src="/fixture.js"></script></body></html>');
      return;
    }
    let raw = ''; for await (const chunk of req) raw += chunk;
    const p = new URLSearchParams(raw); const cmd = p.get('cmd'); let value;
    switch (cmd) {
      case 'sharestates': value = { mail: { configured: true, code: 'ready', sharing_v3: true, sharing_v4: true }, dpi: { installed: { installed: true }, history: [] }, saved: { reports: [], code: 'ready', skipped: 0, scan_truncated: false } }; break;
      case 'shareinventory': value = { files: [], skipped: 0, scan_truncated: false }; break;
      case 'sharednssources': value = { sources: [], warnings: [] }; break;
      case 'sharestrategydraft': value = { blocks: [{ key: 'NFQWS_ARGS', value: '--filter-tcp=443' }], config: initial }; break;
      case 'sharelocation': value = { available: false }; break;
      case 'shareanalyze': value = { config_sha256: 'a'.repeat(64), audit: { references: [], missing: [], unresolved: [], complete: true } }; break;
      case 'shareprepare': {
        if (previewFailures.length) {
          const error = previewFailures.shift();
          res.statusCode = error === 'invalid_proof' ? 403 : error === 'source_changed' ? 409 : 503;
          value = { error }; break;
        }
        const selection = JSON.parse(p.get('selection')); prepared++;
        assert.equal(selection.strategy.mode, 'config');
        assert.equal(selection.strategy.config, initial);
        const body = Buffer.from(JSON.stringify({ type: 'nfqws2_strategy', schema_version: 2, mode: 'config', config: initial, ...selection.context }));
        const file = { type: 'strategy', filename: `NFQWS2_STRATEGY_2026-11-01_11-00-0${prepared}Z.json`, byte_length: body.length, sha256: createHash('sha256').update(body).digest('hex'), data_base64: body.toString('base64') };
        previews.push(file);
        value = { version: 4, files: [file], source, proof: `v4.1000.${'a'.repeat(32)}.${'b'.repeat(64)}` };
        break;
      }
      case 'sharesend': {
        const envelope = JSON.parse(p.get('envelope')); sends.push(envelope);
        assert.deepEqual(envelope.files, [previews.at(-1)]);
        assert.equal(p.get('consent'), 'send');
        if (sends.length % 2 === 1) {
          previewFailures = ['unavailable', 'invalid_proof', 'source_changed'];
          res.statusCode = 503;
          value = { state: 'unknown', submission_id: envelope.submission_id, code: 'delivery_unknown' }; break;
        }
        value = { state: 'accepted', submission_id: envelope.submission_id, code: 'smtp_accepted' }; break;
      }
      default: errors.push(cmd); res.statusCode = 400; value = { error: 'unexpected_command' };
    }
    res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(value));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  browser = await chromium.launch({ headless: true, ...(process.env.NFQWS_CHROMIUM_EXECUTABLE ? { executablePath: process.env.NFQWS_CHROMIUM_EXECUTABLE } : {}) });
  for (const lang of ['ru', 'en']) {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 }, acceptDownloads: true });
    await page.addInitScript(() => { window.showSaveFilePicker = undefined; });
    page.setDefaultTimeout(5000);
    const pack = JSON.parse(await readFile(join(web, `src/translations/${lang}.json`), 'utf8'));
    await page.goto(`http://127.0.0.1:${server.address().port}/?${lang}`);
    await page.getByRole('checkbox', { name: pack.share.kinds.strategy, exact: true }).check();
    await page.getByRole('checkbox', { name: pack.share.full_config, exact: true }).check();
    await page.getByLabel(pack.share.purpose, { exact: false }).fill('YouTube');
    await page.getByLabel(pack.share.operator, { exact: false }).fill('Diagnostic ISP');
    const preview = page.getByRole('button', { name: pack.share.preview, exact: true }).first();
    const send = page.getByRole('button', { name: pack.share.send, exact: true });
    await preview.click(); await page.waitForFunction(button => !button.disabled, await send.elementHandle());
    assert.equal(await send.isEnabled(), true);
    const before = sends.length;
    await send.click();
    await page.getByText(pack.share.delivery_unknown, { exact: false }).waitFor();
    assert.equal(sends.length, before + 1, 'Uncertain result must not automatically send again');
    assert.equal(await send.isDisabled(), true, 'The uncertain snapshot remains locked');
    const download = page.getByRole('button', { name: pack.report.download, exact: true });
    assert.equal(await download.isEnabled(), true);
    const downloaded = page.waitForEvent('download'); await download.click(); await downloaded;
    assert.equal(await preview.isEnabled(), true, 'User must be able to prepare another attempt after a lost response');
    assert.equal(await page.getByLabel(pack.share.operator, { exact: false }).isEnabled(), true);
    assert.ok((await page.getByRole('dialog').innerText()).includes(sends.at(-1).submission_id), 'Show a reference the user can send to the developer');
    assert.doesNotMatch(await page.getByRole('dialog').innerText(), /формат v4|format v4/);
    for (const error of ['unavailable', 'invalid_proof', 'source_changed']) {
      await preview.click();
      const message = error === 'invalid_proof' ? 'forbidden' : error;
      await page.getByText(pack.share.errors[message], { exact: true }).waitFor();
      assert.equal(await download.isEnabled(), true, `Keep the old JSON after ${error}`);
      assert.ok((await page.getByRole('dialog').innerText()).includes(sends.at(-1).submission_id), `Keep the submission reference after ${error}`);
      assert.equal(await send.isDisabled(), true);
      assert.equal(sends.length, before + 1, 'Failed preparation must not send');
    }
    if (process.env.NFQWS_EXPORT_SCREENSHOT && lang === 'ru') await page.screenshot({ path: process.env.NFQWS_EXPORT_SCREENSHOT.replace('.png', '-unknown.png') });
    const count = sends.length;
    await preview.click();
    await page.waitForFunction(button => !button.disabled, await send.elementHandle()); assert.equal(await send.isEnabled(), true);
    assert.equal(sends.length, count, 'A fresh preview does not send');
    await send.click();
    await page.waitForFunction(() => document.body.dataset.accepted === 'yes');
    assert.equal(await send.isDisabled(), true, 'An accepted submission stays locked');
    assert.equal(await preview.isDisabled(), true);
    assert.equal(sends.length, count + 1);
    assert.notEqual(sends.at(-1).submission_id, sends.at(-2).submission_id);
    if (process.env.NFQWS_EXPORT_SCREENSHOT && lang === 'ru') await page.screenshot({ path: process.env.NFQWS_EXPORT_SCREENSHOT });
    await page.close();
  }
  assert.deepEqual(errors, []);
  console.log('PASS RU/EN initial strategy, lost response, saved JSON, explicit fresh preview/retry, exact bytes and accepted lock on mobile');
} finally {
  await browser?.close(); if (server) await new Promise(resolve => server.close(resolve)); await rm(dir, { recursive: true, force: true });
}

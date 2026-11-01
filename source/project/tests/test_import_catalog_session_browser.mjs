import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from '../webui/web/node_modules/esbuild/lib/main.js';

const { chromium } = await import(process.env.NFQWS_PLAYWRIGHT_MODULE || 'playwright');
const web = fileURLToPath(new URL('../webui/web/', import.meta.url));
const dir = await mkdtemp(join(tmpdir(), 'catalog-session-'));
let browser, server;
try {
  await build({
    stdin: { resolveDir: web, loader: 'tsx', contents: `
      import React, {useState} from 'react';import {createRoot} from 'react-dom/client';
      import {ImportCatalog} from './src/components/ImportCatalog';
      import {TranslationContext} from './src/context/TranslationContext';
      import en from './src/translations/en.json';
      const t=k=>k.split('.').reduce((v,p)=>v?.[p],en)||k;
      function Fixture(){const [csrf,setCsrf]=useState('old-session');
        window.changeCatalogSession=()=>setCsrf('new-session');
        return <TranslationContext.Provider value={{t,langcode:'en'}}>
          <ImportCatalog csrfToken={csrf} disabled={false} onSelect={()=>{throw Error('unexpected selection')}}/>
        </TranslationContext.Provider>;}
      createRoot(document.getElementById('root')).render(<Fixture/>);
    ` },
    bundle: true, platform: 'browser', format: 'iife', outfile: join(dir, 'fixture.js'),
    jsx: 'automatic', logLevel: 'silent', tsconfig: join(web, 'tsconfig.app.json'),
  });
  const script = await readFile(join(dir, 'fixture.js'));
  const en = JSON.parse(await readFile(join(web, 'src/translations/en.json'), 'utf8'));
  server = createServer((req, res) => {
    res.setHeader('Content-Type', req.url === '/fixture.js' ? 'text/javascript' : 'text/html');
    res.end(req.url === '/fixture.js' ? script : '<!doctype html><html><body><div id="root"></div><script src="/fixture.js"></script></body></html>');
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  browser = await chromium.launch({ headless: true, ...(process.env.NFQWS_CHROMIUM_EXECUTABLE ? { executablePath: process.env.NFQWS_CHROMIUM_EXECUTABLE } : {}) });
  const page = await browser.newPage(); page.setDefaultTimeout(3000);
  const pending = new Map();
  const arrivals = new Map();
  const arrived = token => pending.has(token) ? Promise.resolve(pending.get(token)) : new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(Error('No intercepted catalog request: ' + token)), 3000);
    arrivals.set(token, request => { clearTimeout(timeout); resolve(request); });
  });
  await page.route('**/index.php', async route => {
    const post = new URLSearchParams(route.request().postData());
    assert.equal(post.get('cmd'), 'importcatalog', 'session changes only reload the catalog');
    await new Promise(resolve => {
      const token = post.get('csrf_token'), request = { route, resolve };
      pending.set(token, request); arrivals.get(token)?.(request); arrivals.delete(token);
    });
  });
  const catalog = title => ({ schema_version: 1, revision: 1, build: 82, profiles: [{
    id: title.toLowerCase(), title, category: 'global', provider: '', region: '', description: 'Session fixture',
    attribution: '', updated_at: '2026-11-01T00:00:00Z', revision: 1, min_build: 68, size: 2, sha256: 'a'.repeat(64),
  }] });
  const reply = async (token, outcome) => {
    const request = await arrived(token); pending.delete(token);
    const response = page.waitForResponse(r => r.url().endsWith('/index.php') && new URLSearchParams(r.request().postData()).get('csrf_token') === token);
    const old = token === 'old-session';
    await request.route.fulfill({ status: outcome === 'error' ? 503 : 200, contentType: 'application/json', body: JSON.stringify(outcome === 'error' ? { error: old ? 'catalog_dns' : 'catalog_tls' } : catalog(old ? 'Old' : 'New')) });
    request.resolve(); await (await response).finished();
    await page.evaluate(() => new Promise(requestAnimationFrame));
  };
  const assertCurrent = async outcome => {
    if (outcome === 'success') await page.getByRole('button', { name: /^New/ }).waitFor();
    else await page.getByText(en.import.catalog.errors.catalog_tls, { exact: true }).waitFor();
    assert.equal(await page.getByRole('button', { name: /^Old/ }).count(), 0, 'old catalog never replaces the current result');
    assert.equal(await page.getByText(en.import.catalog.errors.catalog_dns, { exact: true }).count(), 0, 'old error never replaces the current result');
    assert.equal(await page.getByRole('button', { name: 'Refresh list', exact: true }).isEnabled(), true);
  };
  for (const old of ['success', 'error']) for (const current of ['success', 'error']) for (const oldFirst of [true, false]) {
    pending.clear();
    const initial = page.waitForRequest(r => r.url().endsWith('/index.php'));
    await page.goto(`http://127.0.0.1:${server.address().port}`); await initial;
    const next = page.waitForRequest(r => r.url().endsWith('/index.php') && new URLSearchParams(r.postData()).get('csrf_token') === 'new-session');
    await page.evaluate(() => window.changeCatalogSession());
    await next; // A new session must start even while the old request is pending.
    if (oldFirst) {
      await reply('old-session', old);
      assert.equal(await page.getByRole('button', { name: 'Refresh list', exact: true }).isDisabled(), true, 'old finally cannot clear current loading');
      assert.equal(await page.getByRole('progressbar').count(), 1);
      assert.equal(await page.getByRole('button', { name: /^Old/ }).count(), 0);
      assert.equal(await page.getByRole('alert').count(), 0, 'old failure stays invisible while current request is pending');
      await reply('new-session', current); await assertCurrent(current);
    } else {
      await reply('new-session', current); await assertCurrent(current);
      await reply('old-session', old); await assertCurrent(current);
    }
  }
  console.log('PASS catalog session races: new request starts while old pending; stale success/error cannot overwrite current data, error, or loading');
} finally {
  await browser?.close(); if (server) await new Promise(resolve => server.close(resolve));
  await rm(dir, { recursive: true, force: true });
}

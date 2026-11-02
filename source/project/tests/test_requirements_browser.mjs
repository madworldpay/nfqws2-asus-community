import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from '../webui/web/node_modules/esbuild/lib/main.js';

const { chromium } = await import(process.env.NFQWS_PLAYWRIGHT_MODULE || 'playwright');
const web = fileURLToPath(new URL('../webui/web/', import.meta.url));
const locales = Object.fromEntries(await Promise.all(['ru', 'en'].map(async language => [language, JSON.parse(await readFile(join(web, `src/translations/${language}.json`), 'utf8'))])));
const fixtures = new Map();
let browser, server;
try {
  // Render the real guide, translations, status hook and HTTP client. Only the
  // router's read-only status response is substituted; the fixture has no CSRF.
  const result = await build({ stdin: { resolveDir: web, loader: 'tsx', contents: `
    import React from 'react'; import {createRoot} from 'react-dom/client';
    import {QueryClientProvider} from '@tanstack/react-query';
    import {queryClient} from './src/api/client';
    import {RequirementsDialog} from './src/components/RequirementsDialog';
    import {Layout} from './src/components/Layout';
    createRoot(document.getElementById('root')).render(<QueryClientProvider client={queryClient}><Layout><RequirementsDialog onClose={()=>{}}/></Layout></QueryClientProvider>);
  ` }, bundle: true, platform: 'browser', format: 'iife', write: false, jsx: 'automatic',
    tsconfig: join(web, 'tsconfig.app.json'), logLevel: 'silent', define: { 'process.env.APP_VERSION': '"0.1.4"' } });
  server = createServer(async (req, res) => {
    if (req.method !== 'POST') {
      res.setHeader('Content-Type', req.url === '/fixture.js' ? 'text/javascript' : 'text/html');
      res.end(req.url === '/fixture.js' ? result.outputFiles[0].contents : '<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"></head><body><div id="root"></div><script src="/fixture.js"></script></body></html>');
      return;
    }
    const fixture = fixtures.get(req.headers['x-fixture']);
    let raw = ''; for await (const chunk of req) raw += chunk;
    const params = req.headers['content-type']?.startsWith('multipart/form-data')
      ? new URLSearchParams([...await new Response(raw, { headers: { 'Content-Type': req.headers['content-type'] } }).formData()].map(([key, value]) => [key, String(value)]))
      : new URLSearchParams(raw);
    fixture.calls.push(params.get('cmd'));
    res.setHeader('Content-Type', 'application/json');
    if (params.get('cmd') === 'status') {
      res.end(JSON.stringify({ status: 0, platform: fixture.platform, nfqws2: true, anonym: true, authenticated: false, version: '1.3.2-asus6+b84', service: false }));
    } else { res.statusCode = 400; res.end(JSON.stringify({ error: 'unexpected_command' })); }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  browser = await chromium.launch({ headless: true, ...(process.env.NFQWS_CHROMIUM_EXECUTABLE ? { executablePath: process.env.NFQWS_CHROMIUM_EXECUTABLE } : {}) });
  const failures = [];
  for (const language of ['ru', 'en']) for (const platform of ['asus-entware', 'openwrt']) {
    const id = `${language}-${platform}`, fixture = { platform, calls: [] };
    fixtures.set(id, fixture);
    const page = await browser.newPage({ viewport: { width: 1080, height: 800 }, extraHTTPHeaders: { 'x-fixture': id } });
    const errors = []; page.on('pageerror', error => errors.push(error.message));
    page.setDefaultTimeout(1500);
    await page.addInitScript(language => localStorage.setItem('lang', JSON.stringify(language)), language);
    try {
      await page.goto(`http://127.0.0.1:${server.address().port}/`);
      const pack = locales[language];
      const guide = page.getByRole('dialog', { name: pack.requirements.title, exact: true });
      if (platform === 'openwrt') await guide.getByRole('link', { name: 'OpenWrt', exact: true }).waitFor();
      await guide.getByRole('button', { name: pack.requirements.details, exact: true }).click();
      const ipGuidance = guide.getByText(pack.ip_health.title, { exact: false });
      if (platform === 'asus-entware') await ipGuidance.waitFor();
      else assert.equal(await ipGuidance.count(), 0, 'OpenWrt must not offer the ASUS-only address feature');
      assert.deepEqual(fixture.calls, ['status'], 'opening the guide must not configure or start services');
      assert.deepEqual(errors, []);
      console.log(`PASS ${id}: platform-specific guide, read-only opening`);
    } catch (error) { failures.push(`${id}: ${error.message}`); console.error(`FAIL ${id}: ${error.message}`); if (process.env.NFQWS_GUIDE_DEBUG) console.error(JSON.stringify({ calls: fixture.calls, errors, body: await page.locator('body').innerText() })); }
    finally { await page.close(); }
  }
  assert.deepEqual(failures, []);
} finally { await browser?.close(); await new Promise(resolve => server ? server.close(resolve) : resolve()); }

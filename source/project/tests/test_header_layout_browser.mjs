import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { createServer } from 'node:http';
import { mkdir, readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { build } from '../webui/web/node_modules/esbuild/lib/main.js';

const { chromium } = await import(process.env.NFQWS_PLAYWRIGHT_MODULE || 'playwright');
const web = fileURLToPath(new URL('../webui/web/', import.meta.url));
const compact = await readFile(new URL('../webui/web/public/compact-viewport.css', import.meta.url));
const measuredOnly = process.env.NFQWS_HEADER_MEASURED_IMPORT === '1';
const measured = { id: '7'.repeat(32), result: '8'.repeat(32) };
const measuredRaw = '{"fixture":"sealed measurement from the first round"}';
const measuredHash = createHash('sha256').update(measuredRaw).digest('hex');
const calls = [];
const bundle = await build({ stdin: { resolveDir: web, loader: 'tsx', contents: `
  import React from 'react'; import {createRoot} from 'react-dom/client';
  import {QueryClientProvider} from '@tanstack/react-query';
  import {createRootRoute,createRouter,RouterProvider} from '@tanstack/react-router';
  import {queryClient} from './src/api/client'; import {Header} from './src/components/Header';
  import {Layout} from './src/components/Layout'; import {useAppStore} from './src/store/useAppStore';
  useAppStore.setState({auth:true});
  const routeTree=createRootRoute({component:()=> <Header/>});
  const router=createRouter({routeTree});
  createRoot(document.getElementById('root')).render(<QueryClientProvider client={queryClient}><Layout><RouterProvider router={router}/></Layout></QueryClientProvider>);
` }, bundle: true, platform: 'browser', format: 'iife', write: false, outfile: '/fixture.js', jsx: 'automatic', external: ['/community/*'],
tsconfig: web + '/tsconfig.app.json', logLevel: 'silent', define: { 'process.env.APP_VERSION': '"0.1.4"' } });
let server, browser;
try {
  server = createServer(async (req, res) => {
    if (req.method !== 'POST') {
      if (/^\/community\/[A-Za-z0-9_.-]+$/.test(req.url)) {
        try { res.setHeader('Content-Type', req.url.endsWith('.webp') ? 'image/webp' : 'image/png'); res.end(await readFile(new URL('../webui/web/public' + req.url, import.meta.url))); }
        catch { res.statusCode = 404; res.end(); }
        return;
      }
      const file = bundle.outputFiles.find(file => file.path.endsWith(req.url));
      res.setHeader('Content-Type', req.url.endsWith('.js') ? 'text/javascript' : req.url.endsWith('.css') ? 'text/css' : 'text/html');
      res.end(req.url === '/compact.css' ? compact : file ? file.contents : '<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"><link rel="stylesheet" href="/fixture.css"><link rel="stylesheet" href="/compact.css"></head><body><div id="root"></div><script src="/fixture.js"></script></body></html>');
      return;
    }
    let raw = ''; for await (const chunk of req) raw += chunk;
    const params = req.headers['content-type']?.startsWith('multipart/form-data')
      ? new URLSearchParams([...await new Response(raw, { headers: { 'Content-Type': req.headers['content-type'] } }).formData()].map(([key, value]) => [key, String(value)]))
      : new URLSearchParams(raw);
    res.setHeader('Content-Type', 'application/json');
    const cmd = params.get('cmd');
    if (measuredOnly) calls.push(Object.fromEntries(params));
    if (cmd === 'status') res.end(JSON.stringify({ status: 0, platform: req.headers['x-platform'], nfqws2: true, anonym: true, authenticated: false, csrf_token: 'fixture', version: '1.3.2-88', service: false }));
    else if (measuredOnly && cmd === 'pickerexport') res.end(JSON.stringify({
      raw: measuredRaw, sha256: req.headers['x-damaged'] ? '0'.repeat(64) : measuredHash,
      filename: `NFQWS2_MEASURED_${measured.result}.json`,
    }));
    else if (measuredOnly && cmd === 'importstatus') res.end(JSON.stringify({
      state: 'idle', id: null, can_undo: false, config_saved: false, dns_draft_saved: false,
    }));
    else if (measuredOnly && cmd === 'importinspect') res.end(JSON.stringify({
      values: { NFQWS_ARGS: '--filter-tcp=443' }, ports: {}, resources: [],
      dns_sources: [], context: { purpose: 'Замер из первого прогона' },
      source: null, ignored: [], input_sha256: measuredHash,
    }));
    else if (measuredOnly && cmd === 'importprepare') res.end(JSON.stringify({
      ready: true, problems: [], warnings: [], required: { files: [], shared: [] },
      affected_blocks: [], config: 'fixture', changes: [{ key: 'NFQWS_ARGS', before: '', after: '--filter-tcp=443' }],
      files: [], draft: null, old_draft: null, digest: measuredHash, proof: 'fixture',
    }));
    else { res.statusCode = 400; res.end(JSON.stringify({ error: 'unexpected_command' })); }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  browser = await chromium.launch({ headless: true, ...(process.env.NFQWS_CHROMIUM_EXECUTABLE ? { executablePath: process.env.NFQWS_CHROMIUM_EXECUTABLE } : {}) });
  if (measuredOnly) for (const damaged of [false, true]) {
    calls.length = 0;
    const page = await browser.newPage({ extraHTTPHeaders: {
      'x-platform': 'asus-entware', ...(damaged ? { 'x-damaged': '1' } : {}),
    } });
    page.setDefaultTimeout(6000);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.addInitScript(ref => {
      sessionStorage.setItem('nfqws-picker-import-v1', JSON.stringify(ref));
      localStorage.setItem('lang', JSON.stringify('ru'));
    }, measured);
    await page.goto(`http://127.0.0.1:${server.address().port}/?picker-import=1`);
    const dialog = page.getByRole('dialog', { name: 'Импорт профиля' });
    await dialog.waitFor();
    const preview = dialog.getByRole('button', { name: 'Предпросмотр', exact: true }).filter({ hasText: 'Предпросмотр' });
    const save = dialog.getByRole('button', { name: 'Сохранить выбранное', exact: true }).filter({ hasText: 'Сохранить выбранное' });
    if (damaged) {
      await dialog.getByRole('alert').waitFor();
      assert.equal(await preview.isEnabled(), false);
      assert.equal(calls.some(p => p.cmd === 'importinspect'), false);
    } else {
      await preview.and(page.locator(':enabled')).waitFor();
      assert.deepEqual(calls.filter(p => p.cmd === 'pickerexport'), [
        { cmd: 'pickerexport', csrf_token: 'fixture', ...measured },
      ]);
      assert.deepEqual(calls.filter(p => p.cmd === 'importinspect').map(p => JSON.parse(p.documents)), [[measuredRaw]]);
      assert.equal(calls.some(p => p.cmd === 'importprepare'), false);
      assert.equal(await save.isEnabled(), false);
      await preview.click();
      await save.and(page.locator(':enabled')).waitFor();
      assert.deepEqual(calls.filter(p => p.cmd === 'importprepare').map(p => JSON.parse(p.documents)), [[measuredRaw]]);
    }
    assert.equal(calls.some(p => p.cmd === 'importapply' || p.cmd === 'pickerapply'), false);
    assert.equal(await page.evaluate(() => sessionStorage.getItem('nfqws-picker-import-v1')), null);
    assert.deepEqual(errors, []);
    await page.close();
    console.log(damaged ? 'PASS refused a damaged measurement document' : 'PASS explicit Import preview for a sealed earlier measurement');
  }
  const platforms = process.env.NFQWS_HEADER_PLATFORM ? [process.env.NFQWS_HEADER_PLATFORM] : ['asus-entware', 'openwrt'];
  assert.ok(platforms.every(value => ['asus-entware', 'openwrt'].includes(value)));
  for (const platform of measuredOnly ? [] : platforms) for (const language of ['ru', 'en']) for (const appearance of ['rabbit', 'classic']) {
    const page = await browser.newPage({ extraHTTPHeaders: { 'x-platform': platform } });
    const errors = []; page.on('pageerror', error => errors.push(error.message));
    await page.addInitScript(({ language, appearance }) => { localStorage.setItem('lang', JSON.stringify(language)); localStorage.setItem('nfqws2-appearance', appearance); }, { language, appearance });
    for (const viewport of [{ width: 1306, height: 900 }, { width: 1024, height: 768 }, { width: 390, height: 844 }, { width: 844, height: 390 }, { width: 1024, height: 500 }]) {
      await page.setViewportSize(viewport);
      await page.goto(`http://127.0.0.1:${server.address().port}/`);
      await page.locator('header .MuiChip-root').waitFor();
      await page.getByRole('button', { name: 'DPI Detector', exact: true }).waitFor();
      await page.locator('header button img').evaluateAll(images=>Promise.all(images.map(image=>image.decode())));
      const result = await page.locator('header').evaluate(header => {
        const controls = [...header.querySelectorAll('button:not(.rabbit-build-video-trigger),.MuiChip-root')].map(node => { const r = node.getBoundingClientRect(); return { text: node.getAttribute('aria-label') || node.textContent, chip: node.classList.contains('MuiChip-root'), x: r.x, y: r.y, width: r.width, height: r.height }; });
        const sprites = [...header.querySelectorAll('.rabbit-build-sprite')].map(node => { const r = node.getBoundingClientRect(); return { display: getComputedStyle(node).display, top: r.top, bottom: r.bottom }; });
        const r = header.getBoundingClientRect();
        const transfers = [...header.querySelectorAll('button img')].map(image => {
          const r = image.getBoundingClientRect();
          return { src: image.getAttribute('src'), loaded: image.complete && image.naturalWidth > 0, width: r.width, height: r.height };
        });
        return { controls, sprites, transfers, width: document.documentElement.clientWidth, top: r.top, bottom: r.bottom };
      });
      const label = `${platform}/${language}/${appearance}/${viewport.width}x${viewport.height}`;
      assert.ok(result.controls.length >= 10, `${label}: real authorized header controls rendered`);
      for (const name of ['import-937c2946.png', 'export-e9a226cd.png']) {
        const image = result.transfers.find(value => value.src.endsWith(name));
        assert.ok(image?.loaded && image.width >= 28 && image.height >= 28, `${label}: visible loaded rabbit for ${name}`);
      }
      for (const control of result.controls) {
        assert.ok(Math.abs(control.height - 36) <= 1, `${label}: ${control.text} height ${control.height}`);
        assert.ok(control.x >= -1 && control.x + control.width <= result.width + 1, `${label}: ${control.text} fits the viewport`);
      }
      const chip = result.controls.find(control => control.chip);
      assert.ok(result.controls.some(control => !control.chip && Math.abs(control.y - chip.y) <= 1), `${label}: Build shares a button row`);
      const rows = [...new Set(result.controls.map(control => Math.round(control.y)))].sort((a, b) => a - b);
      for (let i = 1; i < rows.length; i++) assert.ok(rows[i] - rows[i - 1] <= 45, `${label}: adjacent control rows have compact gaps ${rows}`);
      if (appearance === 'rabbit') {
        assert.ok(result.sprites.length && result.sprites.every(sprite => sprite.display === 'block'), `${label}: rabbit visible`);
        assert.ok(result.sprites.every(sprite => sprite.top >= result.top && sprite.bottom <= result.bottom), `${label}: artwork remains inside the header`);
      }
      if (process.env.NFQWS_HEADER_SCREENSHOT_DIR && platform === (process.env.NFQWS_HEADER_PLATFORM || 'openwrt') && language === 'ru' && appearance === 'rabbit') {
        await mkdir(process.env.NFQWS_HEADER_SCREENSHOT_DIR, { recursive: true });
        await page.locator('header').screenshot({ path: `${process.env.NFQWS_HEADER_SCREENSHOT_DIR}/header-${viewport.width}x${viewport.height}.png` });
      }
      assert.deepEqual(errors, [], label);
      console.log(`PASS ${label}: uniform controls, Build alignment, compact rows, rabbit visibility`);
    }
    await page.close();
  }
} finally { await browser?.close(); if (server) await new Promise(resolve => server.close(resolve)); }

import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { mkdir, readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { build } from '../webui/web/node_modules/esbuild/lib/main.js';

const { chromium } = await import(process.env.NFQWS_PLAYWRIGHT_MODULE || 'playwright');
const web = fileURLToPath(new URL('../webui/web/', import.meta.url));
const compact = await readFile(new URL('../webui/web/public/compact-viewport.css', import.meta.url));
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
    if (params.get('cmd') === 'status') res.end(JSON.stringify({ status: 0, platform: req.headers['x-platform'], nfqws2: true, anonym: true, authenticated: false, csrf_token: 'fixture', version: '1.3.2-88', service: false }));
    else { res.statusCode = 400; res.end(JSON.stringify({ error: 'unexpected_command' })); }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  browser = await chromium.launch({ headless: true, ...(process.env.NFQWS_CHROMIUM_EXECUTABLE ? { executablePath: process.env.NFQWS_CHROMIUM_EXECUTABLE } : {}) });
  for (const platform of ['asus-entware', 'openwrt']) for (const language of ['ru', 'en']) for (const appearance of ['rabbit', 'classic']) {
    const page = await browser.newPage({ extraHTTPHeaders: { 'x-platform': platform } });
    const errors = []; page.on('pageerror', error => errors.push(error.message));
    await page.addInitScript(({ language, appearance }) => { localStorage.setItem('lang', JSON.stringify(language)); localStorage.setItem('nfqws2-appearance', appearance); }, { language, appearance });
    for (const viewport of [{ width: 1306, height: 900 }, { width: 1024, height: 768 }, { width: 390, height: 844 }, { width: 844, height: 390 }, { width: 1024, height: 500 }]) {
      await page.setViewportSize(viewport);
      await page.goto(`http://127.0.0.1:${server.address().port}/`);
      await page.locator('header .MuiChip-root').waitFor();
      await page.getByRole('button', { name: 'DPI Detector', exact: true }).waitFor();
      const result = await page.locator('header').evaluate(header => {
        const controls = [...header.querySelectorAll('button,.MuiChip-root')].map(node => { const r = node.getBoundingClientRect(); return { text: node.getAttribute('aria-label') || node.textContent, chip: node.classList.contains('MuiChip-root'), x: r.x, y: r.y, width: r.width, height: r.height }; });
        const sprites = [...header.querySelectorAll('.rabbit-build-sprite')].map(node => { const r = node.getBoundingClientRect(); return { display: getComputedStyle(node).display, top: r.top, bottom: r.bottom }; });
        const r = header.getBoundingClientRect();
        return { controls, sprites, width: document.documentElement.clientWidth, top: r.top, bottom: r.bottom };
      });
      const label = `${platform}/${language}/${appearance}/${viewport.width}x${viewport.height}`;
      assert.ok(result.controls.length >= 10, `${label}: real authorized header controls rendered`);
      for (const control of result.controls) {
        assert.ok(Math.abs(control.height - 36) <= 1, `${label}: ${control.text} height ${control.height}`);
        assert.ok(control.x >= -1 && control.x + control.width <= result.width + 1, `${label}: ${control.text} fits the viewport`);
      }
      const chip = result.controls.find(control => control.chip);
      assert.ok(result.controls.some(control => !control.chip && Math.abs(control.y - chip.y) <= 1), `${label}: Build shares a button row`);
      const rows = [...new Set(result.controls.map(control => Math.round(control.y)))].sort((a, b) => a - b);
      for (let i = 1; i < rows.length; i++) assert.ok(rows[i] - rows[i - 1] <= 45, `${label}: adjacent control rows have compact gaps ${rows}`);
      if (appearance === 'rabbit') {
        const compact = viewport.width < 600 || viewport.height <= 600;
        assert.ok(result.sprites.every(sprite => sprite.display === (compact ? 'none' : 'block')), `${label}: desktop rabbit retained, compact rabbit hidden`);
        if (!compact) assert.ok(result.sprites.every(sprite => sprite.top >= result.top && sprite.bottom <= result.bottom), `${label}: desktop artwork remains inside the header`);
      }
      if (process.env.NFQWS_HEADER_SCREENSHOT_DIR && platform === 'openwrt' && language === 'ru' && appearance === 'rabbit') {
        await mkdir(process.env.NFQWS_HEADER_SCREENSHOT_DIR, { recursive: true });
        await page.locator('header').screenshot({ path: `${process.env.NFQWS_HEADER_SCREENSHOT_DIR}/header-${viewport.width}x${viewport.height}.png` });
      }
      assert.deepEqual(errors, [], label);
      console.log(`PASS ${label}: uniform controls, Build alignment, compact rows, rabbit visibility`);
    }
    await page.close();
  }
} finally { await browser?.close(); if (server) await new Promise(resolve => server.close(resolve)); }

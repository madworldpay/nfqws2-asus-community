import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from '../webui/web/node_modules/esbuild/lib/main.js';

// Real component, browser events and layout; no report sender or router API.
const { chromium } = await import(process.env.NFQWS_PLAYWRIGHT_MODULE || 'playwright');
const web = fileURLToPath(new URL('../webui/web/', import.meta.url));
const dir = await mkdtemp(join(tmpdir(), 'nfqws-frank-browser-'));
let browser;
let server;
try {
  await build({ stdin: { resolveDir: web, loader: 'tsx', contents: `
    import React from 'react'; import {createRoot} from 'react-dom/client';
    import {TranslationContext} from './src/context/TranslationContext';
    import ru from './src/translations/ru.json'; import {ShareThanks} from './src/components/ShareThanks';
    const t=(key)=>key.split('.').reduce((v,k)=>v?.[k],ru)||key;
    function Fixture(){const [event,setEvent]=React.useState(0);const [serial,setSerial]=React.useState(0);
      return <TranslationContext.Provider value={{t}}>
        <button onClick={()=>{setSerial(n=>n+1);setEvent(serial+1)}}>New accepted send</button>
        <ShareThanks appearance="rabbit" event={event} onClose={()=>setEvent(0)}/>
      </TranslationContext.Provider>}
    createRoot(document.getElementById('root')).render(<Fixture/>);
  ` }, bundle: true, platform: 'browser', format: 'iife', outfile: join(dir, 'fixture.js'),
  jsx: 'automatic', logLevel: 'silent', tsconfig: join(web, 'tsconfig.app.json') });
  const script = await readFile(join(dir, 'fixture.js'));
  const gif = await readFile(join(web, 'public/community/rabbit-respect-once.gif'));
  server = createServer((req, res) => {
    const path = req.url.split('?')[0];
    if (path === '/fixture.js') { res.setHeader('Content-Type', 'text/javascript'); res.end(script); }
    else if (path === '/community/rabbit-respect-once.gif') { res.setHeader('Content-Type', 'image/gif'); res.end(gif); }
    else { res.setHeader('Content-Type', 'text/html'); res.end('<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"></head><body style="margin:0;min-height:300vh;background:#0b1119"><div id="root"></div><script src="/fixture.js"></script></body></html>'); }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  browser = await chromium.launch({ headless: true, ...(process.env.NFQWS_CHROMIUM_EXECUTABLE ? { executablePath: process.env.NFQWS_CHROMIUM_EXECUTABLE } : {}) });
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  page.setDefaultTimeout(4000);
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  const image = page.locator('img[src*="rabbit-respect-once.gif"]');
  assert.equal(await image.count(), 0, 'No approval before accepted send');
  await page.getByRole('button', { name: 'New accepted send' }).click();
  const frank = page.getByRole('button', { name: 'Фрэнк', exact: true });
  await frank.waitFor();
  assert.equal(await page.getByRole('status').innerText(), 'Фрэнк одобряет...');
  const initial = await image.getAttribute('src');
  for (let i = 0; i < 27; i++) await frank.click();
  assert.equal(await image.getAttribute('src'), initial, '27 clicks must not replay');
  assert.equal(await page.getByRole('status').innerText(), 'Фрэнк одобряет...');
  await frank.click();
  const replay = await image.getAttribute('src');
  assert.notEqual(replay, initial, 'The 28th click replays the existing one-shot GIF');
  assert.equal(await page.getByRole('status').innerText(), 'Фрэнк наблюдает...');
  for (let i = 0; i < 28; i++) await frank.click();
  assert.notEqual(await image.getAttribute('src'), replay, 'Each subsequent group of 28 replays once');
  for (const [width, height] of [[1280, 720], [2560, 1440], [3840, 2160]]) {
    await page.setViewportSize({ width, height });
    await page.evaluate(() => window.scrollTo(0, 400));
    const box = await page.getByRole('status').boundingBox();
    assert.ok(Math.abs(box.x + box.width / 2 - width / 2) < 2, `Centered horizontally at ${width}`);
    assert.ok(Math.abs(box.y + box.height / 2 - height / 2) < 2, `Centered vertically at ${width}`);
  }
  if (process.env.NFQWS_FRANK_SCREENSHOT) await page.screenshot({ path: process.env.NFQWS_FRANK_SCREENSHOT });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.getByRole('button', { name: 'Закрыть', exact: true }).click();
  assert.equal(await image.count(), 0, 'Close still works');
  await page.getByRole('button', { name: 'New accepted send' }).click();
  assert.equal(await page.getByRole('status').innerText(), 'Фрэнк одобряет...');
  const fresh = await image.getAttribute('src');
  for (let i = 0; i < 27; i++) await frank.click();
  assert.equal(await image.getAttribute('src'), fresh, 'New send resets the counter');
  console.log('Frank: 28-click replay, caption, reset, close and viewport center at HD/2K/4K: PASS');
} finally {
  await browser?.close();
  if (server) await new Promise(resolve => server.close(resolve));
  await rm(dir, { recursive: true, force: true });
}

import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { fileURLToPath } from 'node:url';
import { build } from '../webui/web/node_modules/esbuild/lib/main.js';
const { chromium } = await import(process.env.NFQWS_PLAYWRIGHT_MODULE || 'playwright');
const web = fileURLToPath(new URL('../webui/web/', import.meta.url));
let browser, server;
try {
  const result = await build({ stdin: { resolveDir: web, loader: 'tsx', contents: `
    import React,{useRef,useState}from'react';import{createRoot}from'react-dom/client';
    import{Layout}from'./src/components/Layout';import{BlobPicker}from'./src/components/BlobPicker';import{Editor}from'./src/components/Editor';
    const initial='--debug=0 --blob=tls:@/opt/etc/nfqws2/blobs/old.bin';
    function Fixture(){const[value,setValue]=useState(initial),[revision,setRevision]=useState(0),ref=useRef(initial);const edit=v=>{ref.current=v;setValue(v)};const replace=v=>{edit(v);setRevision(r=>r+1)};return <Layout><BlobPicker value={value} getValue={()=>ref.current} onChange={replace}/><Editor key={revision} type='arg' value={value} onChange={edit}/><output id='draft'>{value}</output><button onClick={()=>replace(initial)}>Reset fixture</button><button onClick={()=>edit(initial+' --props=1')}>External props fixture</button></Layout>}
    createRoot(document.getElementById('root')).render(<Fixture/>);
  ` }, bundle: true, platform: 'browser', format: 'iife', write: false, jsx: 'automatic', logLevel: 'silent', tsconfig: joinPath(web, 'tsconfig.app.json'), plugins: [{ name: 'status-boundary', setup(b) { b.onLoad({ filter: /hooks\/useStatus\.tsx$/ }, () => ({ contents: 'export const useStatus=()=>({csrfToken:"fixture-csrf"});', loader: 'tsx' })); } }] });
  server = createServer((req, res) => { res.setHeader('Content-Type', req.url === '/fixture.js' ? 'text/javascript' : 'text/html'); res.end(req.url === '/fixture.js' ? result.outputFiles[0].contents : '<!doctype html><html><body><div id="root"></div><script src="/fixture.js"></script></body></html>'); });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  browser = await chromium.launch({ headless: true, ...(process.env.NFQWS_CHROMIUM_EXECUTABLE ? { executablePath: process.env.NFQWS_CHROMIUM_EXECUTABLE } : {}) });
  const page = await browser.newPage({ locale: 'en-US' }); page.setDefaultTimeout(5000);
  await page.route('**/index.php', async route => {
    assert.equal(new URLSearchParams(route.request().postData()).get('cmd'), 'blobinventory');
    const files = ['old.bin', 'new.bin'].map(name => ({ name, path: '/opt/etc/nfqws2/blobs/' + name, byte_length: 1, sha256: 'a'.repeat(64), state: 'available', format: 'tls', label: null, bundled: false }));
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ files, skipped: 0, scan_truncated: false }) });
  });
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  const editor = page.locator('.cm-content'), draft = page.locator('#draft');
  await editor.waitFor(); const initial = await draft.textContent();
  const typeAndUndo = async expected => {
    await page.waitForFunction(value => document.querySelector('.cm-content').textContent === value, expected);
    await editor.click(); await page.keyboard.press('End'); await page.keyboard.type(' --debug=9');
    await page.waitForFunction(value => document.querySelector('#draft').textContent === value + ' --debug=9', expected);
    await page.keyboard.press('Control+z');
    await page.waitForFunction(value => document.querySelector('#draft').textContent === value, expected);
  };
  await typeAndUndo(initial);
  await page.getByRole('button', { name: 'Packet templates (blobs)', exact: true }).click();
  await page.getByRole('combobox').selectOption('/opt/etc/nfqws2/blobs/new.bin');
  const selected = initial.replace('/old.bin', '/new.bin');
  await page.waitForFunction(value => document.querySelector('#draft').textContent === value, selected);
  await typeAndUndo(selected);
  await page.keyboard.press('Control+z');
  assert.equal(await draft.textContent(), selected, 'External blob choice starts a fresh undo baseline');
  await page.getByRole('button', { name: 'Reset fixture', exact: true }).click();
  await typeAndUndo(initial);
  await page.getByRole('button', { name: 'External props fixture', exact: true }).click();
  await typeAndUndo(initial + ' --props=1');
  await page.keyboard.press('Control+z');
  assert.equal(await draft.textContent(), initial + ' --props=1', 'Delayed external props also establish a fresh undo baseline');
  console.log('PASS actual controlled CodeMirror: local typing remains undoable; blob selection and reset refresh props and establish a fresh history baseline');
} finally { await browser?.close(); if (server) await new Promise(resolve => server.close(resolve)); }
function joinPath(root, file) { return root + file; }

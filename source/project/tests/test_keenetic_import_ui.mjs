import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { fileURLToPath } from 'node:url';
import { build } from '../webui/web/node_modules/esbuild/lib/main.js';
const { chromium } = await import(process.env.NFQWS_PLAYWRIGHT_MODULE || 'playwright');
const web = fileURLToPath(new URL('../webui/web/', import.meta.url));
let browser, server;
try {
  const result = await build({ stdin: { resolveDir: web, loader: 'tsx', contents: `
    import React from'react';import{createRoot}from'react-dom/client';import{Layout}from'./src/components/Layout';import{ImportDialog}from'./src/components/ImportDialog';
    createRoot(document.getElementById('root')).render(<Layout><ImportDialog onClose={()=>{}}/></Layout>);
  ` }, bundle: true, platform: 'browser', format: 'iife', write: false, jsx: 'automatic', logLevel: 'silent', tsconfig: web + 'tsconfig.app.json', plugins: [{ name: 'status-boundary', setup(b) { b.onLoad({ filter: /hooks\/useStatus\.tsx$/ }, () => ({ contents: 'export const useStatus=()=>({csrfToken:"fixture-csrf"});', loader: 'tsx' })); } }] });
  server = createServer((req, res) => { res.setHeader('Content-Type', req.url === '/fixture.js' ? 'text/javascript' : 'text/html'); res.end(req.url === '/fixture.js' ? result.outputFiles[0].contents : '<!doctype html><html><body><div id="root"></div><script src="/fixture.js"></script></body></html>'); });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  browser = await chromium.launch({ headless: true, ...(process.env.NFQWS_CHROMIUM_EXECUTABLE ? { executablePath: process.env.NFQWS_CHROMIUM_EXECUTABLE } : {}) });
  const page = await browser.newPage({ locale: 'ru-RU' }); page.setDefaultTimeout(5000);
  const calls = [], texts = [], selections = [];
  const converted = '{"type":"nfqws2_strategy","schema_version":1,"fixture":"converted"}';
  const after = '--filter-tcp=443 --hostlist=/opt/etc/nfqws2/lists/missing.list';
  const document = { values: { NFQWS_ARGS: after }, ports: {}, resources: [], dns_sources: [], context: null, source: null, ignored: [], input_sha256: 'b'.repeat(64) };
  let unsupported = false;
  await page.route('**/index.php', async route => {
    const post = Object.fromEntries(new URLSearchParams(route.request().postData())); calls.push(post.cmd); assert.equal(post.csrf_token, 'fixture-csrf');
    let body, status = 200;
    if (post.cmd === 'importstatus') body = { state: 'idle', id: null, can_undo: false, config_saved: false, dns_draft_saved: false };
    else if (post.cmd === 'importconvert') { texts.push(post.text); if (unsupported) { status = 422; body = { error: 'unsupported_keenetic_strategy' }; } else body = { document: converted }; }
    else if (post.cmd === 'importinspect') { assert.deepEqual(JSON.parse(post.documents), [converted]); body = document; }
    else if (post.cmd === 'importprepare') { assert.deepEqual(JSON.parse(post.documents), [converted]); selections.push(JSON.parse(post.selection)); body = { ready: false, problems: [{ code: 'unresolved_file', key: 'NFQWS_ARGS', name: 'missing.list' }], warnings: [], required: { files: [], shared: [] }, affected_blocks: [], config: '', changes: [{ key: 'NFQWS_ARGS', before: '--filter-tcp=80', after }], files: [], draft: null, old_draft: null, digest: 'e'.repeat(64), proof: null }; }
    else throw new Error('Unexpected mutation or request: ' + post.cmd);
    await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
  });
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  await page.getByRole('button', { name: 'Вставить стратегию Keenetic', exact: true }).click();
  await page.getByText('Вставьте текст стратегии NFQWS2 с Keenetic. Пути к файлам будут адаптированы под ASUS. Проверьте результат перед сохранением.', { exact: true }).waitFor();
  assert.equal(calls.includes('importconvert'), false, 'Opening the editor never starts conversion');
  const editor = page.locator('.cm-content').first();
  const text = '--filter-tcp=443 --hostlist=/opt/etc/nfqws/user.list\n--lua-desync=fake:blob=tls';
  await editor.click(); await page.keyboard.insertText(text);
  assert.ok(await editor.locator('.cm-line span').count() > 0, 'Pasted strategy uses the real NFQWS CodeMirror syntax');
  await page.getByRole('button', { name: 'Преобразовать под ASUS', exact: true }).dblclick();
  await page.getByText('Нужного файла нет на роутере: missing.list', { exact: true }).waitFor();
  assert.deepEqual(texts, [text]);
  assert.deepEqual(calls, ['importstatus', 'importconvert', 'importinspect', 'importprepare']);
  assert.deepEqual(selections[0].blocks, [{ key: 'NFQWS_ARGS', value: after }]);
  assert.equal(await page.getByRole('checkbox', { name: 'Базовая стратегия', exact: true }).isChecked(), true);
  assert.equal(await page.getByRole('button', { name: 'Сохранить выбранное', exact: true }).isDisabled(), true);
  await page.getByRole('button', { name: 'Базовая стратегия', exact: true }).click();
  await page.getByText('Было', { exact: true }).waitFor(); await page.getByText('Станет', { exact: true }).waitFor();
  assert.ok(await page.locator('pre').filter({ hasText: after }).count() > 0);
  unsupported = true;
  await editor.click(); await page.keyboard.press('Control+a'); await page.keyboard.insertText('--dpi-desync=fake');
  assert.equal(await page.getByText('Нужного файла нет на роутере: missing.list', { exact: true }).count(), 0, 'Editing pasted text invalidates the previous preview');
  await page.getByRole('button', { name: 'Преобразовать под ASUS', exact: true }).click();
  await page.getByText('Не удалось преобразовать этот формат. Нужна текстовая стратегия NFQWS2 без команд оболочки.', { exact: true }).waitFor();
  assert.equal(await editor.textContent(), '--dpi-desync=fake', 'Conversion errors keep the pasted text');
  assert.equal(calls.includes('importapply'), false);
  await page.evaluate(() => localStorage.setItem('lang', JSON.stringify('en'))); await page.reload();
  await page.getByRole('button', { name: 'Paste a Keenetic strategy', exact: true }).click();
  await page.getByRole('button', { name: 'Convert for ASUS', exact: true }).waitFor();
  console.log('PASS real Keenetic paste UI: existing CodeMirror syntax, convert→inspect→select all→automatic before/after preview, named missing file blocks Apply, edited/error input preserved, RU/EN and no automatic mutation');
} finally { await browser?.close(); if (server) await new Promise(resolve => server.close(resolve)); }

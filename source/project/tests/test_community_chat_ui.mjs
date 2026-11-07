import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { fileURLToPath } from 'node:url';
import { build } from '../webui/web/node_modules/esbuild/lib/main.js';

const { chromium } = await import(process.env.NFQWS_PLAYWRIGHT_MODULE || 'playwright');
const web = fileURLToPath(new URL('../webui/web/', import.meta.url));
const chat = 'https://t.me/nfqws2AsusCommunityChat';
let browser, server;
try {
  const bundle = await build({
    stdin: { resolveDir: web, loader: 'tsx', contents: `
import React from 'react';import{createRoot}from'react-dom/client';
import{Layout}from'./src/components/Layout';import{PackageUpdateDialog}from'./src/components/PackageUpdateDialog';
const succeeded=new URLSearchParams(location.search).get('state')!=='failed';
const updates={pending:false,error:null,data:{check:{state:'current'},operation:{state:succeeded?'succeeded':'failed',package_version:'1.3.2-asus6+b80',installed_version:'1.3.2-asus6+b80',code:succeeded?null:'request_failed'}},refresh(){},prepare(){},apply(){}};
createRoot(document.getElementById('root')).render(<Layout><PackageUpdateDialog open onClose={()=>{}} installed="1.3.2-asus6+b80" updates={updates}/></Layout>);
` },
    bundle: true, platform: 'browser', format: 'iife', write: false,
    jsx: 'automatic', logLevel: 'silent', tsconfig: web+'tsconfig.app.json', loader: {'.sh':'text','.py':'text'},
  });
  server = createServer((req, res) => {
    res.setHeader('Content-Type', req.url === '/fixture.js' ? 'text/javascript' : 'text/html');
    res.end(req.url === '/fixture.js' ? bundle.outputFiles[0].contents : '<!doctype html><html><body><div id="root"></div><script src="/fixture.js"></script></body></html>');
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  browser = await chromium.launch({headless:true,...(process.env.NFQWS_CHROMIUM_EXECUTABLE ? {executablePath:process.env.NFQWS_CHROMIUM_EXECUTABLE} : {})});
  const page = await browser.newPage({locale:'ru-RU'});
  page.setDefaultTimeout(5000);
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'clipboard', {value:undefined});
    window.copied = [];
    document.execCommand = command => {
      const input = document.activeElement;
      if (command === 'copy' && input instanceof HTMLTextAreaElement && input.closest('[role="dialog"]')) {
        window.copied.push(input.value); return true;
      }
      return false;
    };
  });
  const url = `http://127.0.0.1:${server.address().port}`;
  for (const [lang, name, copy, done, failure] of [
    ['ru','Чат сообщества','Скопировать ссылку','Ссылка скопирована','Не удалось скопировать'],
    ['en','Community chat','Copy link','Link copied','Could not copy'],
  ]) {
    await page.goto(url);
    await page.evaluate(language => localStorage.setItem('lang', JSON.stringify(language)), lang);
    await page.reload();
    const dialog = page.getByRole('dialog');
    const link = dialog.getByRole('link', {name, exact:true});
    await link.waitFor();
    assert.equal(await link.getAttribute('href'), chat);
    assert.equal(await link.getAttribute('target'), '_blank');
    assert.ok((await link.getAttribute('rel')).includes('noopener'));
    await dialog.getByRole('button', {name:copy, exact:true}).click();
    assert.equal((await page.evaluate(() => window.copied)).at(-1), chat, 'HTTP modal fallback copies the complete public chat URL');
    await dialog.getByRole('status').filter({hasText:done}).waitFor();
    await page.evaluate(() => { document.execCommand = () => false; });
    await dialog.getByRole('button', {name:copy, exact:true}).click();
    await dialog.getByRole('status').filter({hasText:failure}).waitFor();
    await page.setViewportSize({width:390,height:844});
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'No mobile page overflow');
    if (lang === 'ru' && process.env.NFQWS_UI_SCREENSHOT) await page.screenshot({path:process.env.NFQWS_UI_SCREENSHOT,fullPage:true});
    await page.goto(url+'/?state=failed');
    await page.getByRole('dialog').waitFor();
    assert.equal(await page.getByRole('dialog').getByRole('link',{name,exact:true}).count(), 0, 'Update success invitation is absent after failure');
  }
  console.log('PASS community chat RU/EN: successful-update link only, HTTP modal clipboard, denied-copy feedback, safe external link and mobile layout');
} finally {
  await browser?.close();
  if (server) await new Promise(resolve => server.close(resolve));
}

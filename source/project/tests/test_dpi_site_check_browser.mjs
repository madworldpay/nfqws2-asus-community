import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from '../webui/web/node_modules/esbuild/lib/main.js';
const { chromium } = await import(process.env.NFQWS_PLAYWRIGHT_MODULE || 'playwright');
const web = fileURLToPath(new URL('../webui/web/', import.meta.url));
const dir = await mkdtemp(join(tmpdir(), 'dpi-service-browser-'));
let browser, server;
try {
  await build({ stdin: { resolveDir: web, loader: 'tsx', contents: `
    import React,{StrictMode,useState}from'react';import{createRoot}from'react-dom/client';
    import{DpiTerminalDialog}from'./src/components/DpiTerminalDialog';import{Layout}from'./src/components/Layout';
    const Fixture=()=>{const[open,setOpen]=useState(true);return <Layout><button onClick={()=>setOpen(true)}>Open Detector</button>{open&&<DpiTerminalDialog csrfToken="fixture-csrf" onClose={()=>setOpen(false)}/>}</Layout>};
    createRoot(document.getElementById('root')).render(<StrictMode><Fixture/></StrictMode>);
  ` }, bundle: true, platform: 'browser', format: 'iife', outfile: join(dir, 'fixture.js'), jsx: 'automatic', tsconfig: join(web, 'tsconfig.app.json'), logLevel: 'silent', define: { 'process.env.NODE_ENV': JSON.stringify(process.env.NFQWS_TERMINAL_REACT_MODE || 'development') } });
  const js = await readFile(join(dir, 'fixture.js')), css = await readFile(join(dir, 'fixture.css'));
  server = createServer((req, res) => {
    res.setHeader('Content-Type', req.url === '/fixture.js' ? 'text/javascript' : req.url === '/fixture.css' ? 'text/css' : 'text/html');
    res.end(req.url === '/fixture.js' ? js : req.url === '/fixture.css' ? css : '<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/fixture.css"></head><body><div id="root"></div><script src="/fixture.js"></script></body></html>');
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  browser = await chromium.launch({ headless: true, ...(process.env.NFQWS_CHROMIUM_EXECUTABLE ? { executablePath: process.env.NFQWS_CHROMIUM_EXECUTABLE } : {}) });
  for (const lang of ['ru', 'en']) for (const viewport of [{ width: 1366, height: 768 }, { width: 390, height: 844 }]) {
    const pack = JSON.parse(await readFile(join(web, `src/translations/${lang}.json`), 'utf8'));
    const t = key => key.split('.').reduce((v, k) => v[k], pack);
    const page = await browser.newPage({ viewport, acceptDownloads: true });
    page.setDefaultTimeout(6000);
    const errors = [], consoleErrors = [], calls = [], targets = [], reports = [];
    let owner = null, issued = 0, offset = 0, inFlight = 0, maxInFlight = 0, busyOnce = true, hold = false, release;
    const terminal = (state = 'running', data = '') => ({ terminal_id: owner || 'a'.repeat(32), state, offset: (offset += Buffer.byteLength(data)), data: Buffer.from(data).toString('base64'), exit_code: state === 'running' ? null : 0 });
    const urls = { 'facebook-main':'https://www.facebook.com/', 'facebook-mobile':'https://m.facebook.com/', 'facebook-cdn':'https://static.xx.fbcdn.net/', 'youtube-main':'https://www.youtube.com/', 'youtube-images':'https://i.ytimg.com/', 'youtube-static':'https://www.gstatic.com/', 'discord-main':'https://discord.com/', 'discord-cdn':'https://cdn.discordapp.com/', 'discord-gateway':'https://gateway.discord.gg/' };
    page.on('pageerror', e => errors.push(e.message));
    page.on('console', m => { if (m.type() === 'error' && !m.text().includes('409 (Conflict)')) consoleErrors.push(m.text()); });
    await page.addInitScript(lang => localStorage.setItem('lang', JSON.stringify(lang)), lang);
    await page.route('**/index.php', async route => {
      const post = new URLSearchParams(route.request().postData()), cmd = post.get('cmd');
      calls.push(cmd);
      let body, status = 200;
      if (cmd === 'dpiterminalinfo') body = { available:true, installed:true, code:null };
      else if (cmd === 'sharesavedrefresh') body = { code:'ok', reports:[], skipped:0, scan_truncated:false };
      else if (cmd === 'dpiterminalstart') { assert.equal(owner, null, 'new terminal must not overlap its old owner'); owner = (++issued).toString(16).repeat(32); offset = 0; body = terminal('running','Native Detector menu\r\nDNS: OK\r\nTLS: OK\r\n'); }
      else if (cmd === 'dpiterminalpoll') { await new Promise(r => setTimeout(r, 15)); body = terminal(); }
      else if (cmd === 'dpiterminalresize') body = terminal();
      else if (cmd === 'dpiterminalstop') { const id = post.get('terminal_id'); body = { ...terminal('stopped'), terminal_id:id }; owner = null; }
      else if (cmd === 'dpisitecheck') {
        assert.deepEqual([...post.keys()].sort(), ['cmd','csrf_token','dns_scope','target']);
        assert.equal(post.get('csrf_token'), 'fixture-csrf');
        assert.equal(await page.locator('.xterm').count(), 0, 'control request must unmount native terminal first');
        if (busyOnce) { busyOnce = false; status = 409; body = {error:'terminal_busy'}; }
        else {
          const target = post.get('target'); targets.push(target); inFlight++; maxInFlight = Math.max(maxInFlight, inFlight);
          if (hold) await new Promise(resolve => { release = resolve; });
          else await new Promise(r => setTimeout(r, 100));
          const before = { nfqws:'running', mode:'auto', config_sha256:'a'.repeat(64) };
          const after = target.endsWith('mobile') ? {nfqws:'stopped',mode:'all',config_sha256:'b'.repeat(64)} : before;
          const unknown = target.endsWith('cdn');
          body = {type:'nfqws2_dpi_site_check',schema_version:1,target,url:urls[target],started_at:1793952000,finished_at:1793952001,context:{before:unknown?{nfqws:'unknown',mode:'unknown',config_sha256:null}:before,after,changed:unknown?null:target.endsWith('mobile')},response:{outcome:'response',http_status:target.endsWith('main')?400:target.endsWith('cdn')?403:302,bytes_read:125,body_limited:false,redirect:target.endsWith('mobile')?'https://www.facebook.com/login/':null,elapsed_ms:451,error_code:null},full_service_verified:false,dns_scope:post.get('dns_scope')};
          if (target === 'facebook-main') body.finished_at = body.started_at - 30;
          if (target === 'youtube-main') body.response = {...body.response,outcome:'timeout',http_status:null,bytes_read:0,error_code:'deadline'};
          if (target === 'youtube-images') body.response = {...body.response,outcome:'tls_error',http_status:null,bytes_read:0,error_code:'tls_failed'};
          if (target === 'youtube-static') body.response = {...body.response,outcome:'read_limited',http_status:200,bytes_read:262144,body_limited:true,error_code:'body_limit'};
          if (target === 'discord-gateway') body.response = {...body.response,outcome:'connection_error',http_status:null,bytes_read:0,error_code:'connection_failed'};
          reports.push(body); inFlight--;
        }
      } else throw Error('Unexpected mutation: '+cmd);
      await route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
    });
    await page.goto(`http://127.0.0.1:${server.address().port}/`);
    await page.waitForFunction(() => document.querySelector('.xterm-rows')?.textContent.includes('Native Detector menu'));
    assert.equal(await page.locator('.xterm').count(), 1);
    assert.ok(await page.getByText(t('dpi_terminal.result_scope'), {exact:true}).isVisible());
    assert.ok(await page.getByText(t('dpi_terminal.native_context'), {exact:true}).count());
    const tab = () => page.getByRole('tab', {name:t('dpi_site_check.title'),exact:true});
    await tab().click();
    await page.waitForFunction(() => !document.querySelector('.xterm'));
    assert.equal(calls.filter(x => x === 'dpiterminalstop').length, 1);
    assert.equal(await page.getByRole('button',{name:t('dpi_site_check.dns_button_local_resolver'),exact:true}).getAttribute('aria-pressed'), 'true');
    const run = () => page.getByRole('button', {name:t('dpi_site_check.run'),exact:true});
    assert.ok(await run().evaluate(button => button.getBoundingClientRect().bottom <= document.querySelector('.MuiDialogActions-root').getBoundingClientRect().top), 'service run button should fit the initial mobile view without duplicated native descriptions');
    await run().click();
    await page.getByText(t('dpi_site_check.busy'), {exact:true}).waitFor();
    assert.equal(targets.length, 0, 'busy request does not advance to the next target');
    await run().evaluate(button => {button.click();button.click();button.click();});
    await page.locator('[data-dpi-site-result]').nth(2).waitFor();
    await run().waitFor({state:'visible'});
    assert.deepEqual(targets, ['facebook-main','facebook-mobile','facebook-cdn']);
    assert.equal(maxInFlight, 1, 'one service check sends strictly sequential requests');
    const first = page.locator('[data-dpi-site-result="facebook-main"]');
    assert.ok((await first.innerText()).includes('HTTP 400'));
    assert.ok((await first.innerText()).includes(t('dpi_site_check.http_error')));
    assert.ok((await first.innerText()).includes(t('dpi_site_check.clock_changed')), 'clock rollback retains the result with an explicit warning');
    assert.equal(await first.locator('.MuiAlert-standardSuccess').count(), 0, 'HTTP 400 must never be green');
    assert.ok((await page.locator('[data-dpi-site-result="facebook-cdn"]').innerText()).includes('HTTP 403'));
    assert.ok((await page.locator('[data-dpi-site-result="facebook-mobile"]').innerText()).includes(t('dpi_site_check.changed')));
    assert.ok((await page.locator('[data-dpi-site-result="facebook-cdn"]').innerText()).includes(t('dpi_site_check.unknown')));
    assert.ok(await page.getByText(t('dpi_site_check.incomplete'),{exact:true}).isVisible());
    const dl = await Promise.all([page.waitForEvent('download'),page.getByRole('button',{name:t('dpi_site_check.download'),exact:true}).click()]);
    const txt = await readFile(await dl[0].path(), 'utf8');
    for (const report of reports) assert.ok(txt.includes(JSON.stringify(report,null,2)));
    assert.ok(txt.includes(t('dpi_site_check.http_error')));
    assert.ok(txt.includes('full_service_verified=false'));
    assert.ok(txt.includes(t('dpi_site_check.clock_changed')));
    assert.ok(!txt.includes('__MISSING__'));
    if (process.env.NFQWS_DPI_SCREENSHOT_DIR) {
      await page.locator('.MuiDialogContent-root').evaluate(node => { node.scrollTop = 0; });
      await page.screenshot({path:join(process.env.NFQWS_DPI_SCREENSHOT_DIR,`dpi-site-${lang}-${viewport.width}-top.png`)});
    }
    const scroll = await page.locator('.MuiDialogContent-root').evaluate(node => {node.scrollTop = node.scrollHeight;return {top:node.scrollTop,overflow:node.scrollWidth-node.clientWidth};});
    assert.ok(scroll.top > 0, 'long results remain vertically scrollable');
    assert.ok(scroll.overflow < 3, 'service view fits narrow mobile width');
    if (process.env.NFQWS_DPI_SCREENSHOT_DIR) await page.screenshot({path:join(process.env.NFQWS_DPI_SCREENSHOT_DIR,`dpi-site-${lang}-${viewport.width}.png`)});
    for (const [service, expected] of [['youtube',['youtube-main','youtube-images','youtube-static']], ['discord',['discord-main','discord-cdn','discord-gateway']]]) {
      await page.getByRole('button',{name:t(`dpi_site_check.service_${service}`),exact:true}).click();
      assert.equal(await page.locator('[data-dpi-site-result]').count(),0,'service selection clears the former service observations');
      await run().click();
      await page.locator(`[data-dpi-site-result="${expected[2]}"]`).waitFor();
      await run().waitFor({state:'visible'});
      assert.deepEqual(targets.slice(-3),expected,'selected service owns its three fixed target IDs');
      const keys = service === 'youtube' ? ['outcome_timeout','outcome_tls_error','read_limited'] : ['http_error','endpoint_response','outcome_connection_error'];
      for (let i=0;i<3;i++) assert.ok((await page.locator(`[data-dpi-site-result="${expected[i]}"]`).innerText()).includes(t(`dpi_site_check.${keys[i]}`)));
    }
    await page.getByRole('tab',{name:t('dpi_site_check.native_view'),exact:true}).click();
    await page.waitForFunction(() => document.querySelector('.xterm-rows')?.textContent.includes('Native Detector menu'));
    assert.equal(await page.locator('.xterm').count(), 1);
    assert.equal(calls.filter(x=>x==='dpiterminalstart').length, 2);
    await tab().click();
    hold = true;
    await run().click();
    await page.waitForFunction(() => document.querySelector('[aria-busy="true"]'));
    for (let n=0; !release && n<30; n++) await page.waitForTimeout(10);
    assert.ok(release);
    const countBeforeClose = targets.length;
    await page.getByRole('button',{name:t('common.close'),exact:true}).last().click();
    release(); hold = false;
    await page.waitForTimeout(250);
    assert.equal(targets.length, countBeforeClose, 'closing cancels the remaining sequential targets');
    await page.getByRole('button',{name:'Open Detector',exact:true}).click();
    await page.waitForFunction(() => document.querySelector('.xterm-rows')?.textContent.includes('Native Detector menu'));
    assert.equal(await page.locator('.xterm').count(), 1);
    assert.equal(calls.filter(x=>x==='dpiterminalstart').length, 3);
    assert.equal(targets.length, countBeforeClose, 'reopening does not restart service requests');
    await page.getByRole('button',{name:t('common.close'),exact:true}).last().click();
    assert.deepEqual(errors, []);
    assert.deepEqual(consoleErrors, []);
    console.log(`PASS React DPI services ${lang} ${viewport.width}: HTTP400/CDN403, serial/no duplicate requests, context/TXT, terminal cleanup, reopen and mobile scroll`);
    await page.close();
  }
} finally {
  await browser?.close();
  if (server) await new Promise(resolve => server.close(resolve));
  await rm(dir,{recursive:true,force:true});
}

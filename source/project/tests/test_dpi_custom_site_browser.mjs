import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { mkdtemp, readFile, mkdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from '../webui/web/node_modules/esbuild/lib/main.js';
const { chromium } = await import(process.env.NFQWS_PLAYWRIGHT_MODULE || 'playwright');
const web = fileURLToPath(new URL('../webui/web/', import.meta.url));
const dir = await mkdtemp(join(tmpdir(), 'dpi-custom-browser-'));
const output = process.env.NFQWS_CUSTOM_SITE_OUTPUT;
assert.ok(output);
await mkdir(output, {recursive:true});
const tenOnly=process.env.NFQWS_CUSTOM_TEN_ONLY==='1';
let browser, server;
try {
 await build({stdin:{resolveDir:web,loader:'tsx',contents:`import React,{StrictMode,useState}from'react';import{createRoot}from'react-dom/client';import{DpiTerminalDialog}from'./src/components/DpiTerminalDialog';import{Layout}from'./src/components/Layout';const Fixture=()=>{const[open,setOpen]=useState(true);return <Layout>{open&&<DpiTerminalDialog csrfToken="fixture-csrf" ${tenOnly?'initialSiteTargets={Array.from({length:10},(_,i)=>`host${i}.example.com`)}':''} onClose={()=>setOpen(false)}/>}</Layout>};createRoot(document.getElementById('root')).render(<StrictMode><Fixture/></StrictMode>);`},bundle:true,platform:'browser',format:'iife',outfile:join(dir,'fixture.js'),jsx:'automatic',tsconfig:join(web,'tsconfig.app.json'),logLevel:'silent',define:{'process.env.NODE_ENV':'"development"'}});
 const js=await readFile(join(dir,'fixture.js')),css=await readFile(join(dir,'fixture.css')).catch(()=>Buffer.alloc(0));
 server=createServer((req,res)=>{res.setHeader('Content-Type',req.url==='/fixture.js'?'text/javascript':req.url==='/fixture.css'?'text/css':'text/html');res.end(req.url==='/fixture.js'?js:req.url==='/fixture.css'?css:'<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/fixture.css"></head><body><div id="root"></div><script src="/fixture.js"></script></body></html>');});
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 browser=await chromium.launch({headless:true,executablePath:process.env.NFQWS_CHROMIUM_EXECUTABLE});
 for(const lang of ['ru','en'])for(const width of [1366,390]){
  if(process.env.NFQWS_CUSTOM_SITE_VARIANT && process.env.NFQWS_CUSTOM_SITE_VARIANT !== `${lang}-${width}`)continue;
  const pack=JSON.parse(await readFile(join(web,`src/translations/${lang}.json`),'utf8'));const t=k=>k.split('.').reduce((v,n)=>v[n],pack);
  const page=await browser.newPage({viewport:{width,height:900},acceptDownloads:true});page.setDefaultTimeout(6000);const errors=[],calls=[];let inFlight=0,maxInFlight=0;let terminalStops=0;const terminal={terminal_id:'a'.repeat(32),state:'running',offset:0,data:'',exit_code:null};
  page.on('pageerror',e=>errors.push(e.message));await page.addInitScript(lang=>localStorage.setItem('lang',JSON.stringify(lang)),lang);
  await page.route('**/index.php',async route=>{
   const post=new URLSearchParams(route.request().postData());const cmd=post.get('cmd');
   if(cmd!=='dpisitecheck'){
    let body;
    if(cmd==='dpiterminalinfo')body={available:true,installed:true,code:null};
    else if(cmd==='sharesavedrefresh')body={code:'ok',reports:[],skipped:0,scan_truncated:false};
    else if(cmd==='dpiterminalstart')body={...terminal,offset:22,data:Buffer.from('Native Detector menu\r\n').toString('base64')};
    else if(cmd==='dpiterminalpoll'||cmd==='dpiterminalresize')body={...terminal,offset:22};
    else if(cmd==='dpiterminalstop'){terminalStops++;body={...terminal,offset:22,state:'stopped',exit_code:0};}
    else throw Error('Unexpected mutation: '+cmd);
    await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});return;
   }
   assert.equal(await page.locator('.xterm').count(),0);assert.equal(post.get('csrf_token'),'fixture-csrf');assert.equal(post.get('dns_scope'),'local_resolver');const target=post.get('target');calls.push(target);assert.ok(target.startsWith('custom-'));const operation=target.startsWith('custom-route:')?'route':'https';const host=target.slice(target.indexOf(':')+1);inFlight++;maxInFlight=Math.max(maxInFlight,inFlight);await new Promise(resolve=>setTimeout(resolve,15));
   const context={nfqws:'running',mode:'auto',config_sha256:'a'.repeat(64)};const piece={state:'partial',output:'1  192.0.2.1  2 ms\n2  *'};
   const body={type:'nfqws2_dpi_site_check',schema_version:2,target,url:`https://${host}/`,host,kind:'domain',operation,addresses:['93.184.216.34'],dns:{rcode:0,answers:['93.184.216.34'],reason:'ready'},network:operation==='route'?{ping:{state:'done',output:'3 packets transmitted, 3 received'},route:{state:'done',output:'93.184.216.34 via 192.0.2.1 dev ppp0'},trace:piece}:null,started_at:1,finished_at:2,context:{before:context,after:context,changed:false},response:{outcome:operation==='route'?'unavailable':'response',http_status:operation==='route'?null:403,bytes_read:0,body_limited:false,redirect:null,elapsed_ms:123,error_code:operation==='route'?'not_requested':null},full_service_verified:false,dns_scope:'local_resolver'};
   inFlight--;await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});
  });

  if(tenOnly){
   await page.goto(`http://127.0.0.1:${server.address().port}/`);
   await page.getByRole('dialog').waitFor();
   const field=page.getByRole('textbox',{name:t('dpi_site_check.custom_target'),exact:true});
   assert.equal(await field.count(),1,'picker prefill must open the existing custom availability view');
   assert.equal((await field.inputValue()).split('\n').length,10);
   assert.deepEqual(calls,[],'prefill must not silently start probes');
   await page.getByRole('button',{name:t('dpi_site_check.run_custom'),exact:true}).click();
   await page.locator('[data-dpi-site-result="custom-route:host9.example.com"]').waitFor();
   assert.deepEqual(calls,Array.from({length:10},(_,i)=>[`custom-https:host${i}.example.com`,`custom-route:host${i}.example.com`]).flat());
   assert.equal(maxInFlight,1);assert.equal(terminalStops,0,'no native terminal should start for a custom prefill');
   const dl=await Promise.all([page.waitForEvent('download'),page.getByRole('button',{name:t('dpi_site_check.download'),exact:true}).click()]);
   await dl[0].saveAs(join(output,`${lang}-${width}-ten.txt`));
   const text=await readFile(join(output,`${lang}-${width}-ten.txt`),'utf8');
   for(let i=0;i<10;i++)assert.ok(text.includes(`host${i}.example.com`));
   assert.deepEqual(errors,[]);await field.scrollIntoViewIfNeeded();await page.screenshot({path:join(output,`${lang}-${width}-ten.png`),animations:'disabled'});
   console.log(`PASS custom TEN prefill ${lang} ${width}:20serial probes/no auto-run/TXT`);await page.close();continue;
  }
  await page.goto(`http://127.0.0.1:${server.address().port}/`);await page.getByRole('tab',{name:t('dpi_site_check.title'),exact:true}).click();await page.waitForFunction(()=>!document.querySelector('.xterm'));const customLabel=t('dpi_site_check.service_custom');
  await page.getByRole('button',{name:'Facebook',exact:true}).waitFor();assert.equal(await page.getByRole('button',{name:customLabel,exact:true}).count(),1,'Owner445 needs an actual custom-address selector');await page.getByRole('button',{name:customLabel,exact:true}).click();
  const field=page.getByRole('textbox',{name:t('dpi_site_check.custom_target'),exact:true});await field.fill('www.facebook.com');await page.waitForTimeout(250);/* Wait for the existing MUI label/selection transitions before visual capture. */await page.screenshot({path:join(output,`${lang}-${width}-form.png`),animations:'disabled'});await page.getByRole('button',{name:t('dpi_site_check.run_custom'),exact:true}).click();
  await page.locator('[data-dpi-site-result="custom-route:www.facebook.com"]').waitFor();assert.deepEqual(calls,['custom-https:www.facebook.com','custom-route:www.facebook.com']);assert.ok(await page.getByText('93.184.216.34 via 192.0.2.1 dev ppp0',{exact:true}).isVisible());assert.ok(await page.getByText(t('dpi_site_check.network_hint'),{exact:true}).isVisible());assert.equal(await page.getByRole('table',{name:t('dpi_site_check.hops'),exact:true}).getByRole('row').count(),3);assert.ok(await page.getByText(t('dpi_site_check.diagnosis_http_403'),{exact:true}).isVisible());assert.ok(await page.getByRole('table',{name:t('dpi_site_check.hops'),exact:true}).getByText(t('dpi_site_check.hop_no_reply'),{exact:true}).isVisible());
  const previewLabel=lang==='ru'?'Предпросмотр отчёта':'Report preview';await page.getByRole('button',{name:previewLabel,exact:true}).click();const preview=page.getByRole('dialog',{name:previewLabel,exact:true});await preview.waitFor();const previewText=await preview.locator('[data-dpi-site-preview]').textContent();assert.ok(previewText.includes('3 packets transmitted, 3 received'));assert.ok(previewText.includes('93.184.216.34'));assert.ok(previewText.includes('full_service_verified=false'));assert.ok(previewText.includes(t('dpi_site_check.custom_scope')));await page.screenshot({path:join(output,`${lang}-${width}-preview.png`),animations:'disabled'});await preview.getByRole('button',{name:lang==='ru'?'Закрыть':'Close',exact:true}).click();
  const dl=await Promise.all([page.waitForEvent('download'),page.getByRole('button',{name:t('dpi_site_check.download'),exact:true}).click()]);const file=join(output,`${lang}-${width}.txt`);await dl[0].saveAs(file);const text=await readFile(file,'utf8');assert.equal(text,previewText);assert.ok(text.includes('3 packets transmitted, 3 received'));assert.ok(text.includes('93.184.216.34'));
  await page.locator('[data-dpi-site-result="custom-route:www.facebook.com"]').scrollIntoViewIfNeeded();await page.screenshot({path:join(output,`${lang}-${width}.png`),fullPage:true});assert.ok(terminalStops>=1);assert.equal(await page.locator('[data-dpi-site-result="custom-route:www.facebook.com"]').getByText('not_requested',{exact:false}).count(),0);assert.deepEqual(errors,[]);console.log(`PASS custom target UI ${lang} ${width}: two serial probes, route output, TXT, no browser errors`);await page.close();
 }
}finally{await browser?.close();if(server)await new Promise(resolve=>server.close(resolve));}

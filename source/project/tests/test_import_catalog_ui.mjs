import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from '../webui/web/node_modules/esbuild/lib/main.js';
const { chromium } = await import(process.env.NFQWS_PLAYWRIGHT_MODULE || 'playwright');
const web=fileURLToPath(new URL('../webui/web/',import.meta.url));
const dir=await mkdtemp(join(tmpdir(),'catalog-ui-'));let browser,server;
try {
  await build({stdin:{resolveDir:web,loader:'tsx',contents:`
    import React from 'react';import {createRoot} from 'react-dom/client';
    import {ImportDialog} from './src/components/ImportDialog';
    import {TranslationContext} from './src/context/TranslationContext';
    import ru from './src/translations/ru.json';import en from './src/translations/en.json';
    const pack=new URLSearchParams(location.search).get('lang')==='en'?en:ru;
    const t=k=>k.split('.').reduce((v,p)=>v?.[p],pack)||k;
    createRoot(document.getElementById('root')).render(<TranslationContext.Provider value={{t}}><ImportDialog onClose={()=>{}}/></TranslationContext.Provider>);
  `},bundle:true,platform:'browser',format:'iife',outfile:join(dir,'fixture.js'),jsx:'automatic',logLevel:'silent',tsconfig:join(web,'tsconfig.app.json'),plugins:[{name:'status-boundary',setup(b){b.onLoad({filter:/hooks\/useStatus\.tsx$/},()=>({contents:'export const useStatus=()=>({csrfToken:"fixture-csrf"});',loader:'tsx'}));b.onLoad({filter:/components\/Editor\.tsx$/},()=>({contents:'import React from "react";export const Editor=({value})=><textarea readOnly value={value}/>;',loader:'tsx'}));}}]});
  const script=await readFile(join(dir,'fixture.js'));
  server=createServer((req,res)=>{res.setHeader('Content-Type',req.url==='/fixture.js'?'text/javascript':'text/html');res.end(req.url==='/fixture.js'?script:'<!doctype html><html><body><div id="root"></div><script src="/fixture.js"></script></body></html>');});
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  browser=await chromium.launch({headless:true,...(process.env.NFQWS_CHROMIUM_EXECUTABLE?{executablePath:process.env.NFQWS_CHROMIUM_EXECUTABLE}:{})});
  const page=await browser.newPage();page.setDefaultTimeout(4000);
  const base=`http://127.0.0.1:${server.address().port}`;
  const profile={id:'original',title:'Original name <script>',category:'global',provider:'',region:'',description:'Example preset',attribution:'Example author',updated_at:'2026-10-23T12:00:00Z',revision:1,min_build:68,size:2,sha256:'a'.repeat(64)};
  const document={values:{NFQWS_ARGS:'--filter-tcp=443'},ports:{},resources:[],dns_sources:[],dependencies:[],audit:null,context:{purpose:'Selected example',operator:'Example'},source:null,ignored:[],input_sha256:'b'.repeat(64)};
  const calls=[];let offline=false;
  await page.route('**/index.php',async route=>{
    const post=new URLSearchParams(route.request().postData());const cmd=post.get('cmd');calls.push(cmd);
    let body;
    if(cmd==='importstatus')body={state:'idle',id:null,can_undo:false};
    else if(cmd==='importcatalog')body=offline?{error:'catalog_unavailable'}:{schema_version:1,revision:1,build:68,profiles:[{...profile,id:'provider',title:'Provider preset',category:'provider',provider:'Example ISP',region:'Example region'},profile]};
    else if(cmd==='importcatalogload'){await new Promise(resolve=>setTimeout(resolve,100));body={document:'{}'};}
    else if(cmd==='importinspect')body=document;
    else throw new Error('Unexpected mutation or request: '+cmd);
    await route.fulfill({status:offline&&cmd==='importcatalog'?503:200,contentType:'application/json',body:JSON.stringify(body)});
  });
  await page.goto(base);assert.equal(calls.includes('importcatalog'),false,'Catalog is fetched only when requested');
  await page.getByRole('button',{name:'Из облака',exact:true}).click();
  await page.getByText('Глобальные стратегии',{exact:true}).waitFor();
  await page.getByText('Профили провайдеров',{exact:true}).waitFor();
  assert.equal(await page.locator('script').count(),1,'Preset title stays escaped text');
  const item=page.getByRole('button',{name:/Original name/});await item.dblclick();
  await page.getByText('Selected example',{exact:false}).first().waitFor();
  assert.equal(calls.filter(x=>x==='importcatalogload').length,1,'Rapid clicks load the preset only once');
  assert.equal(calls.filter(x=>x==='importinspect').length,1);
  assert.equal(await page.locator('input[type="checkbox"]:checked').count(),0,'Preset opens the existing unchecked selection');
  assert.equal(calls.includes('importprepare')||calls.includes('importapply'),false);
  offline=true;await page.goto(base);await page.getByRole('button',{name:'Из облака',exact:true}).click();
  await page.getByText(/Каталог сейчас недоступен/).waitFor();
  await page.locator('input[type=file]').setInputFiles({name:'Профиль Windows.json',mimeType:'',buffer:Buffer.from('{}')});
  await page.getByText('Selected example',{exact:false}).first().waitFor();
  assert.ok(calls.filter(x=>x==='importinspect').length===2,'Local file still enters the same import flow while catalog is unavailable');
  await page.goto(base+'/?lang=en');await page.getByRole('button',{name:'From cloud',exact:true}).waitFor();
  console.log('PASS actual import dialog: local/VPS sources, two categories, escaped names, unchecked selective import, no automatic apply, rapid-click guard and offline local fallback');
}finally{await browser?.close();if(server)await new Promise(resolve=>server.close(resolve));await rm(dir,{recursive:true,force:true});}

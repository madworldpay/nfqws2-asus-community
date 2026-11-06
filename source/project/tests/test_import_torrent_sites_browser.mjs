import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from '../webui/web/node_modules/esbuild/lib/main.js';
const { chromium } = await import(process.env.NFQWS_PLAYWRIGHT_MODULE || 'playwright');
const web = fileURLToPath(new URL('../webui/web/', import.meta.url));
const dir = await mkdtemp(join(tmpdir(), 'torrent-import-ui-'));
let browser, server;
try {
  await build({ stdin: { resolveDir: web, loader: 'tsx', contents: `
    import React from 'react';import{createRoot}from'react-dom/client';
    import{ImportDialog}from'./src/components/ImportDialog';
    import{TranslationContext}from'./src/context/TranslationContext';
    import ru from'./src/translations/ru.json';import en from'./src/translations/en.json';
    const lang=new URLSearchParams(location.search).get('lang')||'ru',p=lang==='en'?en:ru;
    const t=k=>k.split('.').reduce((v,x)=>v?.[x],p)||k;
    createRoot(document.getElementById('root')).render(<TranslationContext.Provider value={{t,langcode:lang}}><ImportDialog onClose={()=>{}}/></TranslationContext.Provider>);
  ` }, bundle: true, platform: 'browser', format: 'iife', outfile: join(dir,'fixture.js'), jsx:'automatic',
  tsconfig:join(web,'tsconfig.app.json'),logLevel:'silent',plugins:[{name:'external-boundaries',setup(b){
    b.onLoad({filter:/hooks\/useStatus\.tsx$/},()=>({contents:'export const useStatus=()=>({csrfToken:"fixture"});',loader:'tsx'}));
    b.onLoad({filter:/components\/Editor\.tsx$/},()=>({contents:'import React from"react";export const Editor=({value})=><textarea readOnly value={value}/>;',loader:'tsx'}));
  }}] });
  const script=await readFile(join(dir,'fixture.js'));
  server=createServer((req,res)=>{res.setHeader('Content-Type',req.url==='/fixture.js'?'text/javascript':'text/html');res.end(req.url==='/fixture.js'?script:'<!doctype html><html><body><div id="root"></div><script src="/fixture.js"></script></body></html>');});
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  browser=await chromium.launch({headless:true,...(process.env.NFQWS_CHROMIUM_EXECUTABLE?{executablePath:process.env.NFQWS_CHROMIUM_EXECUTABLE}:{})});
  for(const lang of ['ru','en'])for(const width of [1280,390]){
    const page=await browser.newPage({viewport:{width,height:900}});page.setDefaultTimeout(4000);
    const texts=JSON.parse(await readFile(join(web,'src/translations',lang+'.json'),'utf8'));
    const selections=[],documents=[],calls=[];
    const sites=['nnmclub.to','rutracker.org','rutor.info','tapochek.net'];
    const block='--comment=nfqws2-community-torrent-sites-v1 --filter-tcp=443 --hostlist-domains='+sites.join(',')+' --payload=tls_client_hello --lua-desync=fake:blob=tls_clienthello:tcp_md5 --lua-desync=multidisorder:pos=1,midsld';
    const doc={values:{NFQWS_ARGS:'--filter-tcp=80,443 --lua-desync=multisplit:pos=1'},ports:{},resources:[],dns_sources:[],context:{purpose:'Cloud fixture'},source:null,ignored:[],input_sha256:'b'.repeat(64)};
    const profiles=['provider','global'].map(category=>({id:category,title:category==='global'?'General fixture':'Provider fixture',category,provider:'',region:'',description:'Website import fixture',attribution:'',updated_at:'2026-11-05T00:00:00Z',revision:1,min_build:68,size:2,sha256:'a'.repeat(64)}));
    await page.route('**/index.php',async route=>{
      const post=new URLSearchParams(route.request().postData()),cmd=post.get('cmd');calls.push(cmd);let body;
      if(cmd==='importstatus')body={state:'idle',id:null,can_undo:false,config_saved:false,dns_draft_saved:false};
      else if(cmd==='importcatalog')body={schema_version:1,revision:1,build:88,profiles};
      else if(cmd==='importaddoncatalog')body={schema_version:1,revision:1,build:92,addons:[]};
      else if(cmd==='importcatalogload')body={document:'{}'};
      else if(cmd==='importinspect')body=doc;
      else if(cmd==='importprepare'){
        const selected=JSON.parse(post.get('selection'));selections.push(selected);documents.push(JSON.parse(post.get('documents')));
        body={ready:true,problems:[],warnings:[],required:{files:[],shared:[]},affected_blocks:[],config:'fixture',changes:[],files:[],draft:null,old_draft:null,digest:'c'.repeat(64),proof:'fixture-proof'};
        if(selected.torrent_sites)body.torrent_sites={sites,block,key:'NFQWS_ARGS_CUSTOM'};
      }else throw Error('Unexpected mutation: '+cmd);
      await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});
    });
    await page.goto(`http://127.0.0.1:${server.address().port}/?lang=${lang}`);
    await page.getByRole('button',{name:texts.import.catalog.choose,exact:true}).click();
    await page.getByRole('button',{name:/Provider fixture/}).click();
    await page.getByText('Cloud fixture',{exact:false}).first().waitFor();
    assert.equal(await page.getByRole('checkbox',{name:/torrent|торрент/i}).count(),0,'provider imports have no option');
    await page.getByRole('button',{name:/General fixture/}).click();
    const choice=page.getByRole('checkbox',{name:lang==='ru'?'Добавить обход для сайтов торрент-трекеров':'Add bypass for torrent tracker websites',exact:true});
    await choice.waitFor();assert.equal(await choice.isChecked(),false,'new global import starts off');
    await choice.check();await page.getByRole('button',{name:texts.import.preview,exact:true}).first().click();
    const apply=page.getByRole('button',{name:texts.import.apply,exact:true});await apply.waitFor();
    await page.getByText(block,{exact:true}).waitFor();assert.equal(await apply.isEnabled(),true);
    assert.deepEqual(selections.at(-1).torrent_sites,{catalog_id:'global',sha256:'a'.repeat(64)});
    assert.deepEqual(selections.at(-1).blocks,[{key:'NFQWS_ARGS',value:doc.values.NFQWS_ARGS}]);
    assert.deepEqual(documents.at(-1),['{}'],'raw cloud document remains unchanged');
    await choice.uncheck();assert.equal(await apply.isDisabled(),true,'toggle invalidates old preview/proof');
    assert.equal(await page.getByText(block,{exact:true}).count(),0);
    await page.getByRole('button',{name:texts.import.preview,exact:true}).first().click();
    await page.waitForFunction(()=>!document.querySelector('[role="progressbar"]'));
    assert.equal(Object.hasOwn(selections.at(-1),'torrent_sites'),false,'off omits the optional selection');
    assert.deepEqual(documents.at(-1),['{}']);assert.equal(calls.includes('importapply'),false);
    await page.getByRole('button',{name:/Provider fixture/}).click();
    await page.getByText('Cloud fixture',{exact:false}).first().waitFor();
    assert.equal(await page.getByRole('checkbox',{name:/torrent|торрент/i}).count(),0,'new source clears the option');
    await page.close();
  }
  console.log('PASS tracker website option RU/EN desktop/mobile: off by default, global-only, visible rule, unchanged document and stale-preview invalidation');
}finally{await browser?.close();if(server)await new Promise(resolve=>server.close(resolve));await rm(dir,{recursive:true,force:true});}

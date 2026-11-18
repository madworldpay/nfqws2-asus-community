import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { build } from '../webui/web/node_modules/esbuild/lib/main.js';
const { chromium } = await import(process.env.NFQWS_PLAYWRIGHT_MODULE || 'playwright');
const web = fileURLToPath(new URL('../webui/web/', import.meta.url));
const dir = await mkdtemp(join(tmpdir(), 'portable-assets-browser-'));
let browser, server;
try {
  await build({ stdin: { resolveDir: web, loader: 'tsx', contents: `
    import React from 'react';import{createRoot}from'react-dom/client';
    import{ImportDialog}from'./src/components/ImportDialog';
    import{TranslationContext}from'./src/context/TranslationContext';
    import{useAppStore}from'./src/store/useAppStore';
    import ru from'./src/translations/ru.json';import en from'./src/translations/en.json';
    const q=new URLSearchParams(location.search),lang=q.get('lang')||'ru',p=lang==='en'?en:ru;
    const t=k=>k.split('.').reduce((v,x)=>v?.[x],p)||k;
    useAppStore.setState({auth:true,needSave:q.has('unsaved')});
    createRoot(document.getElementById('root')).render(<TranslationContext.Provider value={{t,langcode:lang}}><ImportDialog onClose={()=>{window.closedDialog=true}}/></TranslationContext.Provider>);
  ` }, bundle: true, platform: 'browser', format: 'iife', outfile: join(dir, 'fixture.js'), jsx: 'automatic',
  tsconfig: join(web, 'tsconfig.app.json'), logLevel: 'silent', plugins: [{ name: 'owned-http-boundaries', setup(b) {
    b.onLoad({ filter: /hooks\/useStatus\.tsx$/ }, () => ({ contents: 'export const useStatus=()=>({csrfToken:"fixture",isReady:true,nfqws2:true,authenticated:false,anonym:!location.search.includes("noauth"),service:!location.search.includes("stopped")});', loader: 'tsx' }));
    b.onLoad({ filter: /components\/Editor\.tsx$/ }, () => ({ contents: 'import React from"react";export const Editor=({value})=><textarea readOnly value={value}/>;', loader: 'tsx' }));
  } }] });
  const script=await readFile(join(dir,'fixture.js'));
  server=createServer((req,res)=>{res.setHeader('Content-Type',req.url==='/fixture.js'?'text/javascript':'text/html');res.end(req.url==='/fixture.js'?script:'<!doctype html><html><meta name="viewport" content="width=device-width, initial-scale=1"><body><div id="root"></div><script src="/fixture.js"></script></body></html>');});
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  browser=await chromium.launch({headless:true,...(process.env.NFQWS_CHROMIUM_EXECUTABLE?{executablePath:process.env.NFQWS_CHROMIUM_EXECUTABLE}:{})});
  const raw=Buffer.from('function portable() return 1 end\n'),sha=createHash('sha256').update(raw).digest('hex');
  const doc={values:{NFQWS_ARGS:'--filter-tcp=443',NFQWS_BASE_ARGS:'--lua-init=RESOURCE_1 --lua-init=RESOURCE_2'},ports:{},resources:[{id:'a'.repeat(32),kind:'lua',name:'portable.lua',encoding:'utf8',data_base64:raw.toString('base64'),byte_length:raw.length,sha256:sha,source_sha256:sha,aliases:['RESOURCE_1']}],package_files:[{id:'b'.repeat(32),kind:'lua',name:'official.lua',byte_length:12,sha256:'c'.repeat(64),aliases:['RESOURCE_2']}],dns_sources:[],context:null,source:null,ignored:[],input_sha256:'d'.repeat(64)};
  const run=async({lang='ru',width=390,actionResult={status:0,output:[]},configSaved=true,query='',bareLua=false,lostReply=false,undoReply=null}={})=>{
    const page=await browser.newPage({viewport:{width,height:900}});page.setDefaultTimeout(3000);
    const tr=JSON.parse(await readFile(join(web,'src/translations',lang+'.json'),'utf8'));
    const selections=[],calls=[];let committed=false,undone=false,releaseAction,requestId='e'.repeat(32);
    await page.route('**/index.php',async route=>{
      const rawPost=route.request().postData()||'',post=rawPost.startsWith('{')?new URLSearchParams(JSON.parse(rawPost)):new URLSearchParams(rawPost),cmd=post.get('cmd')||/name="cmd"\r\n\r\n([^\r\n]+)/.exec(rawPost)?.[1];calls.push(cmd);let body;
      if(cmd==='importstatus'&&undoReply==='restore_required'&&undone===false&&calls.includes('importundo'))body={state:'restore_required',id:requestId,can_undo:false,config_saved:false,dns_draft_saved:false};
      else if(cmd==='importstatus')body={state:undone?'undone':committed?'committed':'idle',id:committed?requestId:null,can_undo:committed&&!undone,undo_proof:committed&&!undone?'fixture':undefined,config_saved:committed&&!undone&&configSaved,dns_draft_saved:committed&&!undone&&!configSaved};
      else if(cmd==='importinspect')body=bareLua?{...doc,resources:[],package_files:[],values:{NFQWS_ARGS:'--filter-tcp=443 --lua-init=@/opt/etc/nfqws2/lua/local.lua'}}:doc;
      else if(cmd==='importaddoncatalog')body={schema_version:1,revision:1,build:100,addons:[]};
      else if(cmd==='importprepare'){
        const s=JSON.parse(post.get('selection'));selections.push(s);
        body={ready:!!s.trusted_lua,problems:s.trusted_lua?[]:[{code:'lua_trust'}],warnings:[],required:{files:[],shared:[]},affected_blocks:[],changes:[{key:'NFQWS_ARGS',before:'old',after:'new'}],config:'fixture',files:[],draft:null,old_draft:null,digest:'f'.repeat(64),proof:s.trusted_lua?'fixture':null};
      } else if(cmd==='importapply'){committed=true;requestId=post.get('request_id');if(lostReply){await route.abort();return;}body={state:'committed',id:requestId,can_undo:true,config_saved:configSaved,dns_draft_saved:!configSaved};}
      else if(cmd==='importundo'){undone=undoReply!=='restore_required';if(undoReply==='lost'||undoReply==='restore_required'){await route.abort();return;}body={state:'undone',id:requestId,can_undo:false,config_saved:false,dns_draft_saved:false};}
      else if(cmd==='restart'||cmd==='start')body=await new Promise(resolve=>{releaseAction=()=>resolve(actionResult);});
      else throw Error('Unexpected mutation: '+cmd);
      await route.fulfill({contentType:'application/json',body:JSON.stringify(body)});
    });
    await page.goto(`http://127.0.0.1:${server.address().port}/?lang=${lang}${query}`);
    await page.locator('input[type=file]').setInputFiles({name:'strategy.json',mimeType:'application/json',buffer:Buffer.from('{}')});
    await page.getByRole('button',{name:tr.import.preview,exact:true}).first().click();
    await page.getByText(tr.import.problems.lua_trust,{exact:true}).waitFor();
    assert.deepEqual(selections[0].files,bareLua?[]:[{id:'a'.repeat(32)}],'required Lua is selected as data, trust is separate');
    assert.equal(selections[0].trusted_lua,false);
    if(!bareLua)await page.getByRole('alert').filter({hasText:'official.lua'}).waitFor();
    await page.getByRole('checkbox',{name:tr.import.trust_lua,exact:true}).check();
    await page.getByRole('button',{name:tr.import.preview,exact:true}).first().click();
    await page.getByRole('button',{name:tr.import.apply,exact:true}).click();
    if(lostReply){await page.getByText(tr.import.uncertain,{exact:true}).waitFor();await page.getByRole('button',{name:tr.import.check_status,exact:true}).click();}
    await page.getByText(tr.import.saved,{exact:true}).waitFor();
    assert.equal(calls.filter(c=>['restart','start'].includes(c)).length,0,'save never restarts automatically');
    const command=query.includes('stopped')?'start':'restart';
    const label=tr.import[command==='start'?'start_service':'restart_service'];
    if(!configSaved){assert.equal(await page.getByRole('button',{name:label,exact:true}).count(),0);await page.close();return;}
    const button=page.getByRole('button',{name:label,exact:true});await button.waitFor();
    if(undoReply){
      await page.getByRole('button',{name:tr.import.undo,exact:true}).click();
      if(undoReply==='lost'||undoReply==='restore_required'){
        await page.getByText(tr.import.uncertain_undo,{exact:true}).waitFor();assert.equal(await button.count(),0,'unknown undo must close service controls');
        await page.getByRole('button',{name:tr.import.check_status,exact:true}).click();
      }
      if(undoReply==='restore_required'){await page.getByText(tr.import.restore_required,{exact:true}).waitFor();assert.equal(await button.count(),0);await page.close();return;}
      await page.getByText(tr.import.undone,{exact:true}).waitFor();await button.waitFor();
    }
    if(query.includes('noauth')){assert.equal(await button.isDisabled(),true);await page.close();return;}
    await button.click();await page.waitForFunction(()=>!!document.querySelector('button[disabled]'));
    await button.evaluate(el=>{el.click();el.click();});
    assert.equal(calls.filter(c=>c===command).length,1,'duplicate restart is fenced');
    releaseAction();
    const failed=actionResult.status!==0;
    await page.getByText(tr.import[failed?'service_failed':'service_done'],{exact:true}).waitFor();
    assert.equal(await page.getByRole('dialog').count(),1,'service action stays inside import window');
    assert.equal(await page.evaluate(()=>window.closedDialog===true),false);
    await page.close();
  };
  for(const lang of ['ru','en'])for(const width of [390,1280])await run({lang,width});
  await run({actionResult:{status:1,output:['failed']}});
  await run({actionResult:{}});
  await run({configSaved:false});
  await run({query:'&noauth=1'});
  await run({query:'&stopped=1'});
  await run({bareLua:true});
  await run({lostReply:true});
  await run({undoReply:'lost'});
  await run({undoReply:'restore_required'});
  await run({undoReply:'ok'});
  console.log('PASS portable import RU/EN mobile/desktop, Lua consent, stock preview, explicit local start/restart, duplicate/error/auth/DNS boundaries');
} finally {await browser?.close();if(server)await new Promise(resolve=>server.close(resolve));await rm(dir,{recursive:true,force:true});}

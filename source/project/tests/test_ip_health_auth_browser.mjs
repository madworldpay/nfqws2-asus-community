import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {build} from '../webui/web/node_modules/esbuild/lib/main.js';
const {chromium}=await import(process.env.NFQWS_PLAYWRIGHT_MODULE||'playwright');
const web=fileURLToPath(new URL('../webui/web/',import.meta.url));
const fixtures=new Map(),failures=[];
let server,browser;
try{
 const js=(await build({stdin:{resolveDir:web,loader:'tsx',contents:`
 import React,{useState}from'react';import{createRoot}from'react-dom/client';import{QueryClientProvider}from'@tanstack/react-query';
 import{queryClient,API}from'./src/api/client';import{IpHealthPanel}from'./src/components/IpHealthPanel';import{LoginDialog}from'./src/components/LoginDialog';import{useAppStore}from'./src/store/useAppStore';
 import{TranslationContext}from'./src/context/TranslationContext';import ru from'./src/translations/ru.json';import en from'./src/translations/en.json';
 const pack=location.search.includes('en')?en:ru;const t=(key,params={})=>(key.split('.').reduce((v,k)=>v?.[k],pack)||key).replace(/{{(\\w+)}}/g,(_,k)=>String(params[k]??''));
 function App(){API.status();const auth=useAppStore(s=>s.auth);const[show,setShow]=useState(true);window.fixture={hide:()=>setShow(false)};return <TranslationContext.Provider value={{t,langcode:location.search.includes('en')?'en':'ru'}}><div style={{position:'relative',height:'100vh'}}>{auth!==false&&show&&<IpHealthPanel/>}</div>{auth===false&&<LoginDialog/>}</TranslationContext.Provider>}
 createRoot(document.getElementById('root')).render(<QueryClientProvider client={queryClient}><App/></QueryClientProvider>);
 `},bundle:true,write:false,jsx:'automatic',platform:'browser',format:'iife',logLevel:'silent',tsconfig:join(web,'tsconfig.app.json'),define:{'process.env.APP_VERSION':'"0.1.4"'},plugins:process.env.NFQWS_IP_HEALTH_BASELINE_CLIENT?[{name:'baseline-client',setup(b){b.onLoad({filter:/api\/ipHealthClient\.ts$/},async()=>({contents:await readFile(process.env.NFQWS_IP_HEALTH_BASELINE_CLIENT,'utf8'),loader:'ts',resolveDir:join(web,'src/api')}));}}]:[]})).outputFiles[0].contents;
 server=createServer(async(req,res)=>{
  if(req.method!=='POST'){res.setHeader('Content-Type',req.url.startsWith('/fixture.js')?'text/javascript':'text/html');res.end(req.url.startsWith('/fixture.js')?js:'<!doctype html><div id="root"></div><script src="/fixture.js"></script>');return;}
  const f=fixtures.get(req.headers['x-fixture']);let raw='';for await(const b of req)raw+=b;
  const p=req.headers['content-type']?.startsWith('multipart/form-data')?new URLSearchParams([...await new Response(raw,{headers:{'Content-Type':req.headers['content-type']}}).formData()].map(([k,v])=>[k,String(v)])):new URLSearchParams(raw);
  const cmd=p.get('cmd');f.calls.push(Object.fromEntries(p));
  const reply=(v,status=200)=>{res.statusCode=status;res.setHeader('Content-Type','application/json');res.end(JSON.stringify(v));};
  const unauthorized=()=>{res.statusCode=401;res.end();};
  if(cmd==='status'){const finish=()=>{if(f.session==='503'){res.statusCode=503;res.end();return;}return f.session==='401'?unauthorized():reply({status:0,version:'1.3.2-asus6+b83',nfqws2:true,service:true,anonym:f.anonym,authenticated:!f.anonym&&f.session!=='unauth',csrf_token:f.token});};if(f.holdStatus){f.held.push(finish);return;}return finish();}
  if(cmd==='login'){f.session=f.holdAfterLogin?'unauth':'valid';f.holdStatus=!!f.holdAfterLogin;f.mutationUnauthorized=false;f.token='nonce-b';return reply({status:0});}
  if(f.session==='401'||(cmd!=='iphealthstatus'&&f.mutationUnauthorized))return unauthorized();
  if(p.get('csrf_token')!==f.token)return reply({error:'csrf_failed'},403);
  if(cmd==='iphealthstatus')return reply(f.data);
  if(cmd==='iphealthconfigure'){f.data={...f.data,enabled:p.get('enabled')==='1',revision:'b'.repeat(64)};return reply(f.data);}
  reply({error:'unexpected_command'},400);
 });
 await new Promise(r=>server.listen(0,'127.0.0.1',r));browser=await chromium.launch({headless:true,...(process.env.NFQWS_CHROMIUM_EXECUTABLE?{executablePath:process.env.NFQWS_CHROMIUM_EXECUTABLE}:{})});
 const count=(f,cmd)=>f.calls.filter(c=>c.cmd===cmd).length;
 const mutations=f=>f.calls.filter(c=>c.cmd?.startsWith('iphealth')&&c.cmd!=='iphealthstatus');
 for(const lang of ['ru','en']){
  const pack=JSON.parse(await readFile(join(web,`src/translations/${lang}.json`),'utf8'));
  const recover=lang==='ru'?'Обновить сессию':'Refresh session';
  const run=async(name,options,test)=>{
   if(process.env.NFQWS_IP_HEALTH_AUTH_CASE_FILTER&&!name.includes(process.env.NFQWS_IP_HEALTH_AUTH_CASE_FILTER))return;
   const f={anonym:false,session:'valid',token:'nonce-a',calls:[],held:[],data:{schema_version:1,revision:'a'.repeat(64),enabled:true,runtime:{state:'active',code:null,updated_at:1800000000,dns:'router_udp'},entries:[{id:'a'.repeat(32),ip:'8.8.8.8',port:443,host:'example.com',until:1900000000,first_seen:1800000000,incident:1,last_check:null,check_state:'silent'}]},...options};
   const id=`${lang}-${name}`;fixtures.set(id,f);const page=await browser.newPage({extraHTTPHeaders:{'x-fixture':id}});page.setDefaultTimeout(2500);const errors=[];page.on('pageerror',e=>errors.push(e.message));
   try{await page.clock.install();await page.goto(`http://127.0.0.1:${server.address().port}/?${lang}`);await page.getByText('8.8.8.8',{exact:true}).waitFor();await test(page,f);assert.deepEqual(errors,[]);console.log(`PASS ${id}`);}catch(e){failures.push(`${id}: ${e.message}`);console.error(`FAIL ${id}: ${e.message}`);}finally{f.held.splice(0).forEach(r=>r());await page.close();}
  };
  const login=async page=>{const d=page.getByRole('dialog').filter({has:page.getByLabel(pack.auth.password,{exact:true})});await d.getByLabel(pack.auth.username,{exact:true}).fill('fixture');await d.getByLabel(pack.auth.password,{exact:true}).fill('fixture-password');await d.getByRole('button',{name:pack.auth.login,exact:true}).click();};
  await run('anonymous-read-and-explicit-configure',{anonym:true},async(page,f)=>{assert.equal(mutations(f).length,0);await page.getByRole('switch',{name:pack.ip_health.toggle,exact:true}).click();await page.waitForFunction(()=>!document.querySelector('[aria-busy=true]'));assert.equal(mutations(f).length,1);assert.equal(mutations(f)[0].csrf_token,'nonce-a');assert.equal(await page.getByRole('alert').count(),0);});
  await run('anonymous-csrf-refresh-without-login-or-replay',{anonym:true},async(page,f)=>{f.token='nonce-b';await page.clock.fastForward(5001);await page.getByRole('button',{name:recover,exact:true}).waitFor();await page.getByRole('button',{name:recover,exact:true}).click();await page.waitForFunction(()=>!document.querySelector('[role=alert]'));assert.ok(count(f,'status')>=2);assert.equal(await page.getByLabel(pack.auth.password,{exact:true}).count(),0);assert.equal(mutations(f).length,0);await page.getByRole('switch',{name:pack.ip_health.toggle,exact:true}).click();await page.waitForFunction(()=>!document.querySelector('[aria-busy=true]'));assert.equal(mutations(f).at(-1).csrf_token,'nonce-b');});
  await run('empty503-session-refresh-keeps-visible-error',{},async(page,f)=>{f.token='nonce-b';await page.clock.fastForward(5001);await page.getByRole('button',{name:recover,exact:true}).waitFor();f.session='503';await page.getByRole('button',{name:recover,exact:true}).click();await page.getByText(pack.ip_health.errors.request_failed,{exact:true}).waitFor();assert.equal(await page.getByLabel(pack.auth.password,{exact:true}).count(),0);assert.equal(mutations(f).length,0);f.session='valid';await page.getByRole('button',{name:pack.ip_health.refresh,exact:true}).click();await page.getByText('8.8.8.8',{exact:true}).waitFor();await page.waitForFunction(()=>!document.querySelector('[role=alert]'));assert.equal(mutations(f).length,0);});
  await run('empty401-global-login-never-replays-configure',{},async(page,f)=>{f.mutationUnauthorized=true;await page.getByRole('switch',{name:pack.ip_health.toggle,exact:true}).click();await page.getByRole('button',{name:recover,exact:true}).waitFor();f.session='401';await page.getByRole('button',{name:recover,exact:true}).click();await login(page);await page.getByText('8.8.8.8',{exact:true}).waitFor();assert.equal(mutations(f).length,1);await page.getByRole('switch',{name:pack.ip_health.toggle,exact:true}).click();await page.waitForFunction(()=>!document.querySelector('[aria-busy=true]'));assert.equal(mutations(f).length,2);assert.equal(mutations(f).at(-1).csrf_token,'nonce-b');});
  await run('protected200-local-login-never-replays-configure',{},async(page,f)=>{f.token='nonce-b';await page.clock.fastForward(5001);await page.getByRole('button',{name:recover,exact:true}).waitFor();f.session='unauth';await page.getByRole('button',{name:recover,exact:true}).click();await login(page);await page.waitForFunction(()=>!document.querySelector('[role=alert]'));assert.equal(mutations(f).length,0);assert.equal(count(f,'login'),1);});
  await run('local-cancel-held-status-cannot-reopen-login',{},async(page,f)=>{f.token='nonce-b';await page.clock.fastForward(5001);await page.getByRole('button',{name:recover,exact:true}).waitFor();f.session='unauth';await page.getByRole('button',{name:recover,exact:true}).click();f.holdAfterLogin=true;
   const sent=page.waitForRequest(r=>r.postData()?.includes('name="cmd"\r\n\r\nstatus\r\n'));await login(page);await sent;
   const d=page.getByRole('dialog').filter({has:page.getByLabel(pack.auth.password,{exact:true})});await d.getByRole('button',{name:pack.common.cancel,exact:true}).click();await d.waitFor({state:'hidden'});
   f.holdStatus=false;f.held.splice(0).forEach(r=>r());await page.evaluate(()=>new Promise(r=>setTimeout(r,300)));assert.equal(await page.getByRole('dialog').count(),0,'late recovery cannot reopen cancelled local sign-in');assert.equal(mutations(f).length,0);
  });
  await run('cancel-held-session-cannot-open-login',{},async(page,f)=>{f.token='nonce-b';await page.clock.fastForward(5001);await page.getByRole('button',{name:recover,exact:true}).waitFor();f.holdStatus=true;f.session='unauth';await page.getByRole('button',{name:recover,exact:true}).click();await page.evaluate(()=>window.fixture.hide());f.holdStatus=false;f.held.splice(0).forEach(r=>r());await page.evaluate(()=>new Promise(r=>setTimeout(r,100)));assert.equal(await page.getByRole('dialog').count(),0);assert.equal(mutations(f).length,0);});
 }
 assert.deepEqual(failures,[],'IP Health anonymous and session recovery regressions');
}finally{await browser?.close();if(server)await new Promise(r=>server.close(r));}

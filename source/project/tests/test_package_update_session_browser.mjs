import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from '../webui/web/node_modules/esbuild/lib/main.js';

const { chromium } = await import(process.env.NFQWS_PLAYWRIGHT_MODULE || 'playwright');
const web = fileURLToPath(new URL('../webui/web/', import.meta.url));
const installed = '1.3.2-asus6+b81';
const target = '1.3.2-asus6+b83';
const candidate = {
  revision: 'a'.repeat(64), package_version: target, core_version: '1.3.2-asus6',
  web_version: '0.1.4', build: 83, notes: 'Verified release',
  package: { family: 'armv7', filename: `nfqws2-asus_${target}_armv7.ipk`, size: 10, sha256: 'b'.repeat(64) },
};
const current = { state: 'current', code: null, candidate: null, installed_version: installed };
const available = { ...current, state: 'available', candidate };
const prepared = { id: 'c'.repeat(32), revision: candidate.revision, state: 'prepared', package_version: target, code: null, service_intent: null };
const fixtures = new Map();
const failures = [];
let server, browser;
try {
  // Real CurrentVersion, shared API/status/auth, updater hook/parser/dialog and
  // local + App-style global login. Only router HTTP is substituted.
  const bundle = await build({ external: ['/community/*'], stdin: { resolveDir: web, loader: 'tsx', contents: `
    import React from 'react'; import {createRoot} from 'react-dom/client';
    import {QueryClientProvider} from '@tanstack/react-query';
    import {queryClient,API} from './src/api/client';
    import {CurrentVersion} from './src/components/CurrentVersion';
    import {LoginDialog} from './src/components/LoginDialog';
    import {useAppStore} from './src/store/useAppStore';
    import {TranslationContext} from './src/context/TranslationContext';
    import ru from './src/translations/ru.json'; import en from './src/translations/en.json';
    const pack=location.search.includes('en')?en:ru;
    const t=(key,params={})=>(key.split('.').reduce((v,k)=>v?.[k],pack)||key).replace(/{{(\\w+)}}/g,(_,k)=>String(params[k]??''));
    function App(){const auth=useAppStore(s=>s.auth);window.fixture={
      overview:()=>queryClient.refetchQueries({queryKey:['package-update-overview'],type:'active'}),
      status:()=>API.invalidateStatus(),
    };return <TranslationContext.Provider value={{t}}><CurrentVersion/>{auth===false&&<LoginDialog/>}</TranslationContext.Provider>}
    createRoot(document.getElementById('root')).render(<QueryClientProvider client={queryClient}><App/></QueryClientProvider>);
  ` }, bundle: true, write: false, platform: 'browser', format: 'iife', jsx: 'automatic',
    tsconfig: join(web, 'tsconfig.app.json'), logLevel: 'silent', define: { 'process.env.APP_VERSION': '"0.1.4"' } });
  server = createServer(async (req, res) => {
    if (req.method !== 'POST') {
      res.setHeader('Content-Type', req.url.startsWith('/fixture.js') ? 'text/javascript' : 'text/html');
      res.end(req.url.startsWith('/fixture.js') ? bundle.outputFiles[0].contents : '<!doctype html><html><div id="root"></div><script src="/fixture.js"></script></html>'); return;
    }
    const f = fixtures.get(req.headers['x-fixture']);
    let raw=''; for await(const b of req) raw+=b;
    const p=req.headers['content-type']?.startsWith('multipart/form-data')
      ? new URLSearchParams([...await new Response(raw,{headers:{'Content-Type':req.headers['content-type']}}).formData()].map(([k,v])=>[k,String(v)])) : new URLSearchParams(raw);
    const cmd=p.get('cmd'); f.calls.push(Object.fromEntries(p));
    const reply=(value,status=200)=>{res.statusCode=status;res.setHeader('Content-Type','application/json');res.end(JSON.stringify(value));};
    const fault=code=>{if(code==='empty401'){res.statusCode=401;res.end();}else reply({error:code},code==='auth_required'?401:403);};
    if(cmd==='status') {
      const finish=()=>{if(f.session==='401')return fault('empty401');if(f.session==='503'){res.statusCode=503;res.end();return;}reply({status:0,nfqws2:true,service:false,version:f.version,anonym:f.anonym,authenticated:f.session!=='unauth'&&!f.anonym,csrf_token:f.token,username:'fixture'});};
      if(f.holdSession){f.held.push(finish);return;} finish();return;
    }
    if(cmd==='login') { if(f.loginFailures){f.loginFailures--;return fault('empty401');}f.session='valid';f.fault=undefined;f.mutationFault=undefined;f.token='nonce-b';reply({status:0});return; }
    if(f.fault)return fault(f.fault);
    if(cmd==='packageupdatestatus')return reply(f.overview);
    if(cmd==='packageupdatecheck') {
      if(f.checking)f.overview={...f.overview,check:{...current,state:'checking',installed_version:f.version}};
      return reply(f.overview.check);
    }
    if(cmd==='packageupdateprepare'||cmd==='packageupdateapply') {
      if(f.mutationFault)return fault(f.mutationFault);
      return reply({...prepared,state:cmd==='packageupdateprepare'?'prepared':'applying'});
    }
    reply({error:'unexpected_command'},400);
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  browser=await chromium.launch({headless:true,...(process.env.NFQWS_CHROMIUM_EXECUTABLE?{executablePath:process.env.NFQWS_CHROMIUM_EXECUTABLE}:{})});
  const count=(f,cmd)=>f.calls.filter(c=>c.cmd===cmd).length;
  const settle=p=>p.evaluate(()=>new Promise(r=>setTimeout(r,100)));
  for(const lang of ['ru','en']) {
    const locale=JSON.parse(await readFile(join(web,`src/translations/${lang}.json`),'utf8'));
    const pack=locale.package_update;
    const recover=lang==='ru'?'Обновить сессию':'Refresh session';
    const run=async(name,extra,test)=>{
      if(process.env.NFQWS_UPDATE_SESSION_CASE_FILTER&&!name.includes(process.env.NFQWS_UPDATE_SESSION_CASE_FILTER))return;
      const f={version:installed,token:'nonce-a',anonym:false,session:'valid',overview:{check:available,operation:null},...extra,calls:[],held:[]};
      const id=`${lang}-${name}`;fixtures.set(id,f);
      const page=await browser.newPage({extraHTTPHeaders:{'x-fixture':id}});page.setDefaultTimeout(2200);
      const errors=[];page.on('pageerror',e=>errors.push(e.message));
      await page.route('https://api.github.com/**',r=>r.fulfill({status:200,contentType:'application/json',body:'[]'}));
      try{
        await page.clock.install();await page.goto(`http://127.0.0.1:${server.address().port}/?${lang}`);
        await page.locator('.MuiChip-root').waitFor();await settle(page);
        await test(page,f);assert.deepEqual(errors,[]);console.log(`PASS ${id}`);
      }catch(e){failures.push(`${id}: ${e.message}`);console.error(`FAIL ${id}: ${e.message}`,JSON.stringify(f.calls),await page.locator('body').innerText());}
      finally{f.held.splice(0).forEach(r=>r());await page.close();}
    };
    const open=p=>p.locator('.MuiChip-root').click();
    const login=async p=>{const dialog=p.getByRole('dialog').filter({has:p.getByLabel(locale.auth.password,{exact:true})});await dialog.waitFor();await dialog.getByLabel(locale.auth.username,{exact:true}).fill('fixture');await dialog.getByLabel(locale.auth.password,{exact:true}).fill('fixture-secret');await dialog.getByRole('button',{name:locale.auth.login,exact:true}).click();};
    await run('manual-check-refreshes-installed-version',{},async(p,f)=>{
      f.version=target;f.overview={check:{...current,installed_version:target},operation:null};
      await open(p);await p.getByRole('button',{name:pack.check,exact:true}).click();
      await p.waitForFunction(()=>document.querySelector('.MuiChip-root')?.textContent?.includes('Build 83'));
      assert.match(await p.locator('.MuiChip-root').textContent(),/Build 83/);
      assert.ok(count(f,'status')>=2,'manual check refreshes actual status after a manual IPK');
      assert.equal(count(f,'packageupdateprepare')+count(f,'packageupdateapply'),0);
    });
    await run('manual-ipk-checking-never-retains-old-candidate',{},async(p,f)=>{
      f.version=target;f.overview={check:{...current,state:'checking',installed_version:target},operation:null};
      await open(p);await p.getByRole('button',{name:pack.check,exact:true}).click();
      await p.waitForFunction(()=>document.querySelector('.MuiChip-root')?.textContent?.includes('Build 83'));
      await settle(p);assert.equal(await p.getByRole('button',{name:pack.prepare,exact:true}).count(),0,'a prior candidate cannot survive a changed installed version');
      assert.equal(count(f,'packageupdateprepare')+count(f,'packageupdateapply'),0);
    });
    await run('failed-status-cannot-accept-cached-session',{},async(p,f)=>{
      await open(p);const checks=count(f,'packageupdatecheck');f.session='503';
      await p.getByRole('button',{name:pack.check,exact:true}).click();await settle(p);
      assert.equal(count(f,'packageupdatecheck'),checks,'an empty failed status must not validate cached data');
      assert.equal(await p.getByRole('dialog').filter({has:p.getByLabel(locale.auth.password,{exact:true})}).count(),0);
      assert.equal(count(f,'packageupdateprepare')+count(f,'packageupdateapply'),0);
    });
    for(const state of ['available','failed'])await run(`background-keeps-${state}-result`,{overview:{check:state==='available'?available:{...current,state:'failed',code:'pending_packages'},operation:null}},async(p,f)=>{
      await open(p);const before=await p.getByRole('dialog').textContent();
      const height=(await p.getByRole('dialog').boundingBox()).height;
      f.checking=true;await p.clock.fastForward(300001);await settle(p);
      assert.ok((await p.getByRole('dialog').textContent()).includes(state==='available'?pack.available.replace('{{version}}','1.3.2-asus6 — Build 83'):pack.pending_packages),'background checking retains its last settled result');
      assert.equal((await p.getByRole('dialog').boundingBox()).height,height,'background progress must not move or resize the dialog');
      if(state==='available'){
        assert.equal(await p.locator('.MuiChip-colorWarning').count(),1);
        assert.equal(await p.getByRole('button',{name:pack.prepare,exact:true}).isEnabled(),false,'a preserved candidate is not actionable until its refresh settles');
      }
      f.checking=false;f.overview={check:state==='available'?available:{...current,state:'failed',code:'pending_packages'},operation:null};await p.evaluate(()=>window.fixture.overview());
      assert.equal(await p.getByRole('dialog').textContent(),before);
      assert.equal(count(f,'packageupdateprepare')+count(f,'packageupdateapply'),0);
    });
    await run('background-does-not-open-closed-dialog',{},async(p,f)=>{
      f.checking=true;await p.clock.fastForward(300001);await settle(p);
      assert.equal(await p.getByRole('dialog').count(),0);assert.equal(await p.locator('.MuiChip-colorWarning').count(),1);
      assert.equal(count(f,'packageupdateprepare')+count(f,'packageupdateapply'),0);
    });
    for(const action of ['prepare','apply'])await run(`empty401-${action}-signin-does-not-replay`,{overview:{check:available,operation:action==='apply'?prepared:null}},async(p,f)=>{
      await open(p);f.mutationFault='empty401';
      await p.getByRole('button',{name:action==='apply'?pack.install:pack.prepare,exact:true}).click();
      await p.getByRole('button',{name:recover,exact:true}).waitFor();
      f.session='401';await p.getByRole('button',{name:recover,exact:true}).click();await login(p);
      await p.getByRole('dialog',{name:pack.title,exact:true}).waitFor();await settle(p);
      assert.equal(count(f,`packageupdate${action}`),1,'sign-in never replays an ambiguous mutation');
      await p.getByRole('button',{name:action==='apply'?pack.install:pack.prepare,exact:true}).click();await settle(p);
      assert.equal(count(f,`packageupdate${action}`),2,'retry remains an explicit action');
      assert.equal(f.calls.filter(c=>c.cmd===`packageupdate${action}`).at(-1).csrf_token,'nonce-b');
    });
    await run('csrf403-refreshes-anonymous-session-without-login',{anonym:true},async(p,f)=>{
      await open(p);f.fault='csrf_failed';await p.evaluate(()=>window.fixture.overview());
      await p.getByRole('button',{name:recover,exact:true}).waitFor();f.fault=undefined;f.token='nonce-b';
      await p.getByRole('button',{name:recover,exact:true}).click();await settle(p);
      assert.equal(await p.getByRole('dialog').filter({has:p.getByLabel(locale.auth.password,{exact:true})}).count(),0);
      await p.getByRole('button',{name:pack.prepare,exact:true}).click();await settle(p);
      assert.equal(count(f,'packageupdateprepare'),1);assert.equal(f.calls.find(c=>c.cmd==='packageupdateprepare').csrf_token,'nonce-b');
    });
    await run('protected200-unauth-opens-one-local-login',{},async(p,f)=>{
      await open(p);f.fault='csrf_failed';await p.evaluate(()=>window.fixture.overview());
      await p.getByRole('button',{name:recover,exact:true}).waitFor();f.session='unauth';
      await p.getByRole('button',{name:recover,exact:true}).click();await login(p);await settle(p);
      assert.equal(await p.getByRole('dialog').filter({has:p.getByLabel(locale.auth.password,{exact:true})}).count(),0);
      assert.equal(count(f,'login'),1);assert.equal(count(f,'packageupdateprepare')+count(f,'packageupdateapply'),0);
    });
    await run('rejected-local-login-hands-off-once',{},async(p,f)=>{
      await open(p);f.fault='csrf_failed';await p.evaluate(()=>window.fixture.overview());
      await p.getByRole('button',{name:recover,exact:true}).waitFor();f.session='unauth';f.loginFailures=1;
      await p.getByRole('button',{name:recover,exact:true}).click();await login(p);await settle(p);
      assert.equal(await p.getByRole('dialog').filter({has:p.getByLabel(locale.auth.password,{exact:true})}).count(),1,'a rejected local login hands off to exactly one global login');
      await login(p);await settle(p);
      await p.waitForFunction(()=>!document.querySelector('button.Mui-disabled'));
      assert.equal(await p.getByRole('button',{name:pack.prepare,exact:true}).isEnabled(),true);
      assert.equal(await p.getByRole('button',{name:recover,exact:true}).count(),0);
      assert.equal(count(f,'login'),2);assert.equal(count(f,'packageupdateprepare')+count(f,'packageupdateapply'),0);
    });
    await run('cancel-held-session-does-not-open-local-login',{},async(p,f)=>{
      await open(p);f.fault='csrf_failed';await p.evaluate(()=>window.fixture.overview());await p.getByRole('button',{name:recover,exact:true}).waitFor();
      f.holdSession=true;f.session='unauth';await p.getByRole('button',{name:recover,exact:true}).click();await settle(p);
      await p.getByRole('button',{name:pack.close,exact:true}).click();f.holdSession=false;f.held.splice(0).forEach(r=>r());await settle(p);
      await p.waitForFunction(()=>!document.querySelector('[role=dialog]'));assert.equal(count(f,'packageupdateprepare')+count(f,'packageupdateapply'),0);
    });
  }
  assert.deepEqual(failures,[],'package update session and passive refresh regressions');
}finally{await browser?.close();if(server)await new Promise(r=>server.close(r));}

import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {build} from '../webui/web/node_modules/esbuild/lib/main.js';

const {chromium}=await import(process.env.NFQWS_PLAYWRIGHT_MODULE || 'playwright');
const web=fileURLToPath(new URL('../webui/web/',import.meta.url));
let server,browser;
try {
  const bundle=await build({stdin:{resolveDir:web,loader:'tsx',contents:`
    import React,{useState} from 'react';import {createRoot} from 'react-dom/client';
    import {PackageUpdateDialog} from './src/components/PackageUpdateDialog';
    import {TranslationContext} from './src/context/TranslationContext';
    import ru from './src/translations/ru.json';import en from './src/translations/en.json';
    const pack=location.search.includes('en')?en:ru;
    const t=(key,params)=>{const text=key.split('.').reduce((v,k)=>v?.[k],pack);return params?text.replace(/{{(\\w+)}}/g,(_,k)=>String(params[k]??'')):text;};
    const base={pending:false,checking:false,error:null,refresh(){},prepare(){},apply(){},data:{check:{state:'current',code:null,candidate:null,installed_version:'1.3.2-asus6+b86'},operation:null}};
    function App(){const [props,setProps]=useState({updates:base});window.fixture={set:(value)=>setProps({updates:{...base,...value}})};
      return <TranslationContext.Provider value={{t}}><PackageUpdateDialog open onClose={()=>{}} installed="1.3.2-asus6+b86" {...props}/></TranslationContext.Provider>;}
    createRoot(document.getElementById('root')).render(<App/>);
  `},bundle:true,write:false,platform:'browser',format:'iife',jsx:'automatic',tsconfig:join(web,'tsconfig.app.json'),logLevel:'silent'});
  server=createServer((req,res)=>{res.setHeader('Content-Type',req.url.startsWith('/fixture.js')?'text/javascript':'text/html');res.end(req.url.startsWith('/fixture.js')?bundle.outputFiles[0].contents:'<!doctype html><html><body><div id="root"></div><script src="/fixture.js"></script></body></html>');});
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  browser=await chromium.launch({headless:true,...(process.env.NFQWS_CHROMIUM_EXECUTABLE?{executablePath:process.env.NFQWS_CHROMIUM_EXECUTABLE}:{})});
  for(const lang of ['ru','en']) for(const width of [1280,390]) {
    const p=await browser.newPage({viewport:{width,height:844}});p.setDefaultTimeout(2500);
    const errors=[];p.on('pageerror',e=>errors.push(e.message));
    await p.goto(`http://127.0.0.1:${server.address().port}/?${lang}`);
    const pack=JSON.parse(await readFile(join(web,`src/translations/${lang}.json`),'utf8')).package_update;
    const operation={id:'c'.repeat(32),revision:'a'.repeat(64),state:'applying',phase:'installing',package_version:'1.3.2-asus6+b87',code:null,service_intent:null};
    const check={state:'current',code:null,candidate:null,installed_version:'1.3.2-asus6+b86'};
    const set=async (operation,extra={})=>{await p.evaluate(({operation,check,extra})=>window.fixture.set({data:{check,operation},...extra}),{operation,check,extra});};
    await p.getByRole('dialog').waitFor();
    // Passive checks must use the same reserved space whether idle or polling.
    const idleHeight=(await p.getByRole('dialog').boundingBox()).height;
    await p.evaluate(()=>window.fixture.set({checking:true}));
    await p.getByRole('progressbar').waitFor();
    assert.equal((await p.getByRole('dialog').boundingBox()).height,idleHeight);
    await set(operation);
    await p.waitForFunction(()=>document.querySelector('[role="progressbar"]')?.getAttribute('aria-valuenow')==='71');
    assert.ok((await p.getByRole('dialog').innerText()).includes('71%'));
    assert.ok((await p.getByRole('dialog').innerText()).includes(pack.stage_installing));
    assert.ok((await p.getByRole('dialog').innerText()).includes(pack.progress_hint));
    // A connection error leaves the last known stage; it cannot label the
    // backend operation as failed or show the original-failure field.
    await set(operation,{error:'request_failed'});
    await p.getByRole('button',{name:pack.copy_error,exact:true}).waitFor();
    assert.ok((await p.getByRole('dialog').innerText()).includes(pack.request_failed));
    assert.ok(!(await p.getByRole('dialog').innerText()).includes(pack.failed_stage.replace('{{stage}}',pack.stage_installing)));
    assert.equal(await p.getByRole('progressbar').getAttribute('aria-valuenow'),'71');
    const failed={...operation,state:'failed',phase:'finished',failure_phase:'installing',failure_code:'install_failed',code:'update_rolled_back'};
    await set(failed,{error:'auth_required'});
    const stopped=pack.failed_stage.replace('{{stage}}',pack.stage_installing);
    await p.getByText(stopped,{exact:true}).waitFor();
    assert.ok((await p.getByRole('dialog').innerText()).includes('install_failed'));
    assert.ok((await p.getByRole('dialog').innerText()).includes('update_rolled_back'));
    assert.equal(await p.getByRole('progressbar').getAttribute('aria-valuenow'),'71');
    assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'update details must fit a narrow screen');
    if(process.env.NFQWS_UPDATE_PROGRESS_SCREENSHOTS) await p.screenshot({path:`${process.env.NFQWS_UPDATE_PROGRESS_SCREENSHOTS}/${lang}-${width}.png`});
    // Force the production HTTP clipboard fallback inside the real MUI modal.
    await p.evaluate(()=>{Object.defineProperty(navigator,'clipboard',{configurable:true,value:undefined});window.copied='';document.execCommand=command=>{if(command!=='copy')return false;window.copied=document.activeElement.value;return true;};});
    await p.getByRole('button',{name:pack.copy_error,exact:true}).click();
    await p.getByRole('status').filter({hasText:pack.error_copied}).waitFor();
    const copied=await p.evaluate(()=>window.copied);
    for(const text of ['1.3.2-asus6+b86','1.3.2-asus6+b87',pack.stage_installing,'install_failed','update_rolled_back','auth_required','c'.repeat(32)])assert.ok(copied.includes(text),`${text}: ${JSON.stringify(copied)}`);
    assert.equal(await p.getByRole('button',{name:pack.copy_error,exact:true}).evaluate(el=>el===document.activeElement),true,'copy restores button focus');
    await p.evaluate(()=>{document.execCommand=()=>false;});
    await p.getByRole('button',{name:pack.copy_error,exact:true}).click();
    await p.getByRole('status').filter({hasText:pack.error_copy_failed}).waitFor();
    // A backend backup timeout and a current sign-in problem are separate.
    const timeoutMessage=lang==='ru'?'Этап обновления превысил допустимое время.':'This update step exceeded its time limit.';
    await set({...failed,failure_phase:'backing_up',failure_code:'timed_out'},{error:'auth_required'});
    await p.getByText(pack.failed_stage.replace('{{stage}}',pack.stage_backing_up),{exact:true}).waitFor();
    assert.ok((await p.getByRole('dialog').innerText()).includes(timeoutMessage),'the original timeout must have a human explanation');
    assert.ok((await p.getByRole('dialog').innerText()).includes('timed_out'));
    assert.equal(await p.getByRole('alert').filter({hasText:pack.session}).count(),1,'the current error remains the session problem');
    assert.equal(await p.getByRole('progressbar').getAttribute('aria-valuenow'),'57');
    await p.evaluate(()=>{document.execCommand=()=>{window.copied=document.activeElement.value;return true;};});
    await p.getByRole('button',{name:pack.copy_error,exact:true}).click();
    await p.getByRole('status').filter({hasText:pack.error_copied}).waitFor();
    const timeoutCopy=await p.evaluate(()=>window.copied);
    for(const text of [timeoutMessage,pack.stage_backing_up,'timed_out','update_rolled_back','auth_required',pack.session])assert.ok(timeoutCopy.includes(text),text);
    assert.ok(timeoutCopy.includes(`${lang==='ru'?'Текущая ошибка':'Current error'}: ${pack.session}`),'the copied current error must not be replaced by the primary server failure');
    for(const code of ['timed_out','download_hash','download_failed','install_failed','web_start_failed','web_health_failed','version_mismatch']) {
      await set({...operation,state:'failed',phase:'finished',code});
      await p.getByRole('alert').filter({hasText:pack[code]}).waitFor();
    }
    // Old receipts have no original failure stage. Never manufacture 100%.
    await set({...operation,state:'failed',phase:'finished',code:'rollback_failed'});
    await p.getByText(pack.failed_stage.replace('{{stage}}',pack.stage_unknown),{exact:true}).waitFor();
    assert.notEqual(await p.getByRole('progressbar').getAttribute('aria-valuenow'),'100');
    assert.ok(!(await p.getByRole('dialog').innerText()).includes('100%'));
    assert.deepEqual(errors,[]);
    console.log(`PASS ${lang}-${width} percentage/stages, retained failure, transport distinction and accessible copy fallback`);
    await p.close();
  }
} finally {await browser?.close();if(server)await new Promise(resolve=>server.close(resolve));}

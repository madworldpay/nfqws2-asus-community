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
const luaFlow=process.env.NFQWS_TEST_SCOPE==='lua-flow';
try {
  await build({stdin:{resolveDir:web,loader:'tsx',contents:`
    import React, {useState} from 'react';import {createRoot} from 'react-dom/client';
    import {ImportDialog} from './src/components/ImportDialog';
    import {Layout} from './src/components/Layout';
    import {TranslationContext} from './src/context/TranslationContext';
    import {useAppStore} from './src/store/useAppStore';
    import ru from './src/translations/ru.json';import en from './src/translations/en.json';
    const pack=new URLSearchParams(location.search).get('lang')==='en'?en:ru;
    const t=k=>k.split('.').reduce((v,p)=>v?.[p],pack)||k;
    useAppStore.getState().setAuth(true);
    function Fixture(){const [open,setOpen]=useState(true);return open
      ? <ImportDialog onClose={()=>setOpen(false)}/>
      : <button onClick={()=>setOpen(true)}>Open import test</button>;}
    createRoot(document.getElementById('root')).render(<Layout><TranslationContext.Provider value={{t,langcode:pack===en?'en':'ru'}}><Fixture/></TranslationContext.Provider></Layout>);
  `},bundle:true,platform:'browser',format:'iife',outfile:join(dir,'fixture.js'),jsx:'automatic',logLevel:'silent',tsconfig:join(web,'tsconfig.app.json'),plugins:[{name:'status-boundary',setup(b){b.onLoad({filter:/hooks\/useStatus\.tsx$/},()=>({contents:'export const useStatus=()=>({csrfToken:"fixture-csrf",service:true,nfqws2:true,isReady:true,authenticated:true});',loader:'tsx'}));b.onLoad({filter:/components\/Editor\.tsx$/},()=>({contents:'import React from "react";export const Editor=({value})=><textarea readOnly value={value}/>;',loader:'tsx'}));}}]});
  const script=await readFile(join(dir,'fixture.js'));
  server=createServer((req,res)=>{res.setHeader('Content-Type',req.url==='/fixture.js'?'text/javascript':'text/html');res.end(req.url==='/fixture.js'?script:'<!doctype html><html><body><div id="root"></div><script src="/fixture.js"></script></body></html>');});
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  browser=await chromium.launch({headless:true,...(process.env.NFQWS_CHROMIUM_EXECUTABLE?{executablePath:process.env.NFQWS_CHROMIUM_EXECUTABLE}:{})});
  const context=await browser.newContext();
  const page=await context.newPage();page.setDefaultTimeout(4000);
  const base=`http://127.0.0.1:${server.address().port}`;
  const profile={id:'original',title:'Original name <script>',category:'global',provider:'',region:'',description:'Адаптация для ASUS. Результат зависит от провайдера.',attribution:'Example author',updated_at:'2026-10-23T12:00:00Z',revision:1,min_build:68,size:2,sha256:'a'.repeat(64)};
  const upstream={id:'example',label:'Example DoH',protocol:'doh',address:'1.1.1.1',port:443,tls_name:'cloudflare-dns.com',url:'https://cloudflare-dns.com/dns-query',bootstrap:['1.1.1.1'],default:true,domains:[{name:'example.com',include_subdomains:true}]};
  const record={name:'media.example.com',include_subdomains:false,addresses:['203.0.113.10'],checked_at:null};
  const document={values:{NFQWS_ARGS:'--filter-tcp=443',NFQWS_BASE_ARGS:'--debug=0'},ports:{TCP_PORTS:'443'},resources:[{id:'c'.repeat(32),kind:'lists',name:'example.list',encoding:'utf8',data_base64:'eA==',byte_length:1,sha256:'2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881',aliases:[]}],dns_sources:[{id:'draft',origin:'draft',sha256:'d'.repeat(64),profile:{schema_version:1,upstreams:[upstream],records:[record]},complete:true,warnings:[]}],dependencies:[],audit:null,context:{purpose:'Selected example',operator:'Example'},source:null,ignored:[],input_sha256:'b'.repeat(64)};
  const calls=[],selections=[];let offline=false,catalogError='catalog_unavailable';
  const localPack=JSON.parse(await readFile(join(web,'public/zapret2-pack/catalog.json'),'utf8'));
  let localResponse=localPack;
  const idle={state:'idle',id:null,can_undo:false,config_saved:false,dns_draft_saved:false};
  let receipt=idle;
  let profiles=[{...profile,id:'provider',title:'Provider preset',category:'provider',provider:'Example ISP',region:'Example region',description:'Адаптация под АСУС. Проверено TCP 8/10. Результат зависит от провайдера.'},profile];
  const bodies=[];
  await page.context().route('**/index.php',async route=>{
    const request=route.request();
    const post=await new Response(request.postDataBuffer(),{
      headers:{'content-type':request.headers()['content-type']},
    }).formData();
    const cmd=post.get('cmd');calls.push(cmd);
    bodies.push([...post.values()].join('\n'));
    let body;
    if(cmd==='importlocalpack')return route.fulfill({json:localResponse});
    if(cmd==='importlocalentry')return route.fulfill({json:{documents:['{}','{}']}});
    if(cmd==='importstatus')body=receipt;
    else if(cmd==='importcatalog')body=offline?{error:catalogError}:{schema_version:1,revision:1,build:68,profiles};
    else if(cmd==='importaddoncatalog')body={schema_version:1,revision:1,build:92,addons:[]};
    else if(cmd==='importcatalogload'){await new Promise(resolve=>setTimeout(resolve,100));body={document:'{}'};}
    else if(cmd==='importinspect')body=document;
    else if(cmd==='importprepare'){
      const selection=JSON.parse(post.get('selection'));selections.push(selection);
      body={ready:false,problems:[],warnings:[],required:{files:[],shared:[]},affected_blocks:[],config:'',changes:[],files:[],draft:null,old_draft:null,digest:'e'.repeat(64),proof:null};
      if(luaFlow)Object.assign(body,{
        ready:selection.trusted_lua,
        proof:selection.trusted_lua?'fixture-proof':null,
        problems:selection.trusted_lua?[]:[{code:'lua_trust'}],
        warnings:[{kind:'lua_dependencies_unchecked',source:'lua'},{kind:'inventory_partial',source:'inventory'}],
        changes:[{key:'NFQWS_ARGS',before:'old strategy rule',after:'new strategy rule'}],
      });
    }
    else if(luaFlow&&cmd==='importapply'){
      assert.equal(JSON.parse(post.get('selection')).trusted_lua,true);
      assert.equal(post.get('proof'),'fixture-proof');
      body=receipt={...idle,state:'committed',id:post.get('request_id'),can_undo:true,config_saved:true};
    }
    else if(luaFlow&&cmd==='restart')body={status:0,output:[]};
    else throw new Error('Unexpected mutation or request: '+cmd);
    await route.fulfill({status:offline&&cmd==='importcatalog'?503:200,contentType:'application/json',body:JSON.stringify(body)});
  });
  if(!['local-pack','catalog-cards','notes','lua-flow'].includes(process.env.NFQWS_TEST_SCOPE)){
  await page.goto(base);assert.equal(calls.includes('importcatalog'),false,'Catalog is fetched only when requested');
  await page.getByRole('button',{name:'Из облака',exact:true}).click();
  await page.getByText('Глобальные стратегии',{exact:true}).waitFor();
  await page.getByText('Профили провайдеров',{exact:true}).waitFor();
  assert.equal(await page.locator('script').count(),1,'Preset title stays escaped text');
  const item=page.getByRole('button',{name:/Original name/});await item.dblclick();
  await page.getByText('Selected example',{exact:false}).first().waitFor();
  assert.equal(calls.filter(x=>x==='importcatalogload').length,1,'Rapid clicks load the preset only once');
  assert.equal(calls.filter(x=>x==='importinspect').length,1);
  const strategy=page.getByRole('checkbox',{name:'Базовая стратегия',exact:true});assert.equal(await strategy.isChecked(),true,'Cloud preset starts with the author composition selected');
  assert.equal(calls.includes('importprepare')||calls.includes('importapply'),false);
  await Promise.all([page.waitForResponse(r=>r.url().endsWith('/index.php')&&new URLSearchParams(r.request().postData()).get('cmd')==='importprepare'),page.getByRole('button',{name:'Предпросмотр',exact:true}).filter({hasText:'Предпросмотр'}).click()]);
  assert.deepEqual(selections[0].blocks,[{key:'NFQWS_ARGS',value:document.values.NFQWS_ARGS}]);assert.deepEqual(selections[0].shared,[{key:'NFQWS_BASE_ARGS',value:document.values.NFQWS_BASE_ARGS}]);assert.deepEqual(selections[0].ports,[{key:'TCP_PORTS',value:'443'}]);assert.deepEqual(selections[0].files,[{id:'c'.repeat(32)}]);assert.deepEqual(selections[0].dns[0].upstreams,[upstream]);assert.deepEqual(selections[0].dns[0].records,[{index:0,value:record}]);assert.equal(selections[0].trusted_lua,false);
  await strategy.uncheck();assert.equal(await strategy.isChecked(),false,'Recipient may remove any selected block');assert.equal(calls.includes('importapply'),false);
  offline=true;await page.goto(base);await page.getByRole('button',{name:'Из облака',exact:true}).click();
  await page.getByText(/Каталог сейчас недоступен/).waitFor();
  await page.locator('input[type=file]').setInputFiles({name:'Профиль Windows.json',mimeType:'',buffer:Buffer.from('{}')});
  await page.getByText('Selected example',{exact:false}).first().waitFor();
  assert.equal(await page.getByRole('checkbox',{name:'Базовая стратегия',exact:true}).isChecked(),true,'A new local JSON resets the full selection after previous opt-out');
  assert.ok(calls.filter(x=>x==='importinspect').length===2,'Local file still enters the same import flow while catalog is unavailable');
  for(const lang of ['ru','en']) {
    const locale=JSON.parse(await readFile(join(web,`src/translations/${lang}.json`),'utf8'));
    for(const code of ['catalog_dns','catalog_tls','catalog_connect','catalog_runtime','catalog_http','catalog_timeout','unauthorized','forbidden','UNEXPECTED_PRIVATE_CANARY','']) {
      offline=true;catalogError=code;
      await page.goto(base+'/?lang='+lang);
      await page.getByRole('button',{name:lang==='en'?'From cloud':'Из облака',exact:true}).click();
      const expected=locale.import.catalog.errors?.[code] ?? locale.import.catalog.offline;
      await page.getByText(expected,{exact:true}).waitFor();
      assert.equal((await page.locator('body').innerText()).includes('UNEXPECTED_PRIVATE_CANARY'),false);
      assert.equal(calls.includes('importapply'),false,'diagnostics never apply a profile');
    }
  }
  offline=false;await page.goto(base+'/?lang=en');await page.getByRole('button',{name:'From cloud',exact:true}).click();await page.getByText('Global strategies',{exact:true}).waitFor();await page.getByText('Provider presets',{exact:true}).waitFor();await page.getByText('From computer (JSON)',{exact:true}).waitFor();
  console.log('PASS actual import dialog: local/VPS sources, two categories, escaped names, complete author selection with recipient opt-out, no automatic apply, rapid-click guard and offline local fallback');
  }
  if(process.env.NFQWS_TEST_SCOPE==='catalog-cards'){
    await page.goto(base);
    await page.getByRole('button',{name:'Из облака',exact:true}).click();
    const original=page.getByRole('button',{name:/Original name/});
    await original.waitFor();
    assert.doesNotMatch(await original.innerText(),/адаптаци|зависит от провайдера/i);
    assert.match(await original.innerText(),/Example author/);
    assert.equal(await original.locator('time').innerText(),'Обновлено: 23.10.2026');
    assert.equal(await original.locator('.MuiListItemText-secondary > .MuiTypography-body2').count(),0,'An empty description must not leave a row');
    const provider=page.getByRole('button',{name:/Provider preset/});
    assert.equal(await provider.locator('.MuiListItemText-secondary > .MuiTypography-body2').innerText(),'Проверено TCP 8/10.');
  }
  if(process.env.NFQWS_TEST_SCOPE==='notes'){
    const open=async(p,source,lang='ru')=>{
      await p.goto(base+'/?lang='+lang);
      const title=source==='cloud'?(lang==='ru'?'Из облака':'From cloud'):(lang==='ru'?'Библиотека Zapret2':'Zapret2 library');
      await p.getByRole('button',{name:title,exact:true}).click();
      await p.getByRole('textbox',{name:/^(Моя заметка|My note) — /}).first().waitFor();
    };
    const note=(p,title,lang='ru')=>p.getByRole('textbox',{name:(lang==='ru'?'Моя заметка':'My note')+' — '+title,exact:true});
    const [first,second]=localPack.entries;
    const marker='Личный тест 729';
    await open(page,'library');
    await note(page,first.title).fill(marker);
    await note(page,second.title).fill('Своя отдельная заметка');
    const row=note(page,first.title).locator('..');
    const [buttonBox,inputBox]=await Promise.all([row.getByRole('button').boundingBox(),note(page,first.title).boundingBox()]);
    assert.ok(inputBox.x>=buttonBox.x+buttonBox.width-1,'The note is directly to the right of its own strategy');
    assert.equal(calls.includes('importlocalentry'),false,'Editing never selects or imports');
    const search=page.getByRole('searchbox');
    await search.fill('729 лИчНый');assert.equal(await page.getByRole('textbox',{name:/Моя заметка —/}).count(),1);
    await note(page,first.title).fill('Новое личное описание');
    assert.equal(await note(page,first.title).inputValue(),'Новое личное описание','Editing a note-only match keeps keyboard focus');
    await search.focus();
    assert.equal(await note(page,first.title).count(),0);
    // Same publisher identifiers, new content, labels, order and a replacement entry with the old title.
    localResponse={...localPack,entries:[{...first,id:'eeeeeeeeeeeeeeeeeeeeeeee'},second,{...first,title:'Переименованный пресет',sha256:'9'.repeat(64)}]};
    await open(page,'library');
    assert.equal(await note(page,'Переименованный пресет').inputValue(),'Новое личное описание');
    assert.equal(await note(page,second.title).inputValue(),'Своя отдельная заметка');
    assert.equal(await note(page,first.title).inputValue(),'');
    const peer=await page.context().newPage();await open(peer,'library');
    await note(peer,second.title).fill('Из соседней вкладки');
    await page.waitForFunction(()=>[...document.querySelectorAll('textarea')].some(el=>el.value==='Из соседней вкладки'));
    await note(page,'Переименованный пресет').fill('');await peer.close();
    await open(page,'library');assert.equal(await note(page,'Переименованный пресет').inputValue(),'');
    profiles=[{...profile,id:first.id,title:second.title},profile];
    await open(page,'cloud');
    assert.equal(await note(page,second.title).inputValue(),'','Overlapping catalog IDs and titles never share notes');
    await note(page,second.title).fill(marker);
    profiles=[profile,{...profiles[0],title:'Updated cloud title',category:'provider',revision:2,sha256:'b'.repeat(64)}];
    await page.getByRole('button',{name:'Обновить список'}).click();
    await search.fill('729');assert.equal(await note(page,'Updated cloud title').inputValue(),marker);
    assert.equal(await page.getByRole('textbox',{name:/Моя заметка —/}).count(),1);
    await page.evaluate(()=>{Storage.prototype.setItem=function(){throw new DOMException('Full','QuotaExceededError')}});
    await note(page,'Updated cloud title').fill('Временный текст');
    await page.getByText(/Браузер не смог прочитать или сохранить заметки/).waitFor();
    assert.equal(await note(page,'Updated cloud title').inputValue(),'Временный текст');
    await open(page,'cloud');assert.equal(await note(page,'Updated cloud title').inputValue(),marker);
    assert.ok(!calls.includes('importcatalogload')&&!calls.includes('importapply')&&!bodies.some(v=>v.includes(marker)));
    localResponse=localPack;
    if(process.env.NFQWS_NOTES_SCREENSHOTS){
      await page.setViewportSize({width:1230,height:930});
      await page.emulateMedia({colorScheme:'dark'});
      for(const lang of ['ru','en']){
        await open(page,'library',lang);
        const list=page.getByRole('list',{name:lang==='ru'?'Библиотека Zapret2':'Zapret2 library'});
        const word='ATV';
        await note(page,'ALL TCP & UDP YTDisBystro_3_4_v1',lang).fill(word+' · '+(lang==='ru'?'проверить вечером':'try this evening'));
        await note(page,'ALL TCP & UDP multisplit_sni',lang).fill(word+' · '+(lang==='ru'?'запасной вариант':'second choice'));
        await search.fill(word);assert.equal(await list.getByRole('textbox').count(),2);
        await search.focus();
        const section=list.locator('..');await section.scrollIntoViewIfNeeded();
        const {x,y,width,height}=await section.boundingBox();
        await page.screenshot({path:join(process.env.NFQWS_NOTES_SCREENSHOTS,'build100-import-notes-'+lang+'.png'),
          clip:{x:x-9,y:y-10,width:width+18,height:height+18},animations:'disabled'});
      }
    }
    console.log('PASS strategy notes: right-aligned fields, private storage, cross-tab edits, text search, publisher revisions and identifier isolation');
  }
  if(luaFlow){
    const button=(name)=>page.getByRole('button',{name,exact:true});
    const save=button('Сохранить выбранное');
    const restart=button('Перезапустить NFQWS2');
    const trust=page.getByRole('checkbox',{name:/Доверяю источнику/});
    await page.goto(base);
    await button('Библиотека Zapret2').click();
    const cards=page.getByRole('list',{name:'Библиотека Zapret2'}).getByRole('button');
    await cards.first().click();
    await button('Предпросмотр').filter({hasText:'Предпросмотр'}).click();
    await page.getByText('old strategy rule',{exact:true}).waitFor();
    await page.getByText('new strategy rule',{exact:true}).waitFor();
    assert.equal(await trust.isChecked(),false);
    assert.equal(await save.isDisabled(),true);
    await trust.check();
    await save.waitFor({state:'visible'});
    await page.getByText(/Изменения готовы к сохранению/).waitFor();
    assert.equal(await save.isEnabled(),true);
    assert.equal(await page.getByText('new strategy rule',{exact:true}).isVisible(),true);
    await trust.uncheck();
    await page.getByText(/Для сохранения этой стратегии подтвердите/).waitFor();
    assert.equal(await save.isDisabled(),true);
    assert.deepEqual(selections.map(s=>s.trusted_lua),[false,true,false]);
    assert.ok(!calls.includes('importapply')&&!calls.includes('restart'));
    await trust.check();
    await save.click();
    await restart.waitFor();
    assert.ok(!calls.includes('restart'),'Saving never starts or restarts the service');
    await cards.nth(1).click();
    assert.equal(await restart.isVisible(),true,'Choosing another preset keeps the pending restart');
    await button('Закрыть').click();
    await button('Open import test').click();
    await restart.waitFor();
    await restart.click();
    await page.getByText(/Команда выполнена/).waitFor();
    assert.equal(await restart.count(),0);
    assert.equal(calls.filter(cmd=>cmd==='restart').length,1);
    await button('Закрыть').click();
    await button('Open import test').click();
    await page.getByRole('button',{name:'Отменить последний импорт'}).waitFor();
    assert.equal(await restart.count(),0,'Confirmed activation stays cleared after reopening');
    console.log('PASS Lua consent, visible comparison, explicit save, pending restart across selection and reopening, explicit activation');
  }
  await page.setViewportSize({width:374,height:710});
  await page.goto(base);
  await page.getByRole('button',{name:'Библиотека Zapret2'}).click();
  const local=page.getByRole('list',{name:'Библиотека Zapret2'});
  await local.getByRole('button').first().waitFor();
  assert.equal(await local.getByRole('button').count(),98);
  const layout=await local.evaluate(el=>[el.scrollWidth,el.clientWidth,el.scrollHeight,el.clientHeight]);
  assert.ok(layout[0]<=layout[1]+1 && layout[2]>layout[3],JSON.stringify(layout));
  await page.getByRole('searchbox').fill('ytdisbystro_3_4_v1');
  const chosen=local.getByRole('button',{name:/ALL TCP & UDP YTDisBystro_3_4_v1/});
  await chosen.waitFor();
  assert.equal(await local.getByRole('link').count(),0);
  assert.match(await chosen.innerText(),/zapretdiscordyoutube\/magisk-zapret2/);
  assert.equal(await chosen.locator('time').innerText(),'Дата сборника: 01.11.2026');
  assert.doesNotMatch(await chosen.innerText(),/https?:\/\/|#L\d|адаптация (?:для|под)|зависит от провайдера/i);
  const before=calls.length;
  await chosen.click();
  await page.getByText('Selected example',{exact:false}).first().waitFor();
  assert.deepEqual(calls.slice(before).filter(cmd=>['importlocalentry','importinspect','importapply'].includes(cmd)),['importlocalentry','importinspect']);
  console.log('PASS local library: 98 presets, phone-width scrolling, plain credit/date, normal import selection');
}finally{await browser?.close();if(server)await new Promise(resolve=>server.close(resolve));await rm(dir,{recursive:true,force:true});}

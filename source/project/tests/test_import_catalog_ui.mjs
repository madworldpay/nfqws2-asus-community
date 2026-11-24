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
const action=(page,name)=>page.getByRole('button',{name,exact:true});
const tab=(page,name)=>page.getByRole('tab',{name,exact:true});
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
  const magiskPack=JSON.parse(await readFile(join(web,'public/zapret2-pack/catalog.json'),'utf8'));
  const supplemental=JSON.parse(await readFile(join(web,'public/zapret2-pack/collections.json'),'utf8'));
  const zemidala=JSON.parse(await readFile(join(web,'public/zapret2-pack/zemidala-index.json'),'utf8')).entries;
  const localPack={...magiskPack,entries:[...magiskPack.entries,...supplemental.entries,...zemidala],assets:[...magiskPack.assets,...supplemental.assets]};
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
    if(cmd==='importcatalog'||cmd==='importcatalogload')assert.equal(post.get('source'),'package');
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
      if(luaFlow&&JSON.parse(post.get('documents')).length===1)Object.assign(body,{
        ready:selection.trusted_lua,
        proof:selection.trusted_lua?'fixture-proof':null,
        problems:selection.trusted_lua?[]:[{code:'lua_trust'}],
        warnings:[{kind:'lua_dependencies_unchecked',source:'lua'},{kind:'inventory_partial',source:'inventory'}],
        changes:[{key:'NFQWS_ARGS',before:'old strategy rule',after:'new strategy rule'}],
      });
      else Object.assign(body,{
        ready:true,
        proof:'fixture-proof',
        warnings:[{kind:'inventory_partial',source:'inventory'}],
        changes:[{key:'NFQWS_ARGS',before:'old strategy rule',after:'new strategy rule'}],
      });
    }
    else if(cmd==='importapply'){
      const localPreset=JSON.parse(post.get('documents')).length===2;
      assert.equal(JSON.parse(post.get('selection')).trusted_lua,luaFlow&&!localPreset);
      assert.equal(post.get('proof'),'fixture-proof');
      body=receipt={...idle,state:'committed',id:post.get('request_id'),can_undo:true,config_saved:true};
    }
    else if(cmd==='restart')body={status:0,output:[]};
    else throw new Error('Unexpected mutation or request: '+cmd);
    await route.fulfill({status:offline&&cmd==='importcatalog'?503:200,contentType:'application/json',body:JSON.stringify(body)});
  });
  if(!['local-pack','catalog-cards','notes','lua-flow','source-marks','zemidala'].includes(process.env.NFQWS_TEST_SCOPE)){
  await page.goto(base);assert.equal(calls.includes('importcatalog'),false,'Catalog is fetched only when requested');
  await page.getByRole('button',{name:'Стратегии',exact:true}).click();
  await page.getByText('Глобальные стратегии',{exact:true}).waitFor();
  await page.getByRole('searchbox').fill('Example ISP');
  await page.getByText('Профили провайдеров',{exact:true}).waitFor();
  await page.getByRole('searchbox').clear();
  assert.equal(await page.locator('script').count(),1,'Preset title stays escaped text');
  const item=page.getByRole('button',{name:/Original name/});await item.dblclick();
  await action(page,'Применить').and(page.locator(':enabled')).waitFor();
  assert.equal(calls.filter(x=>x==='importcatalogload').length,1,'Rapid clicks load the preset only once');
  assert.equal(calls.filter(x=>x==='importinspect').length,1);
  assert.equal(await page.getByRole('tablist').count(),0);
  assert.equal(await action(page,'Перезапустить').isDisabled(),true);
  assert.equal(calls.includes('importapply'),false);
  await action(page,'Просмотр').click();
  await tab(page,'Состав').waitFor();
  const strategy=page.getByRole('checkbox',{name:'Базовая стратегия',exact:true});assert.equal(await strategy.isChecked(),true,'Cloud preset starts with the author composition selected');
  assert.equal(calls.filter(x=>x==='importprepare').length,1);
  assert.deepEqual(selections[0].blocks,[{key:'NFQWS_ARGS',value:document.values.NFQWS_ARGS}]);assert.deepEqual(selections[0].shared,[{key:'NFQWS_BASE_ARGS',value:document.values.NFQWS_BASE_ARGS}]);assert.deepEqual(selections[0].ports,[{key:'TCP_PORTS',value:'443'}]);assert.deepEqual(selections[0].files,[{id:'c'.repeat(32)}]);assert.deepEqual(selections[0].dns[0].upstreams,[upstream]);assert.deepEqual(selections[0].dns[0].records,[{index:0,value:record}]);assert.equal(selections[0].trusted_lua,false);
  await strategy.uncheck();assert.equal(await strategy.isChecked(),false,'Recipient may remove any selected block');assert.equal(calls.includes('importapply'),false);
  offline=true;await page.goto(base);await action(page,'Стратегии').click();
  await page.getByText('Не удалось открыть встроенные профили.',{exact:true}).waitFor();
  await page.getByRole('button',{name:/ALL TCP & UDP YTDisBystro_3_4_v1/}).waitFor();
  await page.locator('input[type=file]').setInputFiles({name:'Профиль Windows.json',mimeType:'',buffer:Buffer.from('{}')});
  await page.getByText('Selected example',{exact:false}).first().waitFor();
  assert.equal(await page.getByRole('checkbox',{name:'Базовая стратегия',exact:true}).isChecked(),true,'A new local JSON resets the full selection after previous opt-out');
  assert.ok(calls.filter(x=>x==='importinspect').length===2,'Local file still enters the same import flow while catalog is unavailable');
  for(const lang of ['ru','en']) {
    const locale=JSON.parse(await readFile(join(web,`src/translations/${lang}.json`),'utf8'));
    for(const code of ['catalog_dns','catalog_tls','catalog_connect','catalog_runtime','catalog_http','catalog_timeout','unauthorized','forbidden','UNEXPECTED_PRIVATE_CANARY','']) {
      offline=true;catalogError=code;
      await page.goto(base+'/?lang='+lang);
      await action(page,locale.import.strategies.choose).click();
      const expected=locale.import.strategies.package_unavailable;
      await page.getByText(expected,{exact:true}).waitFor();
      assert.equal((await page.locator('body').innerText()).includes('UNEXPECTED_PRIVATE_CANARY'),false);
      assert.equal(calls.includes('importapply'),false,'diagnostics never apply a profile');
    }
  }
  offline=false;await page.goto(base+'/?lang=en');await action(page,'Strategies').click();await page.getByText('Global strategies',{exact:true}).waitFor();await page.getByText('From computer (JSON)',{exact:true}).waitFor();
  console.log('PASS unified strategy import: package requests, source failure isolation, escaped names, complete author selection, no automatic apply and rapid-click guard');
  }
  if(process.env.NFQWS_TEST_SCOPE==='catalog-cards'){
    await page.goto(base);
    await action(page,'Стратегии').click();
    const original=page.getByRole('button',{name:/Original name/});
    await original.waitFor();
    assert.doesNotMatch(await original.innerText(),/адаптаци|зависит от провайдера/i);
    assert.match(await original.innerText(),/Example author/);
    assert.equal(await original.locator('time').innerText(),'Обновлено: 23.10.2026');
    assert.equal(await original.locator('.MuiListItemText-secondary > .MuiTypography-body2').count(),0,'An empty description must not leave a row');
    await page.getByRole('searchbox').fill('Проверено 8/10');
    const provider=page.getByRole('button',{name:/Provider preset/});
    assert.equal(await provider.locator('.MuiListItemText-secondary > .MuiTypography-body2').innerText(),'Проверено TCP 8/10.');
  }
  if(process.env.NFQWS_TEST_SCOPE==='source-marks'){
    await page.setViewportSize({width:1160,height:920});
    await page.emulateMedia({colorScheme:'dark'});
    await page.goto(base);
    await action(page,'Стратегии').click();
    const rail=page.getByRole('navigation',{name:'Быстрый переход по источникам'});
    const list=page.getByRole('list',{name:'Стратегии'});
    const magisk=rail.getByRole('button',{name:/zapretdiscordyoutube\/magisk-zapret2/});
    const avatar=rail.getByRole('button',{name:/avatarDD\/zapret-gui/});
    await avatar.waitFor();
    assert.equal(await rail.getByRole('button').count(),3);
    await avatar.click();
    const title=localPack.entries.find(entry=>entry.collection==='avatar').title;
    const row=await list.getByRole('button').filter({hasText:title}).first().boundingBox();
    const viewport=await list.boundingBox();
    assert.ok(row.y>=viewport.y && row.y<viewport.y+viewport.height);
    assert.ok(await list.evaluate(el=>el.scrollTop)>0);
    assert.equal(calls.includes('importlocalentry'),false);
    await avatar.hover();
    if(process.env.NFQWS_SOURCE_MARK_SCREENSHOT){
      await page.getByRole('tooltip').waitFor();
      await page.getByRole('dialog').screenshot({path:process.env.NFQWS_SOURCE_MARK_SCREENSHOT,animations:'disabled'});
    }
    await magisk.focus();await magisk.press('Enter');
    const magiskHeading=await list.getByRole('heading',{name:'zapretdiscordyoutube/magisk-zapret2'}).boundingBox();
    assert.ok(Math.abs(magiskHeading.y-viewport.y)<=1,'Keyboard jump reaches the start of the Magisk block');
    await page.getByRole('searchbox').fill('avatarDD');
    assert.equal(await list.getByRole('button').count(),4);
    await rail.waitFor({state:'hidden'});
    await page.getByRole('searchbox').clear();
    await page.setViewportSize({width:374,height:710});
    await avatar.waitFor();
    await avatar.click();
    const sizes=await list.evaluate(el=>[el.scrollWidth,el.clientWidth,el.scrollTop]);
    assert.ok(sizes[0]<=sizes[1]+1 && sizes[2]>0,JSON.stringify(sizes));
    assert.equal(calls.includes('importapply'),false);
    console.log('PASS source markers: source jumps, keyboard, filtered results and mobile layout');
  }
  if(process.env.NFQWS_TEST_SCOPE==='zemidala'){
    await page.setViewportSize({width:1160,height:920});
    await page.emulateMedia({colorScheme:'dark'});
    await page.goto(base);
    await action(page,'Стратегии').click();
    await page.getByRole('combobox').click();
    await page.getByRole('option',{name:'По провайдерам'}).click();
    const list=page.getByRole('list',{name:'Стратегии'});
    const rail=page.getByRole('navigation',{name:'Быстрый переход по источникам'});
    const marker=rail.getByRole('button',{name:/Zemidala/});
    await marker.click();
    await marker.hover();
    assert.equal(calls.includes('importlocalentry'),false);
    if(process.env.NFQWS_ZEMIDALA_SCREENSHOT){
      await page.getByRole('tooltip').waitFor();
      await page.getByRole('dialog').screenshot({path:process.env.NFQWS_ZEMIDALA_SCREENSHOT,animations:'disabled'});
    }
    await page.getByRole('searchbox').fill('Zemidala');
    assert.equal(await list.getByRole('button').count(),67);
    const choice=list.getByRole('button').first();
    await choice.click();
    await action(page,'Применить').and(page.locator(':enabled')).waitFor();
    await action(page,'Применить').click();
    assert.equal(calls.filter(x=>x==='importlocalentry').length,1);
    await action(page,'Перезапустить').and(page.locator(':enabled')).waitFor();
    assert.equal(calls.filter(x=>x==='importapply').length,1);
    assert.ok(!calls.includes('restart'));
    console.log('PASS Zemidala: 67 searchable provider cards, source marker and ordinary Apply');
  }
  if(process.env.NFQWS_TEST_SCOPE==='notes'){
    const open=async(p,lang='ru')=>{
      await p.goto(base+'/?lang='+lang);
      await action(p,lang==='ru'?'Стратегии':'Strategies').click();
      await p.getByRole('textbox',{name:/^(Моя заметка|My note) — /}).first().waitFor();
    };
    const note=(p,title,lang='ru')=>p.getByRole('textbox',{name:(lang==='ru'?'Моя заметка':'My note')+' — '+title,exact:true});
    const [first,second]=localPack.entries;
    const marker='Личный тест 729';
    await open(page);
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
    await open(page);
    assert.equal(await note(page,'Переименованный пресет').inputValue(),'Новое личное описание');
    assert.equal(await note(page,second.title).inputValue(),'Своя отдельная заметка');
    assert.equal(await note(page,first.title).inputValue(),'');
    const peer=await page.context().newPage();await open(peer);
    await note(peer,second.title).fill('Из соседней вкладки 729');
    await page.waitForFunction(()=>[...document.querySelectorAll('textarea')].some(el=>el.value==='Из соседней вкладки 729'));
    await note(page,'Переименованный пресет').fill('');await peer.close();
    await open(page);assert.equal(await note(page,'Переименованный пресет').inputValue(),'');
    profiles=[{...profile,id:first.id,title:'Same ID in packaged catalog'},profile];
    await open(page);
    assert.equal(await note(page,'Same ID in packaged catalog').inputValue(),'','Overlapping catalog IDs never share notes');
    await note(page,'Same ID in packaged catalog').fill(marker);
    profiles=[profile,{...profiles[0],title:'Updated cloud title',category:'provider',revision:2,sha256:'b'.repeat(64)}];
    await open(page);
    await search.fill('729');assert.equal(await note(page,'Updated cloud title').inputValue(),marker);
    assert.equal(await page.getByRole('textbox',{name:/Моя заметка —/}).count(),2,'One search finds notes in both sections');
    assert.equal(await note(page,second.title).inputValue(),'Из соседней вкладки 729');
    await page.evaluate(()=>{Storage.prototype.setItem=function(){throw new DOMException('Full','QuotaExceededError')}});
    await note(page,'Updated cloud title').fill('Временный текст');
    await page.getByText(/Браузер не смог прочитать или сохранить заметки/).waitFor();
    assert.equal(await note(page,'Updated cloud title').inputValue(),'Временный текст');
    await open(page);await search.fill('729');assert.equal(await note(page,'Updated cloud title').inputValue(),marker);
    assert.ok(!calls.includes('importcatalogload')&&!calls.includes('importapply')&&!bodies.some(v=>v.includes(marker)));
    localResponse=localPack;
    if(process.env.NFQWS_NOTES_SCREENSHOTS){
      await page.setViewportSize({width:1230,height:930});
      await page.emulateMedia({colorScheme:'dark'});
      for(const lang of ['ru','en']){
        await open(page,lang);
        const list=page.getByRole('list',{name:lang==='ru'?'Стратегии':'Strategies'});
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
    await page.locator('input[type=file]').setInputFiles({
      name:'external.json',mimeType:'application/json',buffer:Buffer.from('{}'),
    });
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
    await button('Стратегии').click();
    await page.getByRole('button',{name:/Original name/}).click();
    await button('К списку стратегий').waitFor();
    assert.equal(await button('Перезапустить').isDisabled(),true,'A new choice cannot start a previously saved preset');
    await button('К списку стратегий').click();
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
  await action(page,'Стратегии').click();
  const local=page.getByRole('list',{name:'Стратегии'});
  await local.getByRole('button',{name:/ALL TCP & UDP YTDisBystro_3_4_v1/}).waitFor();
  assert.equal(await local.getByRole('button',{name:/Original name/}).count(),1);
  assert.equal(magiskPack.entries.filter(entry=>entry.group==='presets').length,98);
  assert.equal(supplemental.entries.filter(entry=>entry.collection==='avatar').length,4);
  assert.equal(await local.getByRole('button').count(),103);
  const layout=await local.evaluate(el=>[el.scrollWidth,el.clientWidth,el.scrollHeight,el.clientHeight]);
  assert.ok(layout[0]<=layout[1]+1 && layout[2]>layout[3],JSON.stringify(layout));
  await page.getByRole('searchbox').fill('avatarDD');
  assert.equal(await local.getByRole('button').count(),4);
  await page.getByRole('searchbox').fill('ytdisbystro_3_4_v1');
  const chosen=local.getByRole('button',{name:/ALL TCP & UDP YTDisBystro_3_4_v1/});
  await chosen.waitFor();
  assert.equal(await local.getByRole('link').count(),0);
  assert.match(await chosen.innerText(),/zapretdiscordyoutube\/magisk-zapret2/);
  assert.equal(await chosen.locator('time').innerText(),'Дата сборника: 01.11.2026');
  assert.doesNotMatch(await chosen.innerText(),/https?:\/\/|#L\d|адаптация (?:для|под)|зависит от провайдера/i);
  const before=calls.length;
  await chosen.click();
  const save=action(page,'Применить');
  const restart=action(page,'Перезапустить');
  const preview=action(page,'Просмотр');
  await save.and(page.locator(':enabled')).waitFor();
  await page.getByRole('heading',{name:'ALL TCP & UDP YTDisBystro_3_4_v1',exact:true}).waitFor();
  assert.equal(await local.count(),0);
  assert.equal(await page.getByRole('button',{name:/Предпросмотр|Раскрыть стратегии/}).count(),0);
  assert.equal(await page.getByRole('checkbox',{name:/Доверяю источнику/}).count(),0);
  assert.equal(await page.getByText(/Проверьте разделы|Панель просмотрела только часть|old strategy rule/).count(),0);
  assert.equal(await restart.isDisabled(),true);
  assert.equal(await page.getByRole('tablist').count(),0);
  assert.deepEqual(await page.locator('.MuiDialogActions-root button').allTextContents(),['Просмотр','Применить','Перезапустить']);
  await preview.click();
  await tab(page,'Изменения').click();
  await page.getByText('new strategy rule',{exact:true}).waitFor();
  await preview.click();
  assert.equal(await page.getByRole('tablist').count(),0);
  assert.deepEqual(calls.slice(before).filter(cmd=>['importlocalentry','importinspect','importprepare','importapply','restart'].includes(cmd)),['importlocalentry','importinspect','importprepare']);
  assert.equal(selections.at(-1).trusted_lua,false);
  await save.click();
  await restart.and(page.locator(':enabled')).waitFor();
  assert.deepEqual(calls.slice(before).filter(cmd=>['importapply','restart'].includes(cmd)),['importapply']);
  await restart.click();
  await page.getByText(/Команда выполнена/).waitFor();
  assert.deepEqual(calls.slice(before).filter(cmd=>['importapply','restart'].includes(cmd)),['importapply','restart']);
  if(!luaFlow){
    await page.goto(base+'/?lang=en');
    await action(page,'Strategies').click();
    await page.getByRole('button',{name:/Original name/}).click();
    const cloudApply=action(page,'Apply'),cloudRestart=action(page,'Restart');
    await cloudApply.and(page.locator(':enabled')).waitFor();
    assert.equal(await cloudRestart.isDisabled(),true);
    assert.equal(await page.getByRole('tablist').count(),0);
    const beforeCloud=calls.length;
    await cloudApply.click();
    await cloudRestart.and(page.locator(':enabled')).waitFor();
    assert.deepEqual(calls.slice(beforeCloud).filter(cmd=>['importapply','restart'].includes(cmd)),['importapply']);
    await cloudRestart.click();
    await page.getByText(/Command completed/).waitFor();
    assert.deepEqual(calls.slice(beforeCloud).filter(cmd=>['importapply','restart'].includes(cmd)),['importapply','restart']);
  }
  console.log('PASS local library: 98 presets, phone-width scrolling, separate apply, restart and optional tabbed details');
}finally{await browser?.close();if(server)await new Promise(resolve=>server.close(resolve));await rm(dir,{recursive:true,force:true});}

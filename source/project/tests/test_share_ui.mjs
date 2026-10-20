import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {mkdtemp,rm,writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';import {join} from 'node:path';import {fileURLToPath,pathToFileURL} from 'node:url';
import {build} from '../webui/web/node_modules/esbuild/lib/main.js';
const root=new URL('../webui/web/src/',import.meta.url);
const header=await readFile(new URL('components/Header.tsx',root),'utf8');
const ark=await readFile(new URL('components/ArkDialog.tsx',root),'utf8');
const dialog=await readFile(new URL('components/ShareDialog.tsx',root),'utf8');
assert.equal((header.match(/<CommunityActions\b/g)||[]).length,1,'one global Share entry required');
assert.doesNotMatch(ark,/DpiDetectorDialog|SaveReportDialog|collectReport|report\.collect|report\.help_title/,'ARK must not retain adjacent share actions');
assert.match(header,/flexWrap="wrap"/);assert.match(dialog,/downloadSupportReport/);assert.match(dialog,/prepareShare/);assert.match(dialog,/sendShare/);
const strategy=(await readFile(new URL('components/ShareStrategySection.tsx',root),'utf8'))+(await readFile(new URL('components/ShareContextSection.tsx',root),'utf8'));
assert.match(strategy,/getStrategyDraft/);assert.match(strategy,/share\.refresh_config/);assert.match(strategy,/required/);assert.match(strategy,/operator/);assert.match(strategy,/share_location/);assert.match(strategy,/https:\/\/db-ip\.com/);
const dpi=await readFile(new URL('components/ShareDpiSection.tsx',root),'utf8');
assert.match(dpi,/\/opt\/bin\/nfqws2-dpi/);assert.doesNotMatch(dpi,/startDpi|DpiSettings|DpiResults/);
for(const lang of ['ru','en']) {
 const tr=JSON.parse(await readFile(new URL(`translations/${lang}.json`,root),'utf8'));
 assert.equal(typeof tr.share.title,'string');assert.equal(typeof tr.share.link_installation,'string');assert.ok(tr.share.link_help.length>30);
 assert.ok(tr.share.operator_required.length>10);assert.ok(tr.share.location_hint.length>30);assert.ok(tr.share.native_hint.includes('S'));
}
console.log('PASS one global entry, no ARK duplicates, original-only DPI and editable/consented context RU/EN');
const dir=await mkdtemp(join(tmpdir(),'share-render-'));
try {
const outfile=join(dir,'render.cjs');
await build({stdin:{resolveDir:fileURLToPath(new URL('../webui/web/',import.meta.url)),contents:`
import {createElement as h} from 'react';import {renderToStaticMarkup} from 'react-dom/server';
import {QueryClientProvider} from '@tanstack/react-query';import {RouterContextProvider,createRouter,createRootRoute,createMemoryHistory} from '@tanstack/react-router';
import {queryClient} from '@/api/client';import {createAPIClient} from '@/api/create-api-client';import {useAppStore} from '@/store/useAppStore';
import {Header} from '@/components/Header';import {ShareStrategySection} from '@/components/ShareStrategySection';import {ShareDpiSection} from '@/components/ShareDpiSection';import {SharePreview} from '@/components/SharePreview';
import {TranslationContext} from '@/context/TranslationContext';import ru from '@/translations/ru.json';import en from '@/translations/en.json';
function local(Component,props,language){const pack=language==='ru'?ru:en;const t=path=>path.split('.').reduce((v,k)=>v[k],pack);return h(TranslationContext.Provider,{value:{t,langcode:language,setLanguage(){}}},h(Component,props));}
export function renderHeader(language,path,anonymous){
 const key=createAPIClient().indexPhp.postIndexCmd.getQueryKey({body:{cmd:'status'}});queryClient.setQueryData(key,{status:0,anonym:anonymous,authenticated:true,nfqws2:true,service:true,version:'1.3.1-asus6+b16',csrf_token:'fixture-csrf'});
 queryClient.setQueryData(['package-update-overview','fixture-csrf'],{check:{state:'current',candidate:null,code:null,installed_version:'1.3.1-asus6+b16'},operation:null});
 const initial=useAppStore.getInitialState();useAppStore.getInitialState=()=>({...initial,auth:true});useAppStore.setState({auth:true});
 const router=createRouter({routeTree:createRootRoute(),history:createMemoryHistory({initialEntries:[path]})});
 return renderToStaticMarkup(h(QueryClientProvider,{client:queryClient},h(RouterContextProvider,{router},local(Header,{},language))));
}
export function renderPart(which,language){
 const none=()=>{};const form={draft:{blocks:[{key:'NFQWS_ARGS',value:'--filter-tcp=443'}],config:'NFQWS_ARGS="--filter-tcp=443"'},selected:[],full:false,context:{purpose:'video',operator:'Example ISP',region:'Berlin',share_location:false,comment:''},locationEdited:false};
 const state={mail:{configured:false,sharing_v3:false,code:'not_configured'},dpi:{available:{available:true,code:'ready'},installed:{installed:true,version:'5'},version:'5',default_tests:[],active:null,history:[]},saved:{reports:[],code:'ready',skipped:0,scan_truncated:false}};
 return renderToStaticMarkup(local(which==='strategy'?ShareStrategySection:which==='dpi'?ShareDpiSection:SharePreview,which==='strategy'?{csrfToken:'csrf',value:form,disabled:false,onChange:none,onLocation:none,onError:none}:which==='dpi'?{csrfToken:'csrf',state,disabled:false,onChange:none,onState:none,onError:none}:{snapshot:{files:[{type:'strategy',filename:'NFQWS2_STRATEGY_2026-10-16_10-00-00Z.json',blob:new Blob(['x']),text:'{"comment":"<script>PRIVATE_HTML_CANARY</script>"}',complete:true}],source:undefined}},language));
}
`},tsconfig:fileURLToPath(new URL('../webui/web/tsconfig.app.json',import.meta.url)),define:{'window.location.origin':'"http://localhost"','process.env.APP_VERSION':'"0.1.4"'},bundle:true,platform:'node',format:'cjs',outfile,logLevel:'silent',plugins:[{name:'server-store-fixture',setup(b){b.onResolve({filter:/useAppStore$/},()=>({path:'store',namespace:'fixture'}));b.onLoad({filter:/.*/,namespace:'fixture'},()=>({contents:`import {create} from 'zustand';export const useAppStore=create(set=>({auth:true,setAuth:auth=>set({auth}),needSave:false,needReload:false,setNeedReload:needReload=>set({needReload}),onSave:async()=>{}}));`,resolveDir:fileURLToPath(new URL('../webui/web/',import.meta.url))}));}}]});
const render=await import(pathToFileURL(outfile));
if(process.env.NFQWS_HEADER_PREVIEW)await writeFile(process.env.NFQWS_HEADER_PREVIEW,'<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Локальный предпросмотр шапки</title><style>body{margin:0;font-family:Arial,sans-serif;background:#f6f7f9;color:#263238}main{padding:24px;font-size:14px}</style></head><body>'+render.renderHeader('ru','/',true)+'<main>Локальный предпросмотр внешнего вида. На роутере пока установлен прежний Build.</main></body></html>');
globalThis.fetch=async()=>{throw Error('render must not request or send anything');};
for(const lang of ['ru','en']){
 for(const path of ['/','/scripts','/lists'])for(const anonymous of [true,false]){const html=render.renderHeader(lang,path,anonymous);const title=lang==='ru'?'Экспорт / поделиться':'Export / share';assert.equal((html.match(new RegExp('aria-label=\"'+title+'\"','g'))||[]).length,1,`one Share in ${lang} ${path}, anonymous=${anonymous}`);assert.ok(html.includes('/community/export-e9a226cd.png'));assert.ok(html.includes('/community/import-937c2946.png'));assert.doesNotMatch(html,/>Поделиться<|>Share</);const importLabel=lang==='ru'?'Импорт стратегий':'Import strategies';assert.match(html,new RegExp('<button[^>]*aria-label=\"'+importLabel+'\"'));assert.doesNotMatch(html,new RegExp('<button[^>]*disabled=\"\"[^>]*aria-label=\"'+importLabel+'\"'));}
 const strategy=render.renderPart('strategy',lang);assert.equal((strategy.match(/ required=""/g)||[]).length,2);assert.doesNotMatch(strategy,/ checked=""/);assert.match(strategy,/https:\/\/db-ip.com/);
 const dpi=render.renderPart('dpi',lang);assert.match(dpi,/\/opt\/bin\/nfqws2-dpi/);assert.doesNotMatch(dpi,/startDpi|DpiSettings/);
 const preview=render.renderPart('preview',lang);assert.ok(preview.includes('&lt;script&gt;PRIVATE_HTML_CANARY&lt;/script&gt;'));assert.ok(!preview.includes('<script>PRIVATE_HTML_CANARY'));
}
console.log('PASS actual rendered Header across routes/auth modes, RU/EN strategy consent/required fields, original command and text-only preview');
} finally {await rm(dir,{recursive:true,force:true});}

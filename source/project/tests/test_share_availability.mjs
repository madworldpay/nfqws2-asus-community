import assert from 'node:assert/strict';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {build} from '../webui/web/node_modules/esbuild/lib/main.js';
const dir=await mkdtemp(join(tmpdir(),'share-availability-'));
try {
 const outfile=join(dir,'render.cjs');
 await build({stdin:{resolveDir:fileURLToPath(new URL('../webui/web/',import.meta.url)),contents:`
import {createElement as h} from 'react'; import {renderToStaticMarkup} from 'react-dom/server';
import * as share from '@/components/ShareDialog';
import {TranslationContext} from '@/context/TranslationContext';
import ru from '@/translations/ru.json'; import en from '@/translations/en.json';
export const hasViews=typeof share.ShareMailNotice==='function' && typeof share.ShareDeliveryButtons==='function';
export function render(language,mail,preview){
 const pack=language==='ru'?ru:en;
 const t=path=>path.split('.').reduce((v,k)=>v[k],pack);
 return renderToStaticMarkup(h(TranslationContext.Provider,{value:{t,langcode:language,setLanguage(){}}},h('div',{},
  h(share.ShareMailNotice,{mail}),
  h(share.ShareDeliveryButtons,{mail,snapshot:preview?{version:4}:undefined,busy:false,disabled:false,retry:false,onSave(){},onSend(){}}))));
}`},tsconfig:fileURLToPath(new URL('../webui/web/tsconfig.app.json',import.meta.url)),define:{'window.location.origin':'"http://localhost"','process.env.APP_VERSION':'"0.1.4"'},bundle:true,platform:'node',format:'cjs',outfile,logLevel:'silent'});
 const view=await import(pathToFileURL(outfile));
 assert.equal(view.hasViews,true,'Share must show the actual unavailable reason before preview and keep JSON saving independent');
 globalThis.window={isSecureContext:false};
 globalThis.fetch=async()=>{throw Error('Availability rendering must not send requests');};
 const cases=[
  [{configured:false,sharing_v3:false,sharing_v4:false,code:'not_configured'},/Канал отправки не настроен/,/Sending channel is not configured/],
  [{configured:true,sharing_v3:true,sharing_v4:false,code:'ready'},/формат v4/,/format v4/],
  [{configured:true,sharing_v3:true,code:'ready'},/формат v4/,/format v4/],
  [{configured:true,sharing_v3:true,sharing_v4:'true',code:'ready'},/формат v4/,/format v4/],
  [{configured:false,sharing_v3:false,sharing_v4:false,code:'https_unavailable'},/HTTPS.*TLS/,/HTTPS.*TLS/],
  [{configured:false,sharing_v3:false,sharing_v4:false,code:'invalid_config'},/Некорректная конфигурация/,/Invalid sending configuration/],
  [{configured:false,sharing_v3:false,sharing_v4:false,code:'PRIVATE_CHANNEL_CANARY'},/недоступна/,/unavailable/],
 ];
 for(const lang of ['ru','en'])for(const [mail,ruReason,enReason] of cases)for(const preview of [false,true]) {
  const html=view.render(lang,mail,preview);
  const visible=html.replace(/<style[^>]*>[\s\S]*?<\/style>/g,'').replace(/<[^>]+>/g,'');
  assert.match(visible,lang==='ru'?ruReason:enReason,'Specific reason is already visible before preview');
  assert.ok(!html.includes('PRIVATE_CHANNEL_CANARY'),'Unknown server codes must not be disclosed');
  const buttons=[...html.matchAll(/<button\b([^>]*)>([\s\S]*?)<\/button>/g)];
  const save=buttons.find(([, ,text])=>text.includes(lang==='ru'?'Скачать JSON':'Download JSON'));
  const send=buttons.find(([, ,text])=>text.includes(lang==='ru'?'Отправить':'Send'));
  assert.ok(save);assert.ok(send);
  assert.equal(save[1].includes('disabled=""'),!preview,'Previewed JSON saves even if sending is unavailable');
  assert.ok(send[1].includes('disabled=""'),'Preview cannot enable an unavailable channel');
 }
 for(const lang of ['ru','en'])for(const preview of [false,true]) {
  const html=view.render(lang,{configured:true,sharing_v3:false,sharing_v4:true,code:'ready'},preview);
  const send=[...html.matchAll(/<button\b([^>]*)>([\s\S]*?)<\/button>/g)].find(([, ,text])=>text.includes(lang==='ru'?'Отправить':'Send'));
  assert.equal(send[1].includes('disabled=""'),!preview,'Ready v4 still requires explicit preview');
 }
 console.log('PASS specific RU/EN channel reasons before/after preview, no private codes, v4 gate and independent JSON saving');
}finally{await rm(dir,{recursive:true,force:true});}

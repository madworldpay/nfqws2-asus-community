import assert from 'node:assert/strict';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {build} from '../webui/web/node_modules/esbuild/lib/main.js';
const dir=await mkdtemp(join(tmpdir(),'share-connect-'));
try {
 const out=join(dir,'test.cjs');
 await build({stdin:{resolveDir:fileURLToPath(new URL('../webui/web/',import.meta.url)),contents:`
import {createElement as h} from 'react';import {renderToStaticMarkup} from 'react-dom/server';
import * as ui from '@/components/ShareDialog';import * as client from '@/api/shareClient';
import {TranslationContext} from '@/context/TranslationContext';import ru from '@/translations/ru.json';import en from '@/translations/en.json';
export const available=typeof ui.ShareConnectButton==='function' && typeof client.connectShareChannel==='function';
export const connect=client.connectShareChannel;
export const render=(lang,mail,busy)=>renderToStaticMarkup(h(TranslationContext.Provider,{value:{t:path=>path.split('.').reduce((v,k)=>v[k],lang==='ru'?ru:en),langcode:lang,setLanguage(){}}},h(ui.ShareConnectButton,{mail,busy,onConnect(){throw Error('render cannot connect');}})));
`},tsconfig:fileURLToPath(new URL('../webui/web/tsconfig.app.json',import.meta.url)),define:{'window.location.origin':'"http://localhost"','process.env.APP_VERSION':'"0.1.4"'},bundle:true,platform:'node',format:'cjs',outfile:out,logLevel:'silent'});
 const view=await import(pathToFileURL(out));assert.equal(view.available,true,'Explicit setup component/client required');
 let requests=[];globalThis.fetch=async(url,options)=>{requests.push({url,options});return new Response(JSON.stringify({connected:true}),{status:200,headers:{'Content-Type':'application/json'}});};
 for(const lang of ['ru','en']) {
  const html=view.render(lang,{configured:false,code:'not_configured',public_setup_available:true},false);assert.match(html,lang==='ru'?/Подключить отправку/:/Connect sending/);assert.ok(!/<input\b/.test(html));assert.equal(requests.length,0);
  assert.match(view.render(lang,{configured:false,code:'not_configured',public_setup_available:true},true),/disabled=""/);
  for(const mail of [{configured:false,code:'not_configured',public_setup_available:false},{configured:false,code:'invalid_config',public_setup_available:true},{configured:true,code:'ready',public_setup_available:true},{configured:false,code:'not_configured',public_setup_available:'true'}])assert.ok(!/<button\b/.test(view.render(lang,mail,false)));
 }
 await view.connect('csrf');assert.equal(requests.length,1);let params=Object.fromEntries(requests[0].options.body);assert.deepEqual(params,{cmd:'sharechannelconnect',csrf_token:'csrf'});assert.ok(!('report' in params)&&!('consent' in params)&&!('url' in params));
 console.log('PASS explicit local setup only, no render requests, no checkbox, disabled/custom/unknown guard, no sending');
}finally{await rm(dir,{recursive:true,force:true});}

import assert from 'node:assert/strict';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {build} from '../webui/web/node_modules/esbuild/lib/main.js';
const dir=await mkdtemp(join(tmpdir(),'nfqws-smartdns-ui-'));
try {
 const out=join(dir,'render.cjs');
 await build({stdin:{resolveDir:fileURLToPath(new URL('../webui/web/',import.meta.url)),contents:`
 import {createElement as h} from 'react';import {renderToStaticMarkup} from 'react-dom/server';
 import {TranslationContext} from './src/context/TranslationContext';import ru from './src/translations/ru.json';
 import {SmartDnsProfileForm} from './src/components/SmartDnsProfileForm';import {SmartDnsPreview} from './src/components/SmartDnsPreview';
 import {emptyProfile,newUpstream} from './src/api/smartDnsProfile';
 export * from './src/api/smartDnsConfigClient';
 const t=(key)=>key.split('.').reduce((v,k)=>v?.[k],ru)||key;
 export const profile=()=>({...emptyProfile(),upstreams:[{...newUpstream('main'),address:'9.9.9.9',tls_name:'dns.quad9.net',default:true,domains:[{name:'image.tmdb.org',include_subdomains:false}]}]});
 export function form(disabled=false){return renderToStaticMarkup(h(TranslationContext.Provider,{value:{t}},h(SmartDnsProfileForm,{value:profile(),onChange(){},disabled,errors:{'upstreams.0.tls_name':'FIELD_ERROR'}})));}
 export function preview(){return renderToStaticMarkup(h(TranslationContext.Provider,{value:{t}},h(SmartDnsPreview,{profile:profile(),preview:{groups:[],overlaps:[],config:'<script>PRIVATE_CANARY()</script>'},onApply(){},disabled:true})));}
 `},bundle:true,platform:'node',format:'cjs',outfile:out,jsx:'automatic',logLevel:'silent',tsconfig:fileURLToPath(new URL('../webui/web/tsconfig.app.json',import.meta.url))});
 const m=await import(out);const form=m.form();
 assert.ok(form.includes('Готовый сервер DoT / DoH'));assert.ok(form.includes('По умолчанию'));assert.ok(form.includes('Сайты для этого DNS'));assert.ok(form.includes('FIELD_ERROR'));assert.ok(form.includes('Фиксированные ответы'));
 assert.ok(!form.includes('__MISSING__'));assert.ok((m.form(true).match(/aria-disabled=\"true\"/g)||[]).length>=2,'both custom selects must be disabled during switching');const preview=m.preview();assert.ok(preview.includes('&lt;script&gt;'));assert.ok(!preview.includes('<script>PRIVATE'));assert.match(preview,/disabled=""/);
 const commands=[];globalThis.fetch=async(_url,options)=>{
  const body=options.body;const cmd=body.get('cmd');commands.push(Object.fromEntries(body));
  let data={schema_version:1,state:'awaiting_confirmation',request_id:'c'.repeat(32),preview_id:null,deadline_remaining_s:119};
  if(cmd==='smartdnsdraft')data={profile_hash:'a'.repeat(64)};
  if(cmd==='smartdnsconfigstatus')data={status:data,draft:m.profile(),active_profile:null};
  return new Response(JSON.stringify(data),{headers:{'Content-Type':'application/json'}});
 };
 const hash=await m.saveSmartDnsDraft('TOKEN',m.profile());assert.equal(hash,'a'.repeat(64));
 await m.validateSmartDnsDraft('TOKEN','b'.repeat(32),hash);await m.getSmartDnsConfigStatus('TOKEN');
 await m.applySmartDnsPreview('TOKEN','c'.repeat(32),{id:'d'.repeat(32),profile_hash:hash,baseline_hash:'e'.repeat(64)});
 await m.confirmSmartDns('TOKEN','c'.repeat(32));await m.rollbackSmartDns('TOKEN','c'.repeat(32));
 assert.deepEqual(commands[3],{cmd:'smartdnsapply',csrf_token:'TOKEN',request_id:'c'.repeat(32),preview_id:'d'.repeat(32),profile_hash:hash,baseline_hash:'e'.repeat(64)});
 assert.deepEqual(commands.map(x=>x.cmd),['smartdnsdraft','smartdnsvalidate','smartdnsconfigstatus','smartdnsapply','smartdnsconfirm','smartdnsrollback']);
 console.log('Real form/preview render, escaped config, field error and HTTP payload contract: PASS');
} finally {await rm(dir,{recursive:true,force:true});}

import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {build} from '../webui/web/node_modules/esbuild/lib/main.js';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';import {join} from 'node:path';import {pathToFileURL,fileURLToPath} from 'node:url';
const dir=await mkdtemp(join(tmpdir(),'share-client-'));
try {
await build({entryPoints:[fileURLToPath(new URL('../webui/web/src/api/shareClient.ts',import.meta.url))],outfile:join(dir,'share.mjs'),bundle:true,alias:{'@':fileURLToPath(new URL('../webui/web/src',import.meta.url))},platform:'node',format:'esm',logLevel:'silent'});
const api=await import(pathToFileURL(join(dir,'share.mjs')));
const raw={report:JSON.stringify({schema_version:1,model:'GT-BE19000AI',captured_at:'2026-10-16T10:00:00Z',complete:false,sections:{},failures:[]}),dpi:JSON.stringify({type:'nfqws2_dpi_saved',schema_version:1,groups:[{group:2}],coverage:{partial:true}}),strategy:JSON.stringify({type:'nfqws2_strategy',schema_version:1,mode:'blocks',blocks:[{key:'NFQWS_ARGS',value:'--filter-tcp=443'}]})};
const names={report:'GT-BE19000AI',dpi:'DPI',strategy:'STRATEGY'};
const files=kinds=>kinds.map(type=>({type,filename:`NFQWS2_${names[type]}_2026-10-16_10-00-00Z.json`,byte_length:Buffer.byteLength(raw[type]),sha256:createHash('sha256').update(raw[type]).digest('hex'),data_base64:Buffer.from(raw[type]).toString('base64')}));
const source={model:'GT-BE19000AI',firmware:{firmver:'3006.102',buildno:'9',extendno:'0'},kernel:'4.19.294',versions:{core:'1.3.1-asus6+b16',web:'0.1.4'}};
const proof='v3.1000.'+'a'.repeat(32)+'.'+'b'.repeat(64);let calls=[];
for(const kinds of [['report'],['dpi'],['strategy'],['report','dpi'],['report','strategy'],['dpi','strategy'],['report','dpi','strategy']]) {
 globalThis.fetch=async(url,options)=>{calls.push({url,options});assert.ok(!('version' in JSON.parse(options.body.get('selection'))),'legacy server rejects a version selector in v3 selection');return Response.json({files:files(kinds),source,proof});};
 const selection={version:3,...Object.fromEntries(kinds.map(k=>[k,{}]))};const v=await api.prepareShare(selection,'csrf');assert.equal(selection.version,3,'serialization must not mutate caller selection');
 assert.deepEqual(v.files.map(f=>f.type),kinds);assert.ok(Object.isFrozen(v));assert.ok(Object.isFrozen(v.source.firmware));
 for(const f of v.files)assert.equal(await f.blob.text(),raw[f.type]);
 assert.equal(calls.at(-1).options.body.get('cmd'),'shareprepare');
}
assert.ok(calls.every(c=>c.options.body.get('cmd')==='shareprepare'),'prepare must not send');
for(const mutate of [v=>{v.files.reverse();},v=>{v.files[0].data_base64+='\n';},v=>{v.files[0].sha256='a'.repeat(64);},v=>{v.source.ip='PRIVATE_CANARY';},v=>{v.extra='PRIVATE_CANARY';}]) {
 const v={files:files(['report','dpi','strategy']),source:structuredClone(source),proof};mutate(v);globalThis.fetch=async()=>Response.json(v);
 await assert.rejects(api.prepareShare({strategy:{}},'csrf'));
}
globalThis.fetch=async()=>Response.json({files:files(['strategy']),source,proof});
const snapshot=await api.prepareShare({strategy:{}},'csrf');const sid='11111111-1111-4111-8111-111111111111';let release;calls=[];
globalThis.fetch=(url,options)=>{calls.push({url,options});return new Promise(resolve=>{release=()=>resolve(Response.json({state:'accepted',submission_id:sid,code:'smtp_accepted'}));});};
const a=api.sendShare(snapshot,'csrf',sid),b=api.sendShare(snapshot,'csrf',sid);await new Promise(r=>setImmediate(r));assert.equal(calls.length,1);
const sent=JSON.parse(calls[0].options.body.get('envelope'));assert.deepEqual(sent.files,snapshot.wire);assert.deepEqual(sent.source,source);assert.equal(calls[0].options.body.get('consent'),'send');release();assert.equal((await a).state,'accepted');await b;await api.sendShare(snapshot,'csrf',sid);assert.equal(calls.length,1);
globalThis.fetch=async()=>Response.json({files:files(['dpi']),source,proof});const uncertain=await api.prepareShare({dpi:{}},'csrf');let attempts=0;
globalThis.fetch=async()=>{attempts++;throw Error('network');};assert.equal((await api.sendShare(uncertain,'csrf',sid)).state,'unknown');await api.sendShare(uncertain,'csrf',sid);assert.equal(attempts,1);
assert.equal(api.autoLocation('edited',true,{available:true,country:'DE',region:'Berlin',city:'Berlin',database_age_days:1}),'edited');
assert.equal(api.autoLocation('',false,{available:true,country:'DE',region:'Berlin',city:'Berlin',database_age_days:1}),'DE, Berlin');
assert.deepEqual(api.strategyContext({purpose:'video',operator:'ISP',comment:'',region:'PRIVATE_REGION',share_location:false}),{purpose:'video',operator:'ISP',comment:'',share_location:false});
let exported;globalThis.window={isSecureContext:true,showSaveFilePicker:async()=>({createWritable:async()=>({write:async blob=>{exported=JSON.parse(await blob.text());},close:async()=>{},abort:async()=>{}})})};
assert.equal(await api.saveShare(snapshot),'native');assert.match(exported.submission_id,/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/);assert.deepEqual(exported.files,snapshot.wire);assert.deepEqual(exported.source,snapshot.source);assert.ok(!('proof' in exported));assert.equal(attempts,1,'saving must not send');
globalThis.fetch=async()=>Response.json({files:files(['strategy']),source:{...source,installation_id:'a'.repeat(32)},proof});
await assert.rejects(api.prepareShare({strategy:{},link_installation:false},'csrf'));
assert.equal((await api.prepareShare({strategy:{},link_installation:true},'csrf')).source.installation_id,'a'.repeat(32));

const extendedRaw={type:'nfqws2_resources',schema_version:1,context:{purpose:'video',operator:'ISP',comment:''},files:[],audit:{scope:'files_only',references:[],unresolved:[],missing_reason:'',complete:true}};
const text4=JSON.stringify(extendedRaw);const wire4={type:'resources',filename:'NFQWS2_RESOURCES_2026-10-19_12-00-00Z.json',byte_length:Buffer.byteLength(text4),sha256:createHash('sha256').update(text4).digest('hex'),data_base64:Buffer.from(text4).toString('base64')};
globalThis.fetch=async(url,options)=>{assert.equal(JSON.parse(options.body.get('selection')).version,4);return Response.json({version:4,files:[wire4],source,proof:proof.replace('v3.','v4.')});};
const snap4=await api.prepareShare({version:4,resources:{files:[],missing_reason:''}},'csrf');assert.equal(snap4.version,4);assert.equal(await snap4.files[0].blob.text(),text4);
for(const kinds of [['report'],['dpi'],['report','dpi']]) {
 globalThis.fetch=async(url,options)=>{assert.equal(JSON.parse(options.body.get('selection')).version,4);return Response.json({version:4,files:files(kinds),source,proof:proof.replace('v3.','v4.')});};
 const prepared=await api.prepareShare({version:4,...Object.fromEntries(kinds.map(k=>[k,{}]))},'csrf');assert.equal(prepared.version,4);assert.deepEqual(prepared.files.map(f=>f.type),kinds);for(const f of prepared.files)assert.equal(await f.blob.text(),raw[f.type]);
}
let sent4;globalThis.fetch=async(url,o)=>{sent4=JSON.parse(o.body.get('envelope'));return Response.json({state:'accepted',submission_id:sid,code:'smtp_accepted'});};await api.sendShare(snap4,'csrf',sid);assert.equal(sent4.version,4);assert.deepEqual(sent4.files,[wire4]);
console.log('PASS seven independent choices, immutable exact preview/source, single explicit send and terminal unknown, separate location consent');
} finally {await rm(dir,{recursive:true,force:true});}

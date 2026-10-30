import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { build } from '../webui/web/node_modules/esbuild/lib/main.js';
const dir=await mkdtemp(join(tmpdir(),'technical-client-'));
try {
 const root=fileURLToPath(new URL('../webui/web/src/',import.meta.url));
 await build({entryPoints:[join(root,'api/technicalChannelClient.ts')],outfile:join(dir,'client.mjs'),bundle:true,alias:{'@':root},platform:'node',format:'esm',logLevel:'silent'});
 const api=await import(pathToFileURL(join(dir,'client.mjs')));
 const state={state:'connecting',session_id:'a'.repeat(32),expires_at:1800000000,code:null};
 const calls=[];
 globalThis.fetch=async(url,opts)=>{calls.push([url,Object.fromEntries(opts.body)]);return Response.json(state);};
 assert.deepEqual(await api.technicalRequest('csrf','technicalstart','  secret-link\n'),state);
 assert.deepEqual(calls, [['/index.php',{cmd:'technicalstart',csrf_token:'csrf',invitation:'secret-link',consent:'temporary_root_access'}]]);
 for(const v of [{...state,tunnel_key:'secret'},{...state,state:'running'}, {...state,expires_at:'1800000000'}, {...state,session_id:'../escape'}]){
  globalThis.fetch=async()=>Response.json(v);await assert.rejects(api.technicalRequest('csrf','technicalstatus'));
 }
 globalThis.fetch=async()=>Response.json({error:'auth_required'},{status:403});
 await assert.rejects(api.technicalRequest('csrf','technicalstatus'),e=>e.code==='auth_required');
 assert.equal(typeof api.TechnicalChannelSession,'function','UI must reconcile a lost start response and ignore stale status replies');
 const deferred=()=>{let resolve;const promise=new Promise(r=>{resolve=r;});return {promise,resolve};};
 const late=deferred();let accepted=false;let pending=0;
 const session=new api.TechnicalChannelSession(async(cmd)=>{
   if(cmd==='technicalstart'){accepted=true;throw Error('response lost');}
   if(cmd==='technicalstop'){accepted=false;return {...state,state:'stopped'};}
   if(++pending===1)return late.promise;
   return accepted?state:{...state,state:'stopped'};
 });
 const stale=session.refresh();
 await session.action('technicalstart','signed-link');
 assert.equal(session.snapshot().state.state,'connecting','accepted start must be rediscovered automatically');
 assert.equal(session.snapshot().unresolved,false);
 late.resolve({...state,state:'idle'});await stale;
 assert.equal(session.snapshot().state.state,'connecting','older status must not hide an active channel');
 await session.action('technicalstop');assert.equal(session.snapshot().state.state,'stopped');
 const unreachable=new api.TechnicalChannelSession(async()=>{throw Error('offline');});
 await unreachable.action('technicalstart','signed-link');
 assert.equal(unreachable.snapshot().unresolved,true,'polling and Disconnect must remain available until status is known');
 console.log('PASS temporary channel exact commands, consent, bounded state, no secrets in status');
} finally {await rm(dir,{recursive:true,force:true});}

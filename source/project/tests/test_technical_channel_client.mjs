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
 console.log('PASS temporary channel exact commands, consent, bounded state, no secrets in status');
} finally {await rm(dir,{recursive:true,force:true});}

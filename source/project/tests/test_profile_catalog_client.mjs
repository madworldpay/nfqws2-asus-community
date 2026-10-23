import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { build } from '../webui/web/node_modules/esbuild/lib/main.js';
const dir = await mkdtemp(join(tmpdir(), 'catalog-client-'));
try {
  const root = fileURLToPath(new URL('../webui/web/src/', import.meta.url));
  await build({entryPoints:[join(root,'api/profileCatalogClient.ts')],outfile:join(dir,'client.mjs'),bundle:true,alias:{'@':root},platform:'node',format:'esm',logLevel:'silent'});
  const api=await import(pathToFileURL(join(dir,'client.mjs')));
  const profile={id:'example',title:'Original name',category:'global',provider:'',region:'',description:'Example',attribution:'Example author',updated_at:'2026-10-23T12:00:00Z',revision:1,min_build:68,size:2,sha256:'a'.repeat(64)};
  const catalog={schema_version:1,revision:1,build:68,profiles:[profile]};const calls=[];
  globalThis.fetch=async(url,opts)=>{calls.push({url,cmd:opts.body.get('cmd'),id:opts.body.get('id'),hash:opts.body.get('sha256')});return Response.json(catalog);};
  assert.deepEqual(await api.loadProfileCatalog('csrf'),catalog);
  assert.deepEqual(calls,[{url:'/index.php',cmd:'importcatalog',id:null,hash:null}]);
  for(const value of [{...catalog,profiles:[{...profile,url:'https://evil.invalid'}]},{...catalog,profiles:[profile,profile]},{...catalog,profiles:[{...profile,category:'unknown'}]},{...catalog,profiles:[{...profile,category:['global']}]}]){
    globalThis.fetch=async()=>Response.json(value);await assert.rejects(api.loadProfileCatalog('csrf'));
  }
  globalThis.fetch=async(url,opts)=>{calls.push({url,cmd:opts.body.get('cmd'),id:opts.body.get('id'),hash:opts.body.get('sha256')});return Response.json({document:'{}'});};
  assert.equal(await api.loadCatalogDocument('csrf','example','a'.repeat(64)),'{}');
  assert.deepEqual(calls.at(-1),{url:'/index.php',cmd:'importcatalogload',id:'example',hash:'a'.repeat(64)});
  const count=calls.length;await assert.rejects(api.loadCatalogDocument('csrf','../escape','a'.repeat(64)));assert.equal(calls.length,count);
  globalThis.fetch=async()=>Response.json({document:'x'.repeat(4194305)});await assert.rejects(api.loadCatalogDocument('csrf','example','a'.repeat(64)));
  globalThis.fetch=async()=>Response.json({error:'catalog_unavailable'},{status:503});await assert.rejects(api.loadProfileCatalog('csrf'),e=>e.code==='catalog_unavailable');
  console.log('PASS catalog groups, original names, bounded response, exact router commands, no arbitrary URL or automatic apply');
} finally { await rm(dir,{recursive:true,force:true}); }

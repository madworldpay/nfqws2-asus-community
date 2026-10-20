import assert from 'node:assert/strict';import {mkdtemp,rm} from 'node:fs/promises';import {tmpdir} from 'node:os';import {join} from 'node:path';import {fileURLToPath,pathToFileURL} from 'node:url';import {build} from '../webui/web/node_modules/esbuild/lib/main.js';
const dir=await mkdtemp(join(tmpdir(),'import-client-'));try{
const root=fileURLToPath(new URL('../webui/web/src/',import.meta.url));await build({entryPoints:[join(root,'api/importClient.ts')],outfile:join(dir,'client.mjs'),bundle:true,alias:{'@':root},platform:'node',format:'esm',logLevel:'silent'});const a=await import(pathToFileURL(join(dir,'client.mjs')));
assert.deepEqual(a.emptyImportSelection(),{blocks:[],shared:[],ports:[],files:[],dns:[],allow_shared_impact:false,allow_incomplete:false,trusted_lua:false});
const files=[new File(['{"type":"x"}'],'test.json')];assert.deepEqual(await a.readImportFiles(files),['{"type":"x"}']);await assert.rejects(a.readImportFiles([]));await assert.rejects(a.readImportFiles(Array(6).fill(files[0])));await assert.rejects(a.readImportFiles([new File([new Uint8Array(4194305)],'large.json')]));await assert.rejects(a.readImportFiles([new File([new Uint8Array([255])],'bad.json')]));
// Windows file pickers may provide an empty MIME type; UTF-8 BOM/CRLF are valid text input.
const windowsText='{\r\n  "type": "x"\r\n}';
const windowsBytes=new Uint8Array([0xef,0xbb,0xbf,...new TextEncoder().encode(windowsText)]);
const windowsFile=new File([windowsBytes],'Профиль Windows.json',{type:''});
const windowsRead=await a.readImportFiles([windowsFile]);
assert.equal(windowsRead[0],windowsText);assert.deepEqual(JSON.parse(windowsRead[0]),{type:'x'});
const doc={values:{NFQWS_ARGS:'--filter-tcp=443'},ports:[],resources:[],dependencies:[],audit:null,dns_sources:[],context:null,source:null,ignored:[],input_sha256:'a'.repeat(64)};let calls=[];
globalThis.fetch=async(_url,o)=>{calls.push(o.body.get('cmd'));return Response.json(doc);};assert.equal((await a.inspectImport('csrf',['{}'])).values.NFQWS_ARGS,'--filter-tcp=443');assert.deepEqual(calls,['importinspect']);
globalThis.fetch=async()=>Response.json({...doc,values:{ASUS_CLIENTS4:'192.0.2.1'}});await assert.rejects(a.inspectImport('csrf',['{}']));
globalThis.fetch=async()=>Response.json({...doc,resources:[{id:'b'.repeat(32),kind:'blobs',name:'x.bin',encoding:'base64',data_base64:'eA==',byte_length:1,sha256:'a'.repeat(64),aliases:[]}]});await assert.rejects(a.inspectImport('csrf',['{}']));
const oldCrypto=globalThis.crypto;Object.defineProperty(globalThis,'crypto',{configurable:true,value:{getRandomValues:v=>v.fill(7)}});assert.match(a.newImportRequestId(),/^[a-f0-9]{32}$/);Object.defineProperty(globalThis,'crypto',{configurable:true,value:oldCrypto});
assert.equal(a.importOutcomeUnknown(new a.ImportError('source_changed')),false);assert.equal(a.importOutcomeUnknown(new TypeError('Failed to fetch')),true);
const s=a.emptyImportSelection();const next=a.selectImportDependencies(s,{...doc,values:{...doc.values,NFQWS_BASE_ARGS:'--x'},resources:[{id:'b'.repeat(32)}]},{files:['b'.repeat(32)],shared:['NFQWS_BASE_ARGS']});assert.equal(s.files.length,0);assert.deepEqual(next.files,[{id:'b'.repeat(32)}]);assert.equal(next.shared[0].value,'--x');assert.equal(next.trusted_lua,false);
globalThis.fetch=async()=>Response.json({state:'made_up',id:null,can_undo:false});await assert.rejects(a.importStatus('csrf'));console.log('PASS import file limits/UTF8, unchecked defaults, closed inspected keys/hash and explicit dependencies/status grammar');
}finally{await rm(dir,{recursive:true,force:true});}

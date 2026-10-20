import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {mkdtemp,rm,writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';import {join} from 'node:path';import {fileURLToPath,pathToFileURL} from 'node:url';import {execFileSync} from 'node:child_process';
import {build} from '../webui/web/node_modules/esbuild/lib/main.js';
const dir=await mkdtemp(join(tmpdir(),'share-resource-client-'));
try{
const root=fileURLToPath(new URL('../webui/web/src/',import.meta.url));
await build({entryPoints:[join(root,'api/shareResourcesClient.ts')],outfile:join(dir,'client.mjs'),bundle:true,alias:{'@':root},platform:'node',format:'esm',logLevel:'silent'});
const a=await import(pathToFileURL(join(dir,'client.mjs')));
const data=Buffer.from([0,255,128,72,69,76,76,79]);const hash=createHash('sha256').update(data).digest('hex');
const meta={id:'a'.repeat(32),kind:'blobs',name:'hello.bin',byte_length:data.length,sha256:hash,state:'available'};
let commands=[];globalThis.fetch=async(url,o)=>{const cmd=o.body.get('cmd');commands.push(cmd);return Response.json(cmd==='shareinventory'?{files:[meta],skipped:0,scan_truncated:false}:{...meta,encoding:'base64',data_base64:data.toString('base64')});};
assert.equal((await a.getShareInventory('csrf')).files[0].name,'hello.bin');const copy=await a.readShareResource('csrf',meta);assert.equal(copy.data_base64,data.toString('base64'));
globalThis.fetch=async()=>Response.json({...meta,encoding:'base64',data_base64:Buffer.from('WRONG').toString('base64')});await assert.rejects(a.readShareResource('csrf',meta));
assert.ok(commands.every(c=>['shareinventory','shareresourceread'].includes(c)));
const zip=a.resourceZip([copy]);await writeFile(join(dir,'files.zip'),new Uint8Array(await zip.arrayBuffer()));
const result=execFileSync('python3',['-c','import sys,zipfile,hashlib; z=zipfile.ZipFile(sys.argv[1]); assert z.namelist()==["blobs/hello.bin"]; print(hashlib.sha256(z.read("blobs/hello.bin")).hexdigest()); assert z.testzip() is None',join(dir,'files.zip')],{encoding:'utf8'}).trim();assert.equal(result,hash);
assert.throws(()=>a.resourceZip([{...copy,name:'../escape'}]));
const large=Buffer.alloc(200000,1);const digest=createHash('sha256').update(large).digest('hex');
const archive=a.resourceZip([0,1,2].map(n=>({...copy,id:String(n).repeat(32),name:'part'+n+'.bin',byte_length:large.length,sha256:digest,data_base64:large.toString('base64')})));assert.ok(archive.size>600000,'local archive has an independent 8MiB cap');
console.log('Resource client: explicit metadata/read, hash checks and ZIP exact binary/CRC/path: PASS');
}finally{await rm(dir,{recursive:true,force:true});}

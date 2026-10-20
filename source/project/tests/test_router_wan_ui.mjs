import assert from 'node:assert/strict';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {build} from '../webui/web/node_modules/esbuild/lib/main.js';
const dir=await mkdtemp(join(tmpdir(),'router-wan-'));
try {
 const out=join(dir,'api.cjs');
 await build({entryPoints:[fileURLToPath(new URL('../webui/web/src/api/routerWan.ts',import.meta.url))],bundle:true,platform:'node',format:'cjs',outfile:out,logLevel:'silent',tsconfig:fileURLToPath(new URL('../webui/web/tsconfig.app.json',import.meta.url))});
 const {addWanClient,getRouterWan}=await import(out);
 assert.equal(addWanClient('192.168.1.20/32','192.168.2.2'),'192.168.1.20/32 192.168.2.2/32');
 for(const value of ['192.168.2.2','192.168.2.2/32','192.168.2.0/24','0.0.0.0/0'])assert.equal(addWanClient(value,'192.168.2.2'),value);
 assert.equal(addWanClient('invalid /33','192.168.2.2'),'invalid /33 192.168.2.2/32');
 assert.equal(addWanClient('192.168.2.0/33','192.168.2.2'),'192.168.2.0/33 192.168.2.2/32');
 assert.equal(addWanClient('already','999.1.2.3'),'already');
 let post;
 globalThis.fetch=async(_url,options)=>{post=Object.fromEntries(options.body);return new Response(JSON.stringify({schema_version:1,state:'available',addresses:[{interface:'ppp0',address:'192.168.2.2'}]}),{headers:{'Content-Type':'application/json'}});};
 assert.equal((await getRouterWan('TOKEN')).addresses[0].address,'192.168.2.2');
 assert.deepEqual(post,{cmd:'wanaddresses',csrf_token:'TOKEN'});
 globalThis.fetch=async()=>new Response(JSON.stringify({schema_version:1,state:'available',addresses:[{interface:'BAD<script>',address:'999.1.2.3'}]}),{headers:{'Content-Type':'application/json'}});
 await assert.rejects(()=>getRouterWan('TOKEN'));
 console.log('WAN client CIDR deduplication, explicit read-only HTTP request and response validation: PASS');
} finally {await rm(dir,{recursive:true,force:true});}

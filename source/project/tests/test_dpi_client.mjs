import assert from 'node:assert/strict';
import {getDpiStatus,installDpi,startDpi,stopDpi,downloadDpiResult,downloadDpiOriginal,deleteDpiResult} from '../webui/web/src/api/dpiClient.ts';
let calls=[];
globalThis.fetch=async(url,options)=>{calls.push({url,options});return Response.json({active:null,history:[],available:{available:true,code:'ready'},installed:{installed:false,version:null},version:'v5.0.0-alpha.21',default_tests:[1,2]});};
await getDpiStatus('token');assert.deepEqual([...calls[0].options.body.keys()],['cmd','csrf_token']);assert.equal(calls[0].options.body.get('cmd'),'dpistatus');
assert.equal(calls.filter(c=>c.options.body.get('cmd')==='dpistart').length,0);
globalThis.fetch=async(url,options)=>{calls.push({url,options});return Response.json({id:'a'.repeat(32),kind:'run',state:'queued',started_at:1,finished_at:null,code:null,tests:[1,2],completed_tests:[],current_group:null});};
await installDpi('token','11111111-1111-4111-8111-111111111111');assert.equal(calls.at(-1).options.body.get('consent'),'install');
await startDpi('token','11111111-1111-4111-8111-111111111111',[1,2],[]);assert.equal(calls.at(-1).options.body.get('tests'),'12');
const before=calls.length;await assert.rejects(startDpi('token','x',[1,1],[]));assert.equal(calls.length,before);
globalThis.fetch=async(url,options)=>{calls.push({url,options});return Response.json({id:'a'.repeat(32),state:'stopping'});};
assert.equal((await stopDpi('token','a'.repeat(32))).state,'stopping');
const text=JSON.stringify({type:'nfqws2_dpi',schema_version:1,origin:'router',started_at:'2026-10-15T12:00:00Z',state:'partial',groups:[{group:1}],selected_tests:[1,2]});
globalThis.fetch=async()=>new Response(text,{headers:{'Content-Type':'application/json','Content-Disposition':'attachment; filename="NFQWS2_DPI_2026-10-15_12-00-00Z.json"'}});
const file=await downloadDpiResult('token','a'.repeat(32));assert.equal(await file.blob.text(),text);assert.equal(file.complete,false);
globalThis.fetch=async()=>new Response('x'.repeat(262145),{headers:{'Content-Type':'application/json'}});await assert.rejects(downloadDpiResult('token','a'.repeat(32)));
globalThis.fetch=async()=>Response.json({deleted:true});assert.equal((await deleteDpiResult('token','a'.repeat(32))).deleted,true);
console.log('PASS explicit install/run/stop, bounded exact JSON and no implicit run');

const v2=text.replace('\"schema_version\":1','\"schema_version\":2');
globalThis.fetch=async()=>new Response(v2,{headers:{'Content-Type':'application/json','Content-Disposition':'attachment; filename=\"NFQWS2_DPI_2026-10-15_12-00-00Z.json\"'}});
assert.equal((await downloadDpiResult('token','a'.repeat(32))).kind,'analysis');

for (const native of [true,false]) {
 const raw=native?text.replace('nfqws2_dpi','nfqws2_dpi_native'):text;
 const filename=native?'NFQWS2_DPI_NATIVE_2026-10-15_12-00-00Z.json':'NFQWS2_DPI_2026-10-15_12-00-00Z.json';
 globalThis.fetch=async(url,options)=>{calls.push({url,options});return new Response(raw,{headers:{'Content-Type':'application/json','Content-Disposition':`attachment; filename="${filename}"`}});};
 const result=await downloadDpiOriginal('token','a'.repeat(32),native);
 assert.equal(calls.at(-1).options.body.get('cmd'),native?'dpinative':'dpiresult');
 assert.equal(await result.blob.text(),raw);assert.equal(result.filename,filename);
}
console.log('PASS legacy original export prefers preserved native bytes, analysis remains fallback');

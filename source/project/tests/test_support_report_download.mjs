import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
assert.ok(existsSync(new URL('../webui/web/src/api/supportReport.ts',import.meta.url)),'report download helper missing');
const { downloadSupportReport, saveSupportReport } = await import('../webui/web/src/api/supportReport.ts');
const filename='NFQWS2_GT-BE19000AI_2026-10-15_12-00-00Z.json';
const report={schema_version:1,collector_version:'1.0.0',model:'GT-BE19000AI',captured_at:'2026-10-15T12:00:00Z',complete:false,sections:{},failures:[]};
const response=(body=report,headers={})=>new Response(JSON.stringify(body),{headers:{'Content-Type':'application/json; charset=utf-8','Content-Disposition':`attachment; filename="${filename}"`,...headers}});
let requests=0;
globalThis.fetch=async(url,options)=>{
  requests++;
  assert.equal(url,'/index.php');assert.equal(options.method,'POST');assert.equal(options.credentials,'same-origin');
  assert.deepEqual(Object.fromEntries(options.body),{cmd:'supportreport',csrf_token:'token'});
  assert.ok(options.signal);return response();
};
const file=await downloadSupportReport('token');
assert.equal(requests,1);assert.equal(file.filename,filename);assert.equal(file.complete,false);assert.deepEqual(JSON.parse(await file.blob.text()),report);
let revoked=false,clicked=false,removed=false;
const originalCreate=URL.createObjectURL, originalRevoke=URL.revokeObjectURL;
URL.createObjectURL=()=> 'blob:test'; URL.revokeObjectURL=()=>{revoked=true;};
globalThis.window={isSecureContext:false};
globalThis.document={createElement:()=>({click(){clicked=true;},remove(){removed=true;}}),body:{append(){}}};
assert.equal(await saveSupportReport(file),'browser');await new Promise(r=>setTimeout(r,1100));
assert.ok(clicked&&removed&&revoked,'download URL cleaned up');
let saved=false,closed=false,pickerCalls=0;
globalThis.window={isSecureContext:true,showSaveFilePicker:async(opts)=>{pickerCalls++;assert.equal(opts.suggestedName,filename);return {createWritable:async()=>({write:async(blob)=>{saved=blob===file.blob;},close:async()=>{closed=true;},abort:async()=>{}})};}};
assert.equal(await saveSupportReport(file),'native');assert.ok(saved&&closed&&pickerCalls===1);
window.showSaveFilePicker=async()=>{throw new DOMException('cancelled','AbortError');};
await assert.rejects(()=>saveSupportReport(file),{name:'AbortError'});
URL.createObjectURL=originalCreate;URL.revokeObjectURL=originalRevoke;
for(const bad of [()=>new Response('bad',{status:503}),()=>response(report,{'Content-Type':'text/html'}),()=>response({...report,schema_version:2}),()=>response(report,{'Content-Disposition':'attachment; filename="../../secret.json"'}),()=>response(report,{'Content-Length':'1048577'})]){
  globalThis.fetch=async()=>bad();await assert.rejects(()=>downloadSupportReport('token'));
}
globalThis.fetch=async()=>new Response('x'.repeat(1048577),{headers:{'Content-Type':'application/json','Content-Disposition':`attachment; filename="${filename}"`}});
await assert.rejects(()=>downloadSupportReport('token'));
let unauthenticated=false;globalThis.fetch=async()=>new Response('',{status:401});
await assert.rejects(()=>downloadSupportReport('token',()=>{unauthenticated=true;}));assert.ok(unauthenticated);
console.log('PASS: report fetch/schema/limits/native-save/cancel/fallback/URL cleanup');

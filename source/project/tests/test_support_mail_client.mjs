import assert from 'node:assert/strict';
import {
  inspectSupportReport, getSupportMailAvailability, sendSupportReport,
  newSupportSubmissionId,
} from '../webui/web/src/api/supportReport.ts';

const filename='NFQWS2_GT-BE19000AI_2026-10-15_12-30-45Z.json';
const text=JSON.stringify({schema_version:1,model:'GT-BE19000AI',captured_at:'2026-10-15T12:30:45Z',
  complete:false,sections:{platform:{state:'partial',data:{canary:'<img src=x onerror="alert(1)">'}}},failures:[]},null,2)+'\n';
const file={blob:new Blob([text],{type:'application/json'}),filename,complete:false,
  proof:'v1.1792067445.'+'a'.repeat(32)+'.'+'b'.repeat(64)};
const sid='769385d2-5d25-4ccf-8974-2da99d3d5496';
let calls=[];
globalThis.fetch=async (url,options)=>{
  calls.push({url,options});
  return Response.json({configured:true,code:'ready'});
};
const preview=await inspectSupportReport(file);
assert.equal(preview.text,text);
assert.equal(preview.bytes,Buffer.byteLength(text));
assert.deepEqual(preview.sections,[{name:'platform',state:'partial'}]);
assert.equal(calls.length,0,'preview must not upload');
assert.equal((await getSupportMailAvailability('csrf')).configured,true);
assert.deepEqual([...calls[0].options.body.keys()],['cmd','csrf_token']);
assert.equal(calls[0].options.body.get('cmd'),'supportmailstatus');

calls=[];
let release;
globalThis.fetch=(url,options)=>{
  calls.push({url,options});
  return new Promise(resolve=>{release=()=>resolve(Response.json({state:'accepted',submission_id:sid,code:'smtp_accepted'}));});
};
const first=sendSupportReport(file,'csrf',sid);
const second=sendSupportReport(file,'csrf',sid);
await new Promise(resolve=>setImmediate(resolve));
assert.equal(calls.length,1,'double click must share one request');
assert.equal(calls[0].url,'/index.php');
const form=calls[0].options.body;
assert.equal(form.get('report'),text);
assert.equal(form.get('report_proof'),file.proof);
assert.equal(form.get('consent'),'send');
assert.equal(form.get('submission_id'),sid);
assert.equal(form.get('filename'),filename);
release();
assert.equal((await first).state,'accepted');
assert.equal((await second).submissionId,sid);
await sendSupportReport(file,'csrf',newSupportSubmissionId());
assert.equal(calls.length,1,'accepted file must not resend');

for (const [http,state,code] of [[429,'limited','rate_limited'],[503,'failed_safe','transport_failed'],[503,'unknown','delivery_unknown']]){
  const item={...file,blob:new Blob([text])}; calls=[];
  globalThis.fetch=async(url,options)=>{calls.push(options);return Response.json({state,submission_id:sid,code},{status:http});};
  assert.equal((await sendSupportReport(item,'csrf',sid)).state,state);
  assert.equal(calls.length,1,'no automatic retry');
  if(state==='unknown'){
    await sendSupportReport(item,'csrf',newSupportSubmissionId());
    assert.equal(calls.length,1,'uncertain delivery cannot auto-resend');
  }
}
let unauthorized=0;
globalThis.fetch=async()=>new Response('',{status:401});
await assert.rejects(sendSupportReport({...file,blob:new Blob([text])},'csrf',sid,()=>unauthorized++),e=>e.code==='unauthorized');
assert.equal(unauthorized,1);
calls=[];
globalThis.fetch=async(url,options)=>{calls.push(options);throw new TypeError('PRIVATE_CANARY');};
assert.equal((await sendSupportReport({...file,blob:new Blob([text])},'csrf',sid)).state,'unknown');
assert.equal(calls.length,1);
await assert.rejects(inspectSupportReport({...file,blob:new Blob([new Uint8Array([255])])}));
assert.match(newSupportSubmissionId(),/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/);
console.log('PASS local preview, exact bytes, consent, single request and safe outcomes');

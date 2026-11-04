import assert from 'node:assert/strict';

const api = await import('../webui/web/src/api/packageUpdates.ts');
const base = {
  id: 'a'.repeat(32), revision: 'b'.repeat(64), state: 'applying',
  phase: 'installing', package_version: '1.3.2-asus6+b87', code: null,
  service_intent: null,
};
const check = {state:'current', code:null, candidate:null, installed_version:'1.3.2-asus6+b86'};
const parse = async operation => {
  globalThis.fetch = async () => Response.json({check, operation});
  return (await api.getPackageUpdateOverview('csrf')).operation;
};
// These new worker phases must survive the real strict status parser.
for (const phase of ['downloading', 'checking_package', 'backing_up']) {
  assert.equal((await parse({...base, phase})).phase, phase);
}
const failed = {...base, state:'failed', phase:'finished', failure_phase:'installing', failure_code:'install_failed', code:'update_rolled_back'};
assert.deepEqual(await parse(failed), failed);
assert.deepEqual(await parse(base), base, 'old operations with no failure details remain valid');
for (const extra of [
  {phase:'x'.repeat(10000)}, {phase:{}}, {failure_phase:'unknown'},
  {failure_phase:42}, {failure_code:null},
  {failure_code:''}, {failure_code:'a'.repeat(65)}, {failure_code:'error: secret'},
  {failure_reason:'PRIVATE_CANARY'},
]) {
  await assert.rejects(parse({...base,...extra}), error => error.code === 'invalid_response');
}
console.log('PASS strict operation parser accepts bounded phases and primary failure codes only');

const {packageUpdateProgress, packageUpdateErrorText} = await import('../webui/web/src/utils/packageUpdateProgress.ts');
const progress = (state, phase, extra={}) => packageUpdateProgress({...base,state,phase,...extra});
// A real operation moves monotonically through preparation and installation.
const stages = [
  ['preparing','queued',0,'queued'],
  ['preparing','downloading',0,'downloading'],
  ['preparing','checking_package',14,'checking_package'],
  ['prepared','checking_package',28,'prepared'],
  ['applying','queued',28,'queued'],
  ['applying','validating',28,'validating'],
  ['applying','stopping',42,'stopping'],
  ['applying','backing_up',57,'backing_up'],
  ['applying','installing',71,'installing'],
  ['applying','verifying',85,'verifying'],
  ['succeeded','finished',100,'finished'],
];
let previous = 0;
for (const [state,phase,percent,stage] of stages) {
  const result=progress(state,phase);
  assert.equal(result.percent,percent);assert.equal(result.stage,stage);
  assert.ok(result.percent>=previous);previous=result.percent;
}
assert.equal(packageUpdateProgress(null),null);
assert.deepEqual(progress('failed','finished',{failure_phase:'installing'}),{stage:'installing',percent:71,failed:true});
assert.deepEqual(progress('interrupted','verifying'),{stage:'verifying',percent:85,failed:true});
for(const state of ['failed','interrupted']) {
  assert.deepEqual(progress(state,'finished'),{stage:'unknown',percent:null,failed:true},'legacy terminal phase never implies 100%');
  assert.deepEqual(progress(state,undefined),{stage:'unknown',percent:null,failed:true});
}
assert.deepEqual(progress('preparing',undefined),{stage:'downloading',percent:0,failed:false});
assert.deepEqual(progress('applying',undefined),{stage:'unknown',percent:null,failed:false});
console.log('PASS stage progress is monotonic and never reports a failed operation as complete');

const text = packageUpdateErrorText({
  installed:'1.3.2-asus6+b86', target:'1.3.2-asus6+b87', operation:{...failed,router:'PRIVATE_CANARY',config:'PRIVATE_CANARY'},
  stage:'Installing package', state:'Installation did not complete.',
  errorCode:'request_failed', errorMessage:'Status checks will resume.',
});
for(const required of ['1.3.2-asus6+b86','1.3.2-asus6+b87','Installation did not complete.','Installing package','install_failed','update_rolled_back','request_failed','Status checks will resume.','a'.repeat(32)])assert.ok(text.includes(required),required);
assert.ok(!text.includes('PRIVATE_CANARY'),'copy diagnostics selects only update fields');
const local=packageUpdateErrorText({installed:undefined,target:undefined,operation:null,stage:'Unknown',state:'Not confirmed',errorCode:'auth_required',errorMessage:'Sign in again.'});
assert.match(local,/auth_required/);assert.doesNotMatch(local,/failed|undefined|null/);
console.log('PASS copied error contains versions, stage and original/current codes without router data');

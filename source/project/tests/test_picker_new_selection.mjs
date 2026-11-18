import test from 'node:test';
import assert from 'node:assert/strict';
import {planSelection,roundChoice,poolChoice,recordedPool} from '../webui/web/public/strategy-picker/concurrency.js';
const input={search:'synthesis',extended:false,goal:'all',custom:null,requested:'100000'};
// A missing new-input default would emit a one-round job instead of the owner-required minimum.
test('new generation selection requests two rounds when count is omitted',()=>{
  assert.deepEqual(planSelection(input),{search:'synthesis',extended:false,goal:'all',concurrency:'100000',rounds:2});
});
// Reaccepting a single round at the new selection boundary would silently defeat the minimum.
test('new generation selection refuses a single round',()=>{
  assert.equal(planSelection({...input,rounds:'1'}),null);
});
test('new generation selection preserves explicit two through ten and rejects malformed counts',()=>{
  for(const value of ['2','3','10'])assert.equal(planSelection({...input,rounds:value}).rounds,Number(value));
  for(const value of ['0','01','2.0','11','',2,null])assert.equal(planSelection({...input,rounds:value}),null);
});
// Recovery decodes already existing one-round records; the new-start rule must not falsify old journals.
test('legacy round decoding and ordinary profile comparison keep their original identity',()=>{
  assert.equal(roundChoice('1'),1);
  assert.deepEqual(planSelection({...input,search:'profiles'}),{search:'profiles',extended:false,goal:'all',concurrency:'100000'});
});

test('a selected million-request pool reaches the new-job selection unchanged',()=>{
 assert.deepEqual(planSelection({...input,rounds:'2',requested:'1000000'}),{search:'synthesis',extended:false,goal:'all',concurrency:'1000000',rounds:2});
});
test('intermediate quarter-million selection is not rejected or silently reduced',()=>{
 assert.equal(planSelection({...input,rounds:'2',requested:'250000'})?.concurrency,'250000');
});
test('recorded million-request result displays its exact accepted pool',()=>{
 assert.deepEqual(recordedPool({concurrency_choice:{policy_version:'picker-concurrency-v1',requested:'1000000',effective:1000000},budget:{concurrency:1000000}}),{policy_version:'picker-concurrency-v1',requested:'1000000',effective:1000000});
});
test('pool upper bound and malformed values stay refused while historical smaller records remain readable',()=>{
 for(const x of ['1000001','010000','1e6','1000000.0','',1000000])assert.equal(poolChoice(x),null);
 assert.equal(poolChoice('10000'),'10000');assert.equal(poolChoice('100000'),'100000');
 assert.deepEqual(recordedPool({concurrency_choice:{policy_version:'picker-concurrency-v1',requested:'1000',effective:1000},budget:{concurrency:1000}}),{policy_version:'picker-concurrency-v1',requested:'1000',effective:1000});
});
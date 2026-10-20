import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { build } from '../webui/web/node_modules/esbuild/lib/main.js';

const dir = await mkdtemp(join(tmpdir(), 'nfqws-start-'));
try {
  const output = join(dir, 'progress.mjs');
  await build({entryPoints: ['webui/web/src/api/startProgress.ts'], bundle: true,
    platform: 'node', format: 'esm', outfile: output, logLevel: 'silent'});
  const { startProgress } = await import(output);
  const states = (input) => Object.fromEntries(startProgress(input).map(x => [x.id, x.state]));
  const checkup = {items: [
    {id:'platform',facts:{package_version:'1.3.1-asus6+b51',entware_abi:'aarch64-3.10'}},
    {id:'ark',facts:{loaded:false}}, {id:'process',facts:{running:true}},
    {id:'nfqueue',facts:{bound:true}}, {id:'dns_runtime',facts:{managed_runtime:true}},
  ]};
  assert.deepEqual(states({}), {install:'unknown',ark:'unknown',configure:'unknown',dns:'unknown',start:'unknown',verify:'todo'});
  const ready = {checkup,hasStrategy:true,dirty:false,pendingRestart:false,
    dns:{status:{state:'confirmed',active_profile_hash:'a'.repeat(64)},draft:{upstreams:[{}],records:[]}}};
  assert.deepEqual(states(ready), {install:'done',ark:'done',configure:'done',dns:'done',start:'done',verify:'todo'});
  assert.equal(states({...ready,pendingRestart:true}).configure,'partial');
  assert.equal(states({...ready,dirty:true}).configure,'partial');
  assert.equal(states({...ready,hasStrategy:false}).configure,'todo');
  assert.equal(states({...ready,dns:{status:{state:'preview_ready'},draft:{upstreams:[{}],records:[]}}}).dns,'partial');
  assert.equal(states({...ready,dns:{status:{state:'failed'},draft:{upstreams:[{}],records:[]}}}).dns,'partial');
  assert.equal(states({...ready,dns:{status:{state:'idle'},draft:null}}).dns,'optional');
  const changed = (id, facts) => ({items:checkup.items.map(x=>x.id===id?{...x,facts}:x)});
  assert.equal(states({...ready,checkup:changed('ark',{loaded:true})}).ark,'todo');
  assert.equal(states({...ready,checkup:changed('nfqueue',{bound:false})}).start,'partial');
  assert.equal(states({...ready,checkup:changed('process',{running:false})}).start,'todo');
  assert.equal(states({...ready,checkup:changed('dns_runtime',{managed_runtime:false})}).dns,'partial');
  console.log('Start progress: real readiness, incomplete settings/DNS and manual service checks: PASS');
} finally { await rm(dir, {recursive:true,force:true}); }

import assert from 'node:assert/strict';
import { runInNewContext } from 'node:vm';
import { fileURLToPath } from 'node:url';
import { build } from '../webui/web/node_modules/esbuild/lib/main.js';
const result = await build({entryPoints:[fileURLToPath(new URL('../webui/web/src/store/useAppearanceStore.ts',import.meta.url))],bundle:true,platform:'node',format:'cjs',write:false,logLevel:'silent'});
function store(saved, denied=false) {
  const values = new Map(saved===null?[]:[['nfqws2-appearance',saved]]);
  const module = {exports:{}};
  runInNewContext(result.outputFiles[0].text,{module,exports:module.exports,process:{env:{NODE_ENV:'production'}},localStorage:{getItem:key=>{if(denied)throw new Error('denied');return values.get(key)??null;},setItem:(key,value)=>{if(denied)throw new Error('denied');values.set(key,value);}},console,setTimeout,clearTimeout});
  return {hook:module.exports.useAppearanceStore,values};
}
assert.equal(store(null).hook.getState().appearance,'rabbit','First visit uses Rabbit Hole');
assert.equal(store('classic').hook.getState().appearance,'classic','Existing classic choice is preserved');
assert.equal(store('rabbit').hook.getState().appearance,'rabbit');
assert.equal(store('unknown').hook.getState().appearance,'rabbit');
const normal=store(null);normal.hook.getState().setAppearance('classic');assert.equal(normal.values.get('nfqws2-appearance'),'classic');assert.equal(normal.hook.getState().appearance,'classic');
const denied=store(null,true);assert.equal(denied.hook.getState().appearance,'rabbit');denied.hook.getState().setAppearance('classic');assert.equal(denied.hook.getState().appearance,'classic','Choice still works without browser storage');
console.log('PASS default Rabbit Hole, saved preference and unavailable browser storage');

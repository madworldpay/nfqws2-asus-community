import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';

const source = new URL('../webui/web/src/api/packageUpdates.ts', import.meta.url);
assert.ok(existsSync(source), 'package update client is missing');
const api = await import(source.href);
const candidate = {
  revision: 'a'.repeat(64), package_version: '1.3.1-asus6+b12',
  core_version: '1.3.1-asus6', web_version: '0.1.4', build: 12,
  notes: 'A real signed Build.',
  package: { family: 'aarch64-3.10', filename: 'nfqws2-asus_1.3.1-asus6+b12_aarch64-3.10.ipk', size: 1000, sha256: 'b'.repeat(64) },
};
const available = { state: 'available', candidate, code: null, installed_version: '1.3.1-asus6+b11' };
assert.deepEqual(api.packageUpdateBadges(available, '1.3.1-asus6+b11', '0.1.4', '11'), { core: false, web: false, build: true });
assert.deepEqual(api.packageUpdateBadges({ ...available, candidate: { ...candidate, core_version: '1.3.2-asus7', web_version: '0.1.5' } }, '1.3.1-asus6+b11', '0.1.4', '11'), { core: true, web: true, build: true });
assert.deepEqual(api.packageUpdateBadges({ ...available, state: 'failed' }, '1.3.1-asus6+b11', '0.1.4', '11'), { core: false, web: false, build: false });
assert.match(api.packageUpdateRequestId(), /^[a-f0-9]{32}$/);
assert.notEqual(api.packageUpdateRequestId(), api.packageUpdateRequestId());

const operation = { id: 'c'.repeat(32), revision: candidate.revision, state: 'applying', phase: 'queued', package_version: candidate.package_version, code: null, service_intent: null };
const calls = [];
globalThis.fetch = async (url, options) => {
  calls.push([url, options]);
  const cmd = options.body.get('cmd');
  return Response.json(cmd === 'packageupdatecheck' ? available : cmd === 'packageupdatestatus' ? { check: available, operation } : operation);
};
assert.deepEqual(await api.checkPackageUpdate('csrf', true), available);
assert.equal(calls[0][0], '/index.php');assert.equal(calls[0][1].credentials, 'same-origin');assert.equal(calls[0][1].redirect, 'error');
assert.equal(calls[0][1].body.get('force'), '1');
await api.preparePackageUpdate('csrf', candidate.revision, 'd'.repeat(32));
await api.applyPackageUpdate('csrf', operation.id, candidate.revision, 'e'.repeat(32));
assert.equal(calls.at(-1)[1].body.get('consent'), 'install');
assert.equal(calls.at(-1)[1].body.get('csrf_token'), 'csrf');
assert.equal((await api.getPackageUpdate('csrf', operation.id)).id, operation.id);
assert.equal((await api.getPackageUpdateOverview('csrf')).operation.state, 'applying');

globalThis.fetch = async () => Response.json({ error: 'busy' }, { status: 409 });
await assert.rejects(api.checkPackageUpdate('csrf', false), error => error.code === 'busy');
globalThis.fetch = async () => Response.json({ ...available, token: 'PRIVATE_CANARY' });
await assert.rejects(api.checkPackageUpdate('csrf', false), error => error.code === 'invalid_response');
globalThis.fetch = async () => Response.json({ state: 'current', candidate: null, code: null, installed_version: null });
assert.equal((await api.checkPackageUpdate('csrf', false)).state, 'current');
console.log('PASS: component-specific update badges, HTTP-LAN request IDs, consent/CSRF, strict responses and status-only recovery');

// A persisted receipt must name its own release, even while a newer one is
// installed or available. Render the actual dialog, not a string formatter.
const {build}=await import('../webui/web/node_modules/esbuild/lib/main.js');
const {mkdtemp,rm}=await import('node:fs/promises');
const {tmpdir}=await import('node:os');const {join}=await import('node:path');
const {fileURLToPath,pathToFileURL}=await import('node:url');
const directory=await mkdtemp(join(tmpdir(),'update-receipt-'));
try {
 const outfile=join(directory,'render.cjs');
 await build({stdin:{resolveDir:fileURLToPath(new URL('../webui/web/',import.meta.url)),contents:`
import {createElement as h} from 'react';import {renderToStaticMarkup} from 'react-dom/server';
import {PackageUpdateDialog} from '@/components/PackageUpdateDialog';import {TranslationContext} from '@/context/TranslationContext';
import ru from '@/translations/ru.json';import en from '@/translations/en.json';
export function render(language,operation){
const pack=language==='ru'?ru:en;const t=(key,params={})=>key.split('.').reduce((v,k)=>v[k],pack).replace(/{{(\\w+)}}/g,(_,k)=>String(params[k]??''));
return renderToStaticMarkup(h(TranslationContext.Provider,{value:{t}},h(PackageUpdateDialog,{open:true,onClose(){},installed:'1.3.1-asus6+b17',updates:{pending:false,error:null,data:{check:{state:'available',candidate:{package_version:'1.3.1-asus6+b18',core_version:'1.3.1-asus6',web_version:'0.1.4',build:18,revision:'x',notes:''}},operation},refresh(){},prepare(){},apply(){}}})));
}`},bundle:true,platform:'node',format:'cjs',outfile,logLevel:'silent',tsconfig:fileURLToPath(new URL('../webui/web/tsconfig.app.json',import.meta.url)),plugins:[{name:'render-in-place',setup(b){b.onResolve({filter:/^@mui\/material$/},()=>({path:'mui',namespace:'fixture'}));b.onLoad({filter:/.*/,namespace:'fixture'},()=>({contents:`import {createElement as h} from 'react';export const Dialog=({children})=>h('section',{},children);export const DialogTitle=Dialog,DialogContent=Dialog,DialogActions=Dialog,Stack=Dialog,Typography=Dialog,Button=Dialog,LinearProgress=Dialog;export const Alert=({children,severity})=>h('div',{'data-severity':severity},children);`,resolveDir:fileURLToPath(new URL('../webui/web/',import.meta.url))}));}}]});
 const {render}=await import(pathToFileURL(outfile));
 for(const lang of ['ru','en'])for(const installed_version of ['1.3.1-asus6+b16',undefined]) {
  const html=render(lang,{...operation,state:'succeeded',package_version:'1.3.1-asus6+b16',installed_version});
  const receipt=html.match(/<div data-severity="success">([^<]*)<\/div>/)?.[1];
  assert.ok(receipt,'completed operation needs a success receipt');
  assert.match(receipt,/1\.3\.1-asus6/);assert.match(receipt,/Build 16/);
  assert.doesNotMatch(receipt,/Build 17|Build 18/,'receipt must not use current or candidate version');
  assert.doesNotMatch(html,/Установка завершена\.|Обновление установлено\./,'remove duplicated generic messages');
 }
 console.log('PASS RU/EN success receipt names the completed release, including older persisted operations');
}finally{await rm(directory,{recursive:true,force:true});}

import assert from 'node:assert/strict';
import {existsSync} from 'node:fs';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {build} from '../webui/web/node_modules/esbuild/lib/main.js';
assert.ok(existsSync(fileURLToPath(new URL('../webui/web/src/components/ShareThanks.tsx',import.meta.url))),'A confirmed send needs a theme-aware acknowledgement');
const dir=await mkdtemp(join(tmpdir(),'nfqws-share-thanks-'));
try {
 const out=join(dir,'render.cjs');
 await build({stdin:{resolveDir:fileURLToPath(new URL('../webui/web/',import.meta.url)),contents:`
 import {createElement as h} from 'react';import {renderToStaticMarkup} from 'react-dom/server';
 import {TranslationContext} from './src/context/TranslationContext';import ru from './src/translations/ru.json';
 import {ShareThanks} from './src/components/ShareThanks';
 const t=(key)=>key.split('.').reduce((v,k)=>v?.[k],ru)||key;
 export function render(appearance,event){return renderToStaticMarkup(h(TranslationContext.Provider,{value:{t}},h(ShareThanks,{appearance,event,onClose(){}})));}
 `},bundle:true,platform:'node',format:'cjs',outfile:out,jsx:'automatic',logLevel:'silent',tsconfig:fileURLToPath(new URL('../webui/web/tsconfig.app.json',import.meta.url))});
 const {render}=await import(out);
 assert.equal(render('rabbit',0),'','Do not show approval before an accepted send');
 const classic=render('classic',123); assert.ok(classic.includes('Кролик наблюдает. И он одобряет.'));assert.ok(!classic.includes('rabbit-respect-once.gif'));
 const rabbit=render('rabbit',123);assert.ok(rabbit.includes('rabbit-respect-once.gif?sent=123'));assert.ok(rabbit.includes('Кролик наблюдает. И он одобряет.'));
 assert.ok(render('rabbit',124).includes('?sent=124'),'A separate accepted send starts a fresh one-shot animation');
 console.log('Accepted-send acknowledgement: hidden before acceptance, classic text, rabbit animation and fresh playback per send: PASS');
} finally {await rm(dir,{recursive:true,force:true});}

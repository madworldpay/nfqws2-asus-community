import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { build } from '../webui/web/node_modules/esbuild/lib/main.js';

const web = fileURLToPath(new URL('../webui/web/',import.meta.url));
const directory = await mkdtemp(join(tmpdir(),'update-notes-ui-'));
try {
  const outfile = join(directory,'render.cjs');
  await build({
    stdin:{resolveDir:web,loader:'tsx',contents:`
import React from 'react';import {renderToStaticMarkup} from 'react-dom/server';
import {PackageUpdateDialog} from '@/components/PackageUpdateDialog';
import {TranslationContext} from '@/context/TranslationContext';
import ru from '@/translations/ru.json';import en from '@/translations/en.json';
export function render(lang,notes,loading=false,prepared=false){
const pack=lang==='ru'?ru:en;
const t=(key,params={})=>key.split('.').reduce((v,k)=>v[k],pack).replace(/{{(\\w+)}}/g,(_,k)=>String(params[k]??''));
const candidate={revision:'a'.repeat(64),build:71,package_version:'1.3.2-asus6+b71',notes:'Signed target notes'};
const operation=prepared?{revision:candidate.revision,state:'prepared',id:'b'.repeat(32)}:null;
return renderToStaticMarkup(<TranslationContext.Provider value={{t}}><PackageUpdateDialog open={true} onClose={()=>{}} installed="1.3.1-asus6+b62" updates={{data:{check:{state:'available',candidate,installed_version:'1.3.1-asus6+b62'},operation},notes,notesLoading:loading,pending:false,refresh(){},prepare(){},apply(){}}}/></TranslationContext.Provider>);
}`},
    bundle:true,platform:'node',format:'cjs',outfile,logLevel:'silent',
    tsconfig:join(web,'tsconfig.app.json'),
    plugins:[{name:'render-dialog-content',setup(b){
      // A portal is absent during SSR; replace only its shell, keeping actual
      // MUI controls and the production dialog's branches and text.
      b.onResolve({filter:/^@mui\/material$/},()=>({path:'mui',namespace:'fixture'}));
      b.onLoad({filter:/.*/,namespace:'fixture'},()=>({contents:`
export * from ${JSON.stringify(join(web,'node_modules/@mui/material/index.js'))};
import {createElement as h} from 'react';export const Dialog=({children})=>h('section',{},children);
`,resolveDir:web}));
    }}],
  });
  const {render} = await import(pathToFileURL(outfile));
  const notes={from_build:62,to_build:71,complete:true,releases:[
    {build:64,notes:'First missed changes'},
    {build:70,notes:'Previous changes <script>alert(1)</script>\n**Import** [Read guide](https://github.com/madworldpay/nfqws2-asus-community/blob/main/IMPORT.md)'},
    {build:71,notes:'Latest published changes'},
  ]};
  for(const lang of ['ru','en']) {
    const malformed=render(lang,{...notes,releases:[{build:71,notes:'[Broken](https://%) [Outside](https://example.com/test) [Credentials](https://user:pass@github.com/madworldpay/nfqws2-asus-community)'}]});
    assert.doesNotMatch(malformed,/<a /,'malformed or foreign links must remain safe text');
    const html=render(lang,notes);
    assert.ok(html.indexOf('Build 64') < html.indexOf('Build 70'));
    assert.ok(html.indexOf('Build 70') < html.lastIndexOf('Build 71'));
    assert.match(html,/First missed changes/);
    assert.match(html,/Latest published changes/);
    assert.doesNotMatch(html,/Signed target notes/,'do not duplicate target notes');
    assert.doesNotMatch(html,/<script>/,'release text must not become executable HTML');
    assert.match(html,/&lt;script&gt;/);
    assert.match(html,/<strong>Import<\/strong>/);
    assert.match(html,/href="https:\/\/github.com\/madworldpay\/nfqws2-asus-community\/blob\/main\/IMPORT.md"/);
    assert.doesNotMatch(html,/\[Read guide\]/,'show a readable link instead of Markdown syntax');
    assert.doesNotMatch(html,/history is unavailable|история изменений недоступна/);
    assert.match(html,/Build 62 → Build 71/);
    for(const history of [undefined,{...notes,complete:false}]) {
      for(const prepared of [false,true]) {
        const fallback=render(lang,history,false,prepared);
        assert.match(fallback,/history is unavailable|история изменений недоступна/);
        if(!history)assert.match(fallback,/Signed target notes/);
        const label=prepared?(lang==='ru'?'Установить обновление':'Install update'):(lang==='ru'?'Подготовить пакет':'Prepare package');
        const button=fallback.match(new RegExp('<button([^>]*)>'+label+'<\\/button>'));
        assert.ok(button,`missing action: ${label}`);
        assert.doesNotMatch(button[1],/disabled/,'unavailable history must not block updating');
      }
    }
    const loading=render(lang,undefined,true);
    assert.match(loading,/Loading release history|Загружаем историю/);
    assert.doesNotMatch(loading,/history is unavailable|история изменений недоступна/);
  }
  console.log('PASS RU/EN cumulative dialog, safe text, target fallback and nonblocking prepare/install');
} finally {await rm(directory,{recursive:true,force:true});}

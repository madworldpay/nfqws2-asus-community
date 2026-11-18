import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { build } from '../webui/web/node_modules/esbuild/lib/main.js';

const web = fileURLToPath(new URL('../webui/web/', import.meta.url));
const dir = await mkdtemp(join(tmpdir(), 'current-panel-labels-'));
try {
  await build({ stdin: { resolveDir: web, loader: 'tsx', contents: `
    import React from 'react';
    import {renderToStaticMarkup} from 'react-dom/server';
    import {MainTabs} from './src/components/MainTabs';
    import {ImportAddons} from './src/components/ImportAddons';
    import {TranslationContext} from './src/context/TranslationContext';
    import ru from './src/translations/ru.json';
    import en from './src/translations/en.json';
    export function render(lang) {
      const pack=lang==='ru'?ru:en;
      const t=key=>key.split('.').reduce((value,part)=>value[part],pack);
      return renderToStaticMarkup(<TranslationContext.Provider value={{t,langcode:lang,setLanguage(){}}}>
        <MainTabs/><ImportAddons csrfToken="fixture" disabled={false} value={[]} onChange={()=>{}}/>
      </TranslationContext.Provider>);
    }
  ` }, bundle: true, platform: 'node', format: 'cjs', outfile: join(dir, 'ui.cjs'),
  tsconfig: join(web, 'tsconfig.app.json'), logLevel: 'silent', plugins: [{ name: 'offline-boundaries', setup(b) {
    b.onResolve({ filter: /^@tanstack\/react-router$/ }, () => ({ path: 'router', namespace: 'fixture' }));
    b.onLoad({ filter: /^router$/, namespace: 'fixture' }, () => ({ contents: 'export const useNavigate=()=>()=>{};export const useLocation=()=>({pathname:"/"});export const useParams=()=>({});', loader: 'js' }));
    b.onLoad({ filter: /hooks\/useStatus\.tsx$/ }, () => ({ contents: 'export const useStatus=()=>({platform:"asus-entware",isPending:false});', loader: 'tsx' }));
  } }] });
  const { render } = await import(pathToFileURL(join(dir, 'ui.cjs')));
  const values = object => Object.values(object).flatMap(value => typeof value === 'string' ? [value] : values(value));
  for (const lang of ['ru', 'en']) {
    const html = render(lang).replace(/<style\b[^>]*>[\s\S]*?<\/style>/g, '');
    assert.doesNotMatch(html, /beta|бета/iu, `${lang}: current tabs and add-ons have no beta label`);
    assert.match(html, /href="\/device-profiles-lab\/device-profiles-lab\.html"/);
    assert.match(html, /href="\/strategy-picker\/index\.html"/);
    assert.match(html, lang === 'ru' ? /aria-label="Дополнения"/ : /aria-label="Add-ons"/);
    const pack = JSON.parse(await readFile(join(web, 'src/translations', lang + '.json'), 'utf8'));
    assert.equal(typeof pack.tabs.devices_beta, 'string', 'existing translation keys stay compatible');
    assert.equal(typeof pack.tabs.strategy_picker_beta, 'string', 'existing translation keys stay compatible');
    assert.doesNotMatch(values(pack).join('\n'), /beta|бета/iu, `${lang}: help and recovery text have no beta label`);
  }
  console.log('PASS current MainTabs/ImportAddons React render and translation values RU/EN; compatible keys retained');
} finally {
  await rm(dir, { recursive: true, force: true });
}

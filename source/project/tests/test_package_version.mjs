import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { build } from '../webui/web/node_modules/esbuild/lib/main.js';

assert.ok(
  existsSync(
    new URL('../webui/web/src/utils/packageVersion.ts', import.meta.url),
  ),
  'Installed package version and build parsing is missing',
);
const { parsePackageVersion, compareVersions } =
  await import('../webui/web/src/utils/packageVersion.ts');

assert.deepEqual(parsePackageVersion('1.3.1-asus6+b1'), {
  version: [1, 3, 1],
  packageVersion: '1.3.1-asus6+b1',
  buildNumber: '1',
});
assert.deepEqual(parsePackageVersion('1.3.1-asus6+b12'), {
  version: [1, 3, 1],
  packageVersion: '1.3.1-asus6+b12',
  buildNumber: '12',
});
assert.deepEqual(parsePackageVersion('1.3.1-asus5'), {
  version: [1, 3, 1],
  packageVersion: '1.3.1-asus5',
  buildNumber: undefined,
});
assert.deepEqual(parsePackageVersion('v2.10.3'), {
  version: [2, 10, 3],
  packageVersion: 'v2.10.3',
  buildNumber: undefined,
});
for (const missing of [undefined, null, '']) {
  assert.deepEqual(parsePackageVersion(missing), {
    version: [0, 0, 0],
    packageVersion: undefined,
    buildNumber: undefined,
  });
}
assert.deepEqual(parsePackageVersion('invalid+b12'), {
  version: [0, 0, 0],
  packageVersion: 'invalid+b12',
  buildNumber: undefined,
});
assert.equal(
  compareVersions(parsePackageVersion('1.3.1-asus6+b1').version, [1, 3, 1]),
  false,
);
assert.equal(
  compareVersions(parsePackageVersion('1.3.1-asus6+b1').version, [1, 3, 2]),
  true,
);
assert.equal(compareVersions([1, 9, 99], [1, 10, 0]), true);
assert.equal(compareVersions([2, 0, 0], [1, 99, 99]), false);

// Render the real status hook and badges from cached API data; no network request.
const temporary = await mkdtemp(join(tmpdir(), 'nfqws-package-version-'));
try {
  const outfile = join(temporary, 'render.cjs');
  await build({
    stdin: {
      resolveDir: fileURLToPath(new URL('../webui/web/', import.meta.url)),
      contents: String.raw`
        import { createElement } from 'react';
        import { renderToStaticMarkup } from 'react-dom/server';
        import { QueryClientProvider } from '@tanstack/react-query';
        import { queryClient } from '@/api/client';
        import { createAPIClient } from '@/api/create-api-client';
        import { CurrentVersion } from '@/components/CurrentVersion';
        import { TranslationContext } from '@/context/TranslationContext';
        import en from '@/translations/en.json';
        import ru from '@/translations/ru.json';

        export function renderVersion(version, language, update) {
          const key = createAPIClient().indexPhp.postIndexCmd.getQueryKey({ body: { cmd: 'status' } });
          queryClient.setQueryData(key, { status: 0, anonym: true, nfqws2: true, service: false, version, csrf_token: 'test-csrf', username: 'test-user' });
          queryClient.setQueryData(['package-update-overview', 'test-csrf'], {check: update ?? {state:'current', candidate:null, code:null, installed_version:version}, operation:null});
          const pack = language === 'ru' ? ru : en;
          const t = (path, params = {}) => path.split('.').reduce((value, key) => value[key], pack)
            .replace(/\{\{(\w+)}}/g, (_, key) => String(params[key]));
          return renderToStaticMarkup(createElement(QueryClientProvider, { client: queryClient },
            createElement(TranslationContext.Provider, { value: { t, langcode: language, setLanguage() {} } },
              createElement(CurrentVersion))));
        }
      `,
    },
    tsconfig: fileURLToPath(
      new URL('../webui/web/tsconfig.app.json', import.meta.url),
    ),
    define: {
      'window.location.origin': '"http://localhost"',
      'process.env.APP_VERSION': '"0.1.4"',
    },
    bundle: true,
    platform: 'node',
    format: 'cjs',
    outfile,
    logLevel: 'silent',
  });
  const { renderVersion } = await import(pathToFileURL(outfile).href);
  const labels = (html) =>
    Array.from(
      html.matchAll(/<span class="MuiChip-label[^"]*">([^<]*)<\/span>/g),
      (match) => match[1],
    );
  assert.deepEqual(labels(renderVersion('1.3.1-asus6+b1', 'ru')), [
    '1.3.1-asus6 — Build 1',
  ]);
  assert.deepEqual(labels(renderVersion('1.3.1-asus6+b12', 'en')), [
    '1.3.1-asus6 — Build 12',
  ]);
  assert.deepEqual(labels(renderVersion('1.3.1-asus5', 'ru')), [
    '1.3.1-asus5',
  ]);
  const candidate = {revision:'a'.repeat(64),package_version:'1.3.1-asus6+b13',core_version:'1.3.1-asus6',web_version:'0.1.4',build:13,notes:'Test',package:{}};
  const update = {state:'available',code:null,installed_version:'1.3.1-asus6+b12',candidate};
  assert.equal((renderVersion('1.3.1-asus6+b12','ru',update).match(/MuiChip-colorWarning/g) ?? []).length,1);
  assert.equal((renderVersion('1.3.1-asus6+b12','ru',{...update,candidate:{...candidate,core_version:'1.3.2-asus7',web_version:'0.1.5'}}).match(/MuiChip-colorWarning/g) ?? []).length,1);
  const webOnly = {...candidate,package_version:'1.3.1-asus6+b12',build:12,web_version:'0.1.5'};
  const html = renderVersion('1.3.1-asus6+b12','ru',{...update,candidate:webOnly});
  assert.deepEqual(labels(html), ['1.3.1-asus6 — Build 12']);
  assert.equal((html.match(/MuiChip-colorWarning/g) ?? []).length,1,'hidden WebUI version still participates in update detection');
  assert.equal((renderVersion('1.3.1-asus6+b12','ru',{...update,state:'failed',candidate:null}).match(/MuiChip-colorWarning/g) ?? []).length,0);
} finally {
  await rm(temporary, { recursive: true, force: true });
}
console.log(
  'PASS: one revision/build badge without a WebUI version; all component updates remain visible',
);

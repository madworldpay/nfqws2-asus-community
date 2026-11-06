import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { build } from '../webui/web/node_modules/esbuild/lib/main.js';
const dir = await mkdtemp(join(tmpdir(), 'import-addons-client-'));
try {
  const root = fileURLToPath(new URL('../webui/web/src/', import.meta.url));
  await build({ entryPoints: [join(root, 'api/importClient.ts')], outfile: join(dir, 'client.mjs'), bundle: true, alias: { '@': root }, platform: 'node', format: 'esm', logLevel: 'silent' });
  const client = await import(pathToFileURL(join(dir, 'client.mjs')));
  const base = { ready: true, problems: [], warnings: [], required: { files: [], shared: [] }, affected_blocks: [], config: '', changes: [], files: [], draft: null, old_draft: null, digest: 'a'.repeat(64), proof: 'fixture-proof' };
  const addon = { id: 'riot-web', title: 'Riot web', kind: 'scope_domains_v1', domains: ['riotgames.com', 'riotcdn.net'], action: 'scope_extended', note: 'Exclusions retained.' };
  globalThis.fetch = async () => Response.json({ ...base, addons: [{ ...addon, kind: 'run_shell' }] });
  await assert.rejects(client.prepareImport('csrf', ['{}'], client.emptyImportSelection()), { code: 'invalid_response' }, 'unknown addon rule kind must not become a trusted preview');
  for (const patch of [
    { domains: ['https://riotgames.com'] }, { domains: ['*.riotgames.com'] }, { domains: ['127.0.0.1'] },
    { domains: ['RIOTGAMES.COM'] }, { domains: ['riotgames.com', 'riotgames.com'] },
    { domains: ['riot.local'] }, { domains: ['x.a'] }, { domains: ['riot.c0m'] }, { domains: ['home.arpa'] },
    { action: 'applied' }, { note: 1 }, { note: 'x'.repeat(4097) }, { url: 'https://untrusted.invalid/' },
  ]) {
    globalThis.fetch = async () => Response.json({ ...base, addons: [{ ...addon, ...patch }] });
    await assert.rejects(client.prepareImport('csrf', ['{}'], client.emptyImportSelection()), { code: 'invalid_response' });
  }
  globalThis.fetch = async () => Response.json({ ...base, addons: [addon, addon] });
  await assert.rejects(client.prepareImport('csrf', ['{}'], client.emptyImportSelection()), { code: 'invalid_response' });
  globalThis.fetch = async () => Response.json({ ...base, addons: [addon, { ...addon, id: 'covered', domains: [], action: 'already_covered' }] });
  assert.deepEqual((await client.prepareImport('csrf', ['{}'], client.emptyImportSelection())).addons, [addon, { ...addon, id: 'covered', domains: [], action: 'already_covered' }]);
  assert.equal(client.importOutcomeUnknown(new client.ImportError('invalid_addon_source')), false, 'verified addon rejection leaves retry safe');
  await build({ entryPoints: [join(root, 'api/importAddonClient.ts')], outfile: join(dir, 'catalog.mjs'), bundle: true, alias: { '@': root }, platform: 'node', format: 'esm', logLevel: 'silent' });
  const { loadImportAddonCatalog } = await import(pathToFileURL(join(dir, 'catalog.mjs')));
  const entry = { id: 'riot-web', title: 'Riot web', description: 'Domains use the base strategy; game UDP is unverified.', attribution: '', updated_at: '2026-11-06T00:00:00Z', revision: 1, min_build: 92, size: 320, sha256: 'd'.repeat(64) };
  const catalog = { schema_version: 1, revision: 1, build: 92, addons: [entry] };
  globalThis.fetch = async (_url, options) => {
    assert.deepEqual(Object.fromEntries(options.body), { cmd: 'importaddoncatalog', csrf_token: 'csrf' }, 'client sends no URLs, rules, documents or credentials');
    return Response.json(catalog);
  };
  assert.deepEqual(await loadImportAddonCatalog('csrf'), catalog);
  for (const invalid of [
    { ...catalog, schema_version: 2 }, { ...catalog, revision: 0 }, { ...catalog, url: 'https://untrusted.invalid/' },
    { ...catalog, addons: [entry, entry] }, { ...catalog, addons: Array.from({ length: 65 }, (_, n) => ({ ...entry, id: 'entry-' + n })) },
    ...[{ id: '../riot-web' }, { title: ' ' }, { description: 'x'.repeat(601) }, { attribution: 'x'.repeat(241) }, { size: 65537 }, { min_build: 91 }, { sha256: 'D'.repeat(64) }, { kind: 'run_shell' }].map(patch => ({ ...catalog, addons: [{ ...entry, ...patch }] })),
  ]) {
    globalThis.fetch = async () => Response.json(invalid);
    await assert.rejects(loadImportAddonCatalog('csrf'), { code: 'catalog_invalid' });
  }
  console.log('PASS add-on preview closed kinds, exact fields, normalized DNS names, limits, duplicates and safe error classification');
} finally { await rm(dir, { recursive: true, force: true }); }

import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { build } from '../webui/web/node_modules/esbuild/lib/main.js';
const dir = await mkdtemp(join(tmpdir(), 'keenetic-client-'));
try {
  const root = fileURLToPath(new URL('../webui/web/src/', import.meta.url));
  await build({ entryPoints: [join(root, 'api/importClient.ts')], outfile: join(dir, 'client.mjs'), bundle: true, alias: { '@': root }, platform: 'node', format: 'esm', logLevel: 'silent' });
  const api = await import(pathToFileURL(join(dir, 'client.mjs')));
  assert.equal(typeof api.convertKeeneticImport, 'function', 'Expose the read-only Keenetic converter');
  const text = 'NFQWS_ARGS="--filter-tcp=443 --lua-desync=fake:blob=tls"\r\n# С телефона\r\n';
  const document = '{"type":"nfqws2_strategy","schema_version":1}';
  const calls = [];
  globalThis.fetch = async (url, options) => { calls.push({ url, post: Object.fromEntries(options.body), credentials: options.credentials }); return Response.json({ document }); };
  assert.equal(await api.convertKeeneticImport('csrf', text), document);
  assert.deepEqual(calls, [{ url: '/index.php', post: { cmd: 'importconvert', csrf_token: 'csrf', text }, credentials: 'same-origin' }]);
  const count = calls.length;
  await assert.rejects(api.convertKeeneticImport('csrf', ' \n\t'), e => e.code === 'unsupported_keenetic_strategy');
  await assert.rejects(api.convertKeeneticImport('csrf', 'я'.repeat(32769)), e => e.code === 'keenetic_limit');
  assert.equal(calls.length, count, 'Reject empty and oversized UTF8 before a request');
  for (const value of [{ document: '' }, { document: [] }, { document, url: 'https://bad.invalid' }, { document: 'x'.repeat(262145) }]) {
    globalThis.fetch = async () => Response.json(value);
    await assert.rejects(api.convertKeeneticImport('csrf', text), e => e.code === 'invalid_response');
  }
  globalThis.fetch = async () => Response.json({ error: 'unsupported_keenetic_strategy' }, { status: 422 });
  await assert.rejects(api.convertKeeneticImport('csrf', text), e => e.code === 'unsupported_keenetic_strategy');
  console.log('PASS Keenetic converter client: exact text/read-only command, UTF8 byte limit, strict bounded response and unsupported-format errors');
} finally { await rm(dir, { recursive: true, force: true }); }

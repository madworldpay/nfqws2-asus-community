import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { File } from 'node:buffer';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { build } from '../webui/web/node_modules/esbuild/lib/main.js';
const dir = await mkdtemp(join(tmpdir(), 'blob-client-'));
try {
  const root = fileURLToPath(new URL('../webui/web/src/', import.meta.url));
  await build({ entryPoints: [join(root, 'api/blobClient.ts')], outfile: join(dir, 'client.mjs'), bundle: true, alias: { '@': root }, platform: 'node', format: 'esm', logLevel: 'silent' });
  const api = await import(pathToFileURL(join(dir, 'client.mjs')));
  const bytes = Buffer.from([0, 255, 128, 10, 13, 1, 254]);
  const hash = createHash('sha256').update(bytes).digest('hex');
  const file = { name: 'hello.bin', path: '/etc/nfqws2/blobs/hello.bin', byte_length: bytes.length, sha256: hash, state: 'available', format: 'tls', label: { ru: 'Пример', en: 'Example' }, bundled: true };
  const inventory = { files: [file], skipped: 0, scan_truncated: false };
  const calls = [];
  globalThis.fetch = async (url, opts) => { calls.push({ url, opts, post: Object.fromEntries(opts.body) }); return Response.json(inventory); };
  assert.deepEqual(await api.loadBlobInventory('csrf'), inventory);
  assert.deepEqual(calls[0].post, { cmd: 'blobinventory', csrf_token: 'csrf' });
  assert.equal(calls[0].opts.credentials, 'same-origin');
  const unavailable = { ...file, state: 'unavailable', sha256: null, byte_length: 0, format: 'other', label: null, bundled: false };
  globalThis.fetch = async () => Response.json({ files: [unavailable], skipped: 1, scan_truncated: true });
  assert.equal((await api.loadBlobInventory('csrf')).files[0].state, 'unavailable');
  globalThis.fetch = async () => Response.json({ files: Array.from({ length: 128 }, (_, n) => ({ ...file, name: `long-${n}-${'x'.repeat(104)}.bin`, path: `/etc/nfqws2/blobs/long-${n}-${'x'.repeat(104)}.bin`, label: { ru: '"'.repeat(256), en: '"'.repeat(256) } })), skipped: 0, scan_truncated: false });
  assert.equal((await api.loadBlobInventory('csrf')).files.length, 128, 'Full valid inventory fits the response bound');
  for (const bad of [{ ...inventory, extra: 1 }, { ...inventory, files: [file, file] }, { ...inventory, files: Array(129).fill(file) }, { ...inventory, files: [{ ...file, path: '/tmp/hello.bin' }] }, { ...inventory, files: [{ ...file, name: '../hello.bin' }] }, { ...inventory, files: [{ ...file, format: ['tls'] }] }, { ...inventory, files: [{ ...file, state: ['available'] }] }, { ...inventory, files: [{ ...file, byte_length: 0 }] }, { ...inventory, files: [{ ...file, sha256: null }] }, { ...inventory, skipped: -1 }]) {
    globalThis.fetch = async () => Response.json(bad);
    await assert.rejects(api.loadBlobInventory('csrf'), e => e.code === 'invalid_response');
  }
  globalThis.fetch = async (url, opts) => { calls.push({ url, opts, post: Object.fromEntries(opts.body) }); return Response.json({ file: { ...file, bundled: false } }); };
  assert.deepEqual(await api.uploadBlob('csrf', new File([bytes], 'Мой шаблон.bin')), { ...file, bundled: false });
  assert.deepEqual(calls.at(-1).post, { cmd: 'blobupload', csrf_token: 'csrf', name: 'Мой шаблон.bin', data_base64: 'AP+ACg0B/g==', sha256: hash });
  const count = calls.length;
  for (const [name, data, code] of [['empty.bin', [], 'empty_file'], ['large.bin', new Uint8Array(262145), 'file_too_large'], ['hello.json', [1], 'invalid_name']]) {
    await assert.rejects(api.uploadBlob('csrf', new File([new Uint8Array(data)], name)), e => e.code === code);
  }
  assert.equal(calls.length, count, 'Invalid files are rejected before network access');
  globalThis.fetch = async () => Response.json({ file: { ...file, sha256: 'a'.repeat(64) } });
  await assert.rejects(api.uploadBlob('csrf', new File([bytes], 'hello.bin')), e => e.code === 'invalid_response');
  globalThis.fetch = async () => Response.json({ error: 'busy' }, { status: 409 });
  await assert.rejects(api.uploadBlob('csrf', new File([bytes], 'hello.bin')), e => e.code === 'busy');
  console.log('PASS bounded blob inventory and upload: exact binary, HTTP-safe SHA256, explicit commands, strict schema, local validation and error preservation');
} finally { await rm(dir, { recursive: true, force: true }); }

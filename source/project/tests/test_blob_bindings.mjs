import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { build } from '../webui/web/node_modules/esbuild/lib/main.js';
const dir = await mkdtemp(join(tmpdir(), 'blob-bindings-'));
try {
  const root = fileURLToPath(new URL('../webui/web/src/', import.meta.url));
  await build({ entryPoints: [join(root, 'utils/blobBindings.ts')], outfile: join(dir, 'bindings.mjs'), bundle: true, platform: 'node', format: 'esm', logLevel: 'silent' });
  const { parseBlobBindings: parse, replaceBlobBinding: replace } = await import(pathToFileURL(join(dir, 'bindings.mjs')));
  const source = "  --debug=0\n--blob='hello:@/opt/etc/nfqws2/blobs/old.bin'  \\\n --blob \"quic:@/opt/etc/nfqws2/blobs/q.bin\" --lua-init=@/keep.lua\n--lua-desync=fake:blob=hello";
  const parsed = parse(source);
  assert.deepEqual(parsed.bindings.map(({ alias, path }) => ({ alias, path })), [{ alias: 'hello', path: '/opt/etc/nfqws2/blobs/old.bin' }, { alias: 'quic', path: '/opt/etc/nfqws2/blobs/q.bin' }]);
  assert.equal(parsed.unsupported, 0);
  assert.equal(replace(source, parsed.bindings[0], '/opt/etc/nfqws2/blobs/new.bin'), source.replace("'hello:@/opt/etc/nfqws2/blobs/old.bin'", "'hello:@/opt/etc/nfqws2/blobs/new.bin'"));
  assert.equal(replace(source, parsed.bindings[1], '/etc/nfqws2/blobs/new.bin'), source.replace('"quic:@/opt/etc/nfqws2/blobs/q.bin"', '"quic:@/etc/nfqws2/blobs/new.bin"'));
  const escaped = '--blob=tls:@/opt/etc/nfqws2/blobs/old\\.bin --filter-tcp=443';
  assert.equal(parse(escaped).bindings[0].path, '/opt/etc/nfqws2/blobs/old.bin');
  assert.equal(replace(escaped, parse(escaped).bindings[0], '/opt/etc/nfqws2/blobs/new.bin'), '--blob=tls:@/opt/etc/nfqws2/blobs/new.bin --filter-tcp=443');
  const mixed = '--blob=tls:@/opt/etc/nfqws2/blobs/"old file.bin"';
  assert.equal(parse(mixed).bindings[0].path, '/opt/etc/nfqws2/blobs/old file.bin');
  assert.equal(replace(mixed, parse(mixed).bindings[0], '/opt/etc/nfqws2/blobs/new.bin'), '--blob=tls:@/opt/etc/nfqws2/blobs/new.bin');
  for (const raw of ['--blob=x:@/a --blob x:@/b', '--blob=x:@/a --blob=x:0x1234', "--blob=x:@/a '--blob=x:@/b'", '--blob=x:@/a --bl\\ob=x:@/b', "--blob=x:@/a '--blob' x:@/b", '--blob=x:@$ROOT/a', '--blob=x:@$(echo /a)', '--blob="x:@/a', '--blob=x:@/a;restart', '$(printf --blob=x:@/a )', 'echo ok; --blob=x:@/a', '`printf --blob=x:@/a `']) {
    assert.equal(parse(raw).bindings.length, 0, raw);
    assert.ok(parse(raw).unsupported > 0, raw);
  }
  assert.deepEqual(parse('--lua-desync="fake:blob=tls" --blob=builtin:0x1234').bindings, []);
  assert.throws(() => replace(source + ' --debug=1', parsed.bindings[0], '/opt/etc/nfqws2/blobs/new.bin'), /stale_binding/);
  assert.throws(() => replace(source, parsed.bindings[0], '/tmp/evil.bin'), /invalid_path/);
  assert.throws(() => replace(source, parsed.bindings[0], '/opt/etc/nfqws2/blobs/../evil.bin'), /invalid_path/);
  console.log('PASS named blob bindings: quoted/split/escaped operands, exact surrounding layout, duplicates, unsupported syntax and stale edits');
} finally { await rm(dir, { recursive: true, force: true }); }

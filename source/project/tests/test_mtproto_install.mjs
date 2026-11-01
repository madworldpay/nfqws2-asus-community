import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { spawnSync } from 'node:child_process';
import { build } from '../webui/web/node_modules/esbuild/lib/main.js';

const source = fileURLToPath(new URL('../webui/web/src/utils/mtprotoInstall.ts', import.meta.url));
assert.ok(existsSync(source), 'MTProto install generator is implemented');
const dir = await mkdtemp(join(tmpdir(), 'nfqws-mtproto-test-'));
try {
  await build({ entryPoints: [source], outfile: join(dir, 'install.mjs'), bundle: true, platform: 'node', format: 'esm', logLevel: 'silent', loader: { '.sh': 'text' } });
  const api = await import(pathToFileURL(join(dir, 'install.mjs')));
  const bytes = Uint8Array.from({ length: 16 }, (_, i) => i + 1);
  const secret = api.createMtprotoSecret(bytes);
  assert.equal(secret, 'dd0102030405060708090a0b0c0d0e0f10');
  assert.notEqual(api.createMtprotoSecret(), api.createMtprotoSecret(), 'Fresh secrets use independent secure random bytes');
  assert.throws(() => api.createMtprotoSecret(new Uint8Array(4)));
  const input = { server: 'proxy.example.org', port: '8443', secret };
  assert.deepEqual(api.validateMtproto(input), {});
  for (const value of ['https://proxy.example.org', 'host;id', '$(id)', 'a\nb', '--help', 'host:443', 'user@host', 'host/path', 'a..b', 'a#b']) {
    assert.ok(api.validateMtproto({ ...input, server: value }).server, 'Reject unsafe host: ' + JSON.stringify(value));
  }
  for (const value of ['0', '65536', '443;id', '1e3', '-1', '443\n', '']) {
    assert.ok(api.validateMtproto({ ...input, port: value }).port, 'Reject invalid port: ' + JSON.stringify(value));
  }
  assert.ok(api.validateMtproto({ ...input, secret: secret + "';id" }).secret);
  for (const host of ['203.0.113.10', 'proxy.example.org', '2001:db8::1', '[2001:db8::1]']) {
    const values = { ...input, server: host };
    assert.deepEqual(api.validateMtproto(values), {});
    const url = new URL(api.mtprotoLink(values));
    assert.equal(url.origin, 'https://t.me');
    assert.equal(url.pathname, '/proxy');
    assert.equal(url.searchParams.get('server'), host.replace(/^\[|\]$/g, ''));
    assert.equal(url.searchParams.get('port'), '8443');
    assert.equal(url.searchParams.get('secret'), secret);
  }
  for (const method of ['docker', 'entware', 'linux']) {
    const script = api.buildMtprotoInstall(method, input, 'ru');
    assert.equal(spawnSync('/bin/sh', ['-n'], { input: script }).status, 0, method + ' is valid POSIX shell');
    assert.ok(script.includes(secret.slice(2)), 'Configuration contains displayed secret');
    assert.ok(script.includes(api.mtprotoLink(input)), 'Installer prints the same connection link');
    assert.ok(!/curl\s+[^|\n]*\|\s*(?:sh|bash)/.test(script), 'No execution of an unverified downloaded installer');
    assert.ok(!/iptables|nvram|ufw|firewall-cmd/.test(script), 'No unsolicited changes to firewall or router configuration');
    assert.throws(() => api.buildMtprotoInstall(method, { ...input, server: 'host;id' }, 'ru'));
    const path = join(dir, method + '.sh');
    await writeFile(path, script);
    if (process.env.NFQWS_MTPROTO_SCRIPTS) await writeFile(join(process.env.NFQWS_MTPROTO_SCRIPTS, method + '.sh'), script);
  }
  for (const method of ['entware', 'linux']) assert.throws(() => api.buildMtprotoInstall(method, { ...input, port: '443' }, 'en'), 'Unprivileged native service rejects reserved ports');
  const docker = api.buildMtprotoInstall('docker', input, 'en');
  assert.ok(docker.includes('docker pull'));
  assert.ok(!docker.includes('docker build'));
  assert.ok(docker.includes(api.MTPROTO_DOCKER_IMAGE));
  assert.ok(docker.includes('PROXY_SECRET=$NFQWS_MT_KEY'));
  const compose = api.buildMtprotoCompose(input);
  assert.ok(compose.includes(api.MTPROTO_DOCKER_IMAGE));
  assert.ok(compose.includes('PROXY_SECRET: '+JSON.stringify(secret.slice(2))));
  assert.ok(compose.includes(JSON.stringify(input.port+':1443')));
  assert.ok(!compose.includes('privileged: true'));
  assert.throws(() => api.buildMtprotoCompose({ ...input, secret: 'bad' }));
  assert.ok(docker.includes('Flowseal/tg-ws-proxy'));
  assert.ok(docker.includes('docker info'));
  assert.ok(docker.includes('docker create'));
  assert.ok(docker.includes('docker start'));
  assert.ok(docker.includes('unless-stopped'));
  const linux = api.buildMtprotoInstall('linux', input, 'en');
  assert.ok(linux.includes('87a38c235d7a4a66d8a3fa50d64e42cc962c11c210a9e65df1469302a6521613'));
  assert.ok(linux.indexOf('sha256sum -c') < linux.indexOf('tar -x'), 'Verify source before extracting');
  assert.ok(linux.includes('os.setuid'), 'Drop root before importing proxy');
  assert.ok(linux.includes('/run/systemd/system'));
  for (const method of ['docker', 'entware', 'linux']) {
    const ru = api.buildMtprotoInstall(method, input, 'ru');
    const en = api.buildMtprotoInstall(method, input, 'en');
    assert.ok(ru.includes('MTProto'));
    assert.notEqual(ru, en, 'Installer feedback is localized');
  }
  console.log('PASS MTProto: secure secret, input/shell injection rejection, IPv4/IPv6 links, matching Docker/native config, pinned verified downloads and POSIX shell');
} finally {
  await rm(dir, { recursive: true, force: true });
}

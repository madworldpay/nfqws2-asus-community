import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from '../webui/web/node_modules/esbuild/lib/main.js';

const { chromium } = await import(process.env.NFQWS_PLAYWRIGHT_MODULE || 'playwright');
const web = fileURLToPath(new URL('../webui/web/', import.meta.url));
const directory = await mkdtemp(join(tmpdir(), 'nfqws-update-recovery-'));
const installed = '1.3.2-asus6+b79';
const candidate = {
  revision: 'a'.repeat(64), package_version: '1.3.2-asus6+b81',
  core_version: '1.3.2-asus6', web_version: '0.1.4', build: 81, notes: 'Recovery fixture',
  package: { family: 'aarch64-3.10', filename: 'nfqws2-asus_1.3.2-asus6+b81_aarch64-3.10.ipk', size: 1000, sha256: 'b'.repeat(64) },
};
const current = { state: 'current', candidate: null, code: null, installed_version: installed };
const available = { state: 'available', candidate, code: null, installed_version: installed };
const operation = { id: 'c'.repeat(32), revision: candidate.revision, state: 'prepared', package_version: candidate.package_version, code: null, service_intent: null };
const fixtures = new Map();
const failures = [];
let server, browser;

// The real hook, QueryClient, API parser, dialog and translations run in Chromium.
// Only the HTTP service is replaced; delayed replies model router contention.
try {
  await build({ stdin: { resolveDir: web, loader: 'tsx', contents: `
    import React, {useEffect, useState} from 'react';
    import {createRoot} from 'react-dom/client';
    import {QueryClient, QueryClientProvider} from '@tanstack/react-query';
    import {usePackageUpdates} from './src/hooks/usePackageUpdates';
    import {PackageUpdateDialog} from './src/components/PackageUpdateDialog';
    import {TranslationContext} from './src/context/TranslationContext';
    import ru from './src/translations/ru.json'; import en from './src/translations/en.json';
    const client = new QueryClient({defaultOptions:{queries:{retry:false,refetchOnWindowFocus:false}}});
    const pack = location.search.includes('en') ? en : ru;
    const t = (key, params={}) => (key.split('.').reduce((v,k)=>v?.[k],pack)||key).replace(/{{(\\w+)}}/g,(_,k)=>String(params[k]??''));
    function App() {
      const [csrf,setCsrf] = useState('session-a');
      const updates = usePackageUpdates(csrf,true,true);
      useEffect(()=>{window.fixture={
        refresh:()=>updates.refresh(true),
        refetch:()=>client.refetchQueries({queryKey:['package-update-overview',csrf],exact:true}),
        setCsrf,
      };});
      return <TranslationContext.Provider value={{t}}>
        <output id="snapshot">{JSON.stringify({pending:updates.pending,error:updates.error??null,data:updates.data??null})}</output>
        <PackageUpdateDialog open onClose={()=>{}} installed="${installed}" updates={updates}/>
      </TranslationContext.Provider>;
    }
    createRoot(document.getElementById('root')).render(<QueryClientProvider client={client}><App/></QueryClientProvider>);
  ` }, bundle: true, platform: 'browser', format: 'iife', jsx: 'automatic', outfile: join(directory, 'fixture.js'),
    tsconfig: join(web, 'tsconfig.app.json'), logLevel: 'silent', define: { 'process.env.APP_VERSION': '"0.1.4"' } });
  const js = await readFile(join(directory, 'fixture.js'));
  server = createServer(async (req, res) => {
    if (req.method !== 'POST') {
      res.setHeader('Content-Type', req.url.startsWith('/fixture.js') ? 'text/javascript' : 'text/html');
      res.end(req.url.startsWith('/fixture.js') ? js : '<!doctype html><html><body><div id="root"></div><script src="/fixture.js"></script></body></html>');
      return;
    }
    const fixture = fixtures.get(req.headers['x-fixture']);
    let raw = ''; for await (const chunk of req) raw += chunk;
    const params = new URLSearchParams(raw);
    const cmd = params.get('cmd');
    fixture.calls.push({ cmd, csrf: params.get('csrf_token'), force: params.get('force') });
    const respond = (value, status = 200) => {
      res.statusCode = status;
      res.setHeader('Content-Type', 'application/json');
      res.end(JSON.stringify(value));
    };
    if (cmd === 'packageupdatestatus') {
      if (fixture.holdStatus) { fixture.heldStatus.push(respond); return; }
      return respond(fixture.overview);
    }
    if (cmd === 'packageupdatecheck') {
      const count = fixture.calls.filter(call => call.cmd === cmd).length;
      if (fixture.check === 'busy' || (fixture.check === 'transient' && count === 1)) return respond({ error: 'busy' }, 409);
      if (fixture.check === 'held') { fixture.held.push({ csrf: params.get('csrf_token'), respond }); return; }
      fixture.overview = { ...fixture.overview, check: available };
      return respond(available);
    }
    if (cmd === 'packageupdateprepare' || cmd === 'packageupdateapply') {
      if (cmd === 'packageupdateapply') fixture.overview = { check: available, operation: { ...operation, state: 'applying' } };
      return respond({ error: 'request_failed' }, 503);
    }
    respond({ error: 'unexpected_command' }, 400);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  browser = await chromium.launch({ headless: true, ...(process.env.NFQWS_CHROMIUM_EXECUTABLE ? { executablePath: process.env.NFQWS_CHROMIUM_EXECUTABLE } : {}) });
  const snapshot = page => page.locator('#snapshot').textContent().then(JSON.parse);
  const waitFor = (page, expression) => page.waitForFunction(`(() => { const s=JSON.parse(document.getElementById('snapshot').textContent); return ${expression}; })()`);
  const count = (fixture, cmd) => fixture.calls.filter(call => call.cmd === cmd).length;
  const settleRequests = page => page.evaluate(() => new Promise(resolve => setTimeout(resolve, 100)));
  for (const lang of ['ru', 'en']) {
    const pack = JSON.parse(await readFile(join(web, `src/translations/${lang}.json`), 'utf8')).package_update;
    const run = async (name, fixture, test) => {
      fixture.calls = []; fixture.held = []; fixture.heldStatus = [];
      const id = `${lang}-${name}`;
      fixtures.set(id, fixture);
      const page = await browser.newPage({ extraHTTPHeaders: { 'x-fixture': id } });
      page.setDefaultTimeout(2500);
      const pageErrors = [];
      page.on('pageerror', error => pageErrors.push(error.message));
      await page.route('https://api.github.com/**', route => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));
      try {
        await page.goto(`http://127.0.0.1:${server.address().port}/?${lang}`);
        await page.waitForFunction(() => !!window.fixture);
        await test(page, fixture);
        assert.deepEqual(pageErrors, []);
        console.log(`PASS ${id}`);
      } catch (error) {
        failures.push(`${id}: ${error.message}`);
        console.error(`FAIL ${id}: ${error.message}`);
      } finally {
        for (const held of fixture.held) held.respond(current);
        for (const respond of fixture.heldStatus) respond(fixture.overview);
        await page.close();
      }
    };

    // Keeping a check error after a later successful status is the reported bug.
    await run('busy-status-recovery', { check: 'busy', overview: { check: { ...current, state: 'checking' }, operation: null } }, async (page, fixture) => {
      await page.getByText(pack.busy, { exact: true }).waitFor();
      await waitFor(page, '!s.pending');
      const checks = count(fixture, 'packageupdatecheck');
      fixture.overview = { check: available, operation: null };
      await page.evaluate(() => window.fixture.refetch());
      await waitFor(page, 's.data?.check.state === "available"');
      assert.equal((await snapshot(page)).error, null, 'a recovered overview must clear the obsolete check warning');
      assert.equal(await page.getByText(pack.busy, { exact: true }).count(), 0);
      assert.equal(await page.getByRole('button', { name: pack.check, exact: true }).isEnabled(), true);
      assert.equal(await page.getByRole('button', { name: pack.prepare, exact: true }).isEnabled(), true);
      assert.equal(count(fixture, 'packageupdatecheck'), checks, 'status recovery must not trigger another background check');
      assert.ok(checks <= 3, 'read-check busy retries must stop');
      assert.equal(count(fixture, 'packageupdateprepare') + count(fixture, 'packageupdateapply'), 0);
    });
    await run('transient-busy-retry', { check: 'transient', overview: { check: current, operation: null } }, async (page, fixture) => {
      await waitFor(page, 's.data?.check.state === "available" && !s.pending');
      assert.equal((await snapshot(page)).error, null);
      assert.equal(count(fixture, 'packageupdatecheck'), 2, 'a transient busy check should recover automatically with a bounded retry');
    });
    await run('coalesced-check', { check: 'held', overview: { check: current, operation: null } }, async (page, fixture) => {
      await waitFor(page, 's.pending && s.data');
      await page.evaluate(() => { void window.fixture.refresh(); void window.fixture.refresh(); });
      await settleRequests(page);
      assert.equal(count(fixture, 'packageupdatecheck'), 1, 'manual and automatic checks must share the in-flight request');
      fixture.held.splice(0).forEach(held => held.respond(available));
      await waitFor(page, 's.data?.check.state === "available" && !s.pending');
    });
    await run('manual-before-overview', { check: 'held', holdStatus: true, overview: { check: current, operation: null } }, async (page, fixture) => {
      await page.evaluate(() => { void window.fixture.refresh(); });
      await waitFor(page, 's.pending');
      await settleRequests(page);
      fixture.held.splice(0).forEach(held => held.respond(available));
      await waitFor(page, 's.data?.check.state === "available" && !s.pending');
      await settleRequests(page);
      assert.equal(count(fixture, 'packageupdatecheck'), 1, 'a manual check before the overview arrives must also satisfy the initial automatic check');
    });
    await run('newer-overview-wins', { check: 'held', overview: { check: current, operation: null } }, async (page, fixture) => {
      await waitFor(page, 's.pending && s.data');
      fixture.overview = { check: available, operation: null };
      await page.evaluate(() => window.fixture.refetch());
      await waitFor(page, 's.data?.check.state === "available"');
      fixture.held.splice(0).forEach(held => held.respond(current));
      await waitFor(page, '!s.pending');
      assert.equal((await snapshot(page)).data.check.candidate?.build, 81, 'a delayed check must not overwrite a newer overview');
    });
    await run('session-change', { check: 'held', overview: { check: current, operation: null } }, async (page, fixture) => {
      await waitFor(page, 's.pending && s.data');
      await page.evaluate(() => window.fixture.setCsrf('session-b'));
      await page.waitForFunction(() => document.querySelector('#snapshot').textContent.includes('"pending":true'));
      await settleRequests(page);
      assert.equal(fixture.held.filter(held => held.csrf === 'session-b').length, 1);
      fixture.held.splice(fixture.held.findIndex(held => held.csrf === 'session-a'), 1)[0].respond({ error: 'busy' }, 409);
      await settleRequests(page);
      assert.equal((await snapshot(page)).pending, true, 'the old session must not unlock the current session request');
      assert.equal((await snapshot(page)).error, null, 'the old session must not report its error in the new session');
      fixture.held.splice(0).forEach(held => held.respond(available));
      await waitFor(page, 's.data?.check.state === "available" && !s.pending');
      assert.equal(fixture.calls.filter(call => call.cmd === 'packageupdatecheck' && call.csrf === 'session-a').length, 1, 'session cleanup must stop old retries');
    });
    await run('older-overview-cannot-undo-check', { check: 'held', overview: { check: current, operation: null } }, async (page, fixture) => {
      await waitFor(page, 's.pending && s.data');
      fixture.holdStatus = true;
      await page.evaluate(() => { void window.fixture.refetch(); });
      await settleRequests(page);
      assert.equal(fixture.heldStatus.length, 1);
      fixture.held.splice(0).forEach(held => held.respond(available));
      await waitFor(page, 's.data?.check.state === "available" && !s.pending');
      fixture.heldStatus.splice(0).forEach(respond => respond({ check: current, operation: null }));
      await settleRequests(page);
      assert.equal((await snapshot(page)).data.check.candidate?.build, 81, 'a status request started before check completion must not undo its result');
    });
    for (const action of ['prepare', 'apply']) {
      await run(`${action}-failure-preserved`, { check: 'success', overview: { check: available, operation: action === 'apply' ? operation : null } }, async (page, fixture) => {
        await waitFor(page, 's.data?.check.state === "available" && !s.pending');
        await page.getByRole('button', { name: action === 'prepare' ? pack.prepare : pack.install, exact: true }).click();
        await page.getByText(pack.request_failed, { exact: true }).waitFor();
        await waitFor(page, '!s.pending');
        await page.evaluate(() => window.fixture.refetch());
        assert.equal((await snapshot(page)).error, 'request_failed', 'successful status must preserve an ambiguous mutation failure');
        const checks = count(fixture, 'packageupdatecheck');
        await page.evaluate(() => window.fixture.refresh());
        assert.equal((await snapshot(page)).error, 'request_failed', 'a background/read check must not erase a prepare/apply error');
        if (action === 'apply') assert.equal(count(fixture, 'packageupdatecheck'), checks, 'do not check the feed while installation is active');
        await settleRequests(page);
        assert.equal(count(fixture, `packageupdate${action}`), 1, 'never automatically replay an ambiguous mutation');
      });
    }
    await run('active-operation-status-only', { check: 'success', overview: { check: available, operation: { ...operation, state: 'applying' } } }, async (page, fixture) => {
      await waitFor(page, 's.data?.operation?.state === "applying" && !s.pending');
      await page.evaluate(() => window.fixture.refresh());
      await page.evaluate(() => window.fixture.refetch());
      assert.equal(count(fixture, 'packageupdatecheck'), 0, 'an active operation needs status polling without conflicting checks');
      assert.equal(await page.getByRole('button', { name: pack.check, exact: true }).isDisabled(), true);
      assert.equal(count(fixture, 'packageupdateapply') + count(fixture, 'packageupdateprepare'), 0);
    });
  }
  assert.deepEqual(failures, [], 'package update recovery browser regressions');
} finally {
  await browser?.close();
  if (server) await new Promise(resolve => server.close(resolve));
  await rm(directory, { recursive: true, force: true });
}

import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { mkdir, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from '../webui/web/node_modules/esbuild/lib/main.js';

const { chromium } = await import(process.env.NFQWS_PLAYWRIGHT_MODULE || 'playwright');
const web = fileURLToPath(new URL('../webui/web/', import.meta.url));
const locales = Object.fromEntries(await Promise.all(['ru', 'en'].map(async lang => [lang, JSON.parse(await readFile(join(web, `src/translations/${lang}.json`), 'utf8'))])));
const fixtures = new Map();
const failures = [];
let server, browser;
const schedule = (overrides = {}) => ({ enabled: false, interval_hours: 24, watchdog_enabled: false, watchdog_state: 'disabled', watchdog_attempts: 0, watchdog_next_seconds: null, scheduler_available: true, ...overrides });
const texts = {
  ru: { restart: 'Перезапустить NFQWS2', timer: 'Перезапуск по таймеру', description: 'Для устройств с небольшим объёмом ОЗУ', off: 'Выключено', custom: 'Свой интервал', hours: 'Интервал, ч', save: 'Сохранить', cancel: 'Отмена', close: 'Закрыть', retry: 'Повторить', invalid: 'Введите целое число часов от 1 до 168.', every: n => `Каждые ${n} ч`, busy: 'Панель занята другой операцией. Повторите сохранение позже.', failed: 'Не удалось перезапустить NFQWS2. Повторите действие.', watchdog: 'Восстанавливать службу', watchdogHelp: 'О восстановлении службы', watchdogTooltip: 'После сбоя — до трёх попыток с увеличением паузы. Затем восстановление остановится. Вручную остановленная служба не запустится.', locked: 'Автовосстановление остановлено после 3 попыток. Запустите NFQWS2 вручную, чтобы возобновить.' },
  en: { restart: 'Restart NFQWS2', timer: 'Scheduled restart', description: 'For devices with limited RAM', off: 'Off', custom: 'Custom interval', hours: 'Interval, hours', save: 'Save', cancel: 'Cancel', close: 'Close', retry: 'Retry', invalid: 'Enter a whole number of hours from 1 to 168.', every: n => `Every ${n} hours`, busy: 'The panel is busy with another operation. Try saving again later.', failed: 'Could not restart NFQWS2. Try again.', watchdog: 'Recover the service', watchdogHelp: 'About service recovery', watchdogTooltip: 'After a crash, try up to three times with increasing delays, then stop recovery. A manually stopped service stays stopped.', locked: 'Automatic recovery stopped after 3 attempts. Start NFQWS2 manually to resume.' },
};

// Render the real Header, API client, service output dialog, layout and locales.
// Only router HTTP responses are substituted; no UI/hook implementation is mocked.
try {
  const result = await build({ stdin: { resolveDir: web, loader: 'tsx', contents: `
    import React from 'react'; import {createRoot} from 'react-dom/client';
    import {QueryClientProvider} from '@tanstack/react-query';
    import {createRootRoute,createRouter,RouterProvider} from '@tanstack/react-router';
    import {queryClient,API} from './src/api/client';
    import {Header} from './src/components/Header'; import {Layout} from './src/components/Layout';
    import {LoginDialog} from './src/components/LoginDialog'; import {useAppStore} from './src/store/useAppStore';
    const Fixture=()=> { const {auth}=useAppStore(); return <Layout><Header/>{auth===false&&<LoginDialog/>}</Layout>; };
    const route=createRootRoute({component:Fixture});
    const router=createRouter({routeTree:route}); window.fixture={refresh:()=>API.invalidateStatus()};
    createRoot(document.getElementById('root')).render(<QueryClientProvider client={queryClient}><RouterProvider router={router}/></QueryClientProvider>);
  ` }, bundle: true, platform: 'browser', format: 'iife', write: false, jsx: 'automatic',
    tsconfig: join(web, 'tsconfig.app.json'), logLevel: 'silent', define: { 'process.env.APP_VERSION': '"0.1.4"' },
    plugins: process.env.NFQWS_RESTART_BASELINE_HEADER ? [{ name: 'baseline-header', setup(builder) {
      builder.onLoad({ filter: /\/components\/Header\.tsx$/ }, async () => ({ contents: await readFile(process.env.NFQWS_RESTART_BASELINE_HEADER, 'utf8'), loader: 'tsx', resolveDir: join(web, 'src/components') }));
    } }] : [],
  });
  server = createServer(async (req, res) => {
    if (req.method !== 'POST') {
      if (['/community/export-e9a226cd.png', '/community/import-937c2946.png'].includes(req.url)) {
        res.setHeader('Content-Type', 'image/png'); res.end(await readFile(join(web, 'public', req.url))); return;
      }
      res.setHeader('Content-Type', req.url.startsWith('/fixture.js') ? 'text/javascript' : 'text/html');
      res.end(req.url.startsWith('/fixture.js') ? result.outputFiles[0].contents : '<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"></head><body><div id="root"></div><script src="/fixture.js"></script></body></html>');
      return;
    }
    const fixture = fixtures.get(req.headers['x-fixture']);
    let raw = ''; for await (const chunk of req) raw += chunk;
    const params = req.headers['content-type']?.startsWith('multipart/form-data')
      ? new URLSearchParams([...await new Response(raw, { headers: { 'Content-Type': req.headers['content-type'] } }).formData()].map(([key, value]) => [key, String(value)]))
      : new URLSearchParams(raw);
    const cmd = params.get('cmd');
    fixture.calls.push(Object.fromEntries(params));
    const respond = (value, status = 200) => { res.statusCode = status; res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(value)); };
    if (cmd === 'status') {
      if (fixture.statusUnauthorized) { res.statusCode = 401; res.end(); return; }
      if (fixture.statusFailure) return respond({ status: 1 }, fixture.statusFailure);
      const finish = () => respond({ status: 0, platform: 'asus-entware', nfqws2: true, service: fixture.running ?? true, anonym: fixture.anonym ?? !fixture.auth, authenticated: fixture.auth, csrf_token: fixture.csrf, version: '1.3.2-asus6+b83', ark_loaded: false });
      if (fixture.holdStatus) { fixture.held.push({ cmd, respond: finish }); return; }
      return finish();
    }
    if (cmd === 'login') {
      if (fixture.loginFailures) { fixture.loginFailures--; return respond({ error: 'auth_required' }, 401); }
      const finish = () => {
        fixture.auth = true; fixture.csrf = 'session-b'; fixture.readUnauthorized = false; fixture.saveUnauthorized = false; fixture.statusUnauthorized = false;
        respond({ status: 0 });
      };
      if (fixture.holdLogin) { fixture.held.push({ cmd, respond: finish }); return; }
      return finish();
    }
    if (cmd === 'packageupdatestatus') return respond({ check: { state: 'current', candidate: null, code: null, installed_version: '1.3.2-asus6+b81' }, operation: null });
    if (cmd === 'restartschedule') {
      if (fixture.readUnauthorized) { res.statusCode = 401; res.end(); return; }
      if (fixture.holdRead) { fixture.held.push({ cmd, csrf: params.get('csrf_token'), respond }); return; }
      if (fixture.readError) return respond({ error: 'invalid_state' }, 503);
      return respond(fixture.schedule);
    }
    if (cmd === 'restartschedulesave') {
      if (fixture.saveUnauthorized) { res.statusCode = typeof fixture.saveUnauthorized === 'number' ? fixture.saveUnauthorized : 403; res.end(); return; }
      if (fixture.holdSave) { fixture.held.push({ cmd, respond }); return; }
      if (fixture.saveError) return respond({ error: fixture.saveError }, fixture.saveError === 'busy' ? 409 : 503);
      if (fixture.schedule.scheduler_available === false && (params.get('enabled') === '1' || params.get('watchdog_enabled') === '1')) return respond({ error: 'unsupported_scheduler' }, 503);
      fixture.schedule = schedule({ enabled: params.get('enabled') === '1', interval_hours: Number(params.get('interval_hours')), watchdog_enabled: params.get('watchdog_enabled') === '1', watchdog_state: params.get('watchdog_enabled') === '1' ? 'ready' : 'disabled', scheduler_available: fixture.schedule.scheduler_available });
      return respond(fixture.schedule);
    }
    if (cmd === 'start' || cmd === 'stop') {
      fixture.running = cmd === 'start';
      return respond({ status: 0, output: ['Done'] });
    }
    if (cmd === 'restart') {
      if (fixture.holdRestart) { fixture.held.push({ cmd, respond }); return; }
      if (fixture.restartError) return respond({ code: 'error', detail: 'fixture error' }, 503);
      return respond({ status: 0, output: ['Restarting NFQWS2', 'Done'] });
    }
    respond({ error: 'unexpected_command' }, 400);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  browser = await chromium.launch({ headless: true, ...(process.env.NFQWS_CHROMIUM_EXECUTABLE ? { executablePath: process.env.NFQWS_CHROMIUM_EXECUTABLE } : {}) });
  const count = (f, cmd) => f.calls.filter(call => call.cmd === cmd).length;
  const settle = page => page.evaluate(() => new Promise(resolve => setTimeout(resolve, 80)));
  for (const lang of ['ru', 'en']) {
    const p = { ...texts[lang], session: locales[lang].restart_schedule.session, csrf: locales[lang].restart_schedule.csrf, recover: locales[lang].restart_schedule.recover ?? 'Refresh session', ...locales[lang].auth };
    const run = async (name, settings, test) => {
      if (process.env.NFQWS_RESTART_CASE_FILTER && !`${lang}-${name}`.includes(process.env.NFQWS_RESTART_CASE_FILTER)) return;
      const fixture = { auth: true, csrf: 'session-a', schedule: schedule(), calls: [], held: [], ...settings };
      const id = `${lang}-${name}`; fixtures.set(id, fixture);
      const page = await browser.newPage({ viewport: { width: 1280, height: 800 }, extraHTTPHeaders: { 'x-fixture': id } });
      page.setDefaultTimeout(1800);
      await page.addInitScript(lang => localStorage.setItem('lang', JSON.stringify(lang)), lang);
      const errors = []; page.on('pageerror', error => errors.push(error.message));
      try {
        await page.goto(`http://127.0.0.1:${server.address().port}/`);
        await page.getByRole('heading', { name: 'NFQWS 2', exact: true }).waitFor();
        await test(page, fixture);
        assert.deepEqual(errors, []);
        console.log(`PASS ${id}`);
      } catch (error) { failures.push(`${id}: ${error.message}`); console.error(`FAIL ${id}: ${error.message}`); if (process.env.NFQWS_RESTART_DEBUG) console.error(JSON.stringify({ calls: fixture.calls, errors, body: await page.locator('body').innerText() })); }
      finally { fixture.held.splice(0).forEach(held => held.respond(schedule())); await page.close(); }
    };
    const open = async page => {
      await page.getByRole('button', { name: p.timer, exact: true }).click();
      const dialog = page.getByRole('dialog', { name: p.timer });
      await dialog.getByRole('radio', { name: p.off, exact: true }).waitFor();
      await page.waitForFunction(() => !document.querySelector('[role="dialog"] [role="progressbar"]'));
      return dialog;
    };
    await run('presets-explicit-save', {}, async (page, f) => {
      await page.getByRole('button', { name: p.restart, exact: true }).waitFor();
      const timer = page.getByRole('button', { name: p.timer, exact: true });
      await timer.hover(); await page.getByRole('tooltip', { name: p.timer }).waitFor();
      let dialog = await open(page);
      assert.equal(await dialog.getByRole('radio', { name: p.off, exact: true }).isChecked(), true);
      await dialog.getByText(p.description, { exact: true }).waitFor();
      for (const h of [4, 12, 24]) {
        await dialog.getByRole('radio', { name: p.every(h), exact: true }).check();
        assert.equal(count(f, 'restartschedulesave'), 0, 'changing the selection must not write settings');
      }
      await dialog.getByRole('button', { name: p.cancel, exact: true }).click();
      assert.equal(count(f, 'restartschedulesave'), 0);
      dialog = await open(page);
      assert.equal(await dialog.getByRole('radio', { name: p.off, exact: true }).isChecked(), true, 'cancel discards the local draft');
      for (const h of [4, 12, 24]) {
        await dialog.getByRole('radio', { name: p.every(h), exact: true }).check();
        await dialog.getByRole('button', { name: p.save, exact: true }).click();
        await dialog.waitFor({ state: 'hidden' });
        assert.deepEqual(f.calls.filter(call => call.cmd === 'restartschedulesave').at(-1), { cmd: 'restartschedulesave', csrf_token: 'session-a', enabled: '1', interval_hours: String(h), watchdog_enabled: '0' });
        dialog = await open(page);
        assert.equal(await dialog.getByRole('radio', { name: p.every(h), exact: true }).isChecked(), true);
      }
      await dialog.getByRole('radio', { name: p.off, exact: true }).check();
      await dialog.getByRole('button', { name: p.save, exact: true }).click();
      await dialog.waitFor({ state: 'hidden' });
      assert.deepEqual(f.schedule, schedule());
    });
    await run('custom-validation-save-error-pending', {}, async (page, f) => {
      const dialog = await open(page);
      await dialog.getByRole('radio', { name: p.custom, exact: true }).check();
      const input = dialog.getByRole('spinbutton', { name: p.hours, exact: true });
      for (const invalid of ['', '0', '-1', '1.5', '169']) {
        await input.fill(invalid);
        assert.equal(await dialog.getByRole('button', { name: p.save, exact: true }).isDisabled(), true);
        await dialog.getByText(p.invalid, { exact: true }).waitFor();
      }
      for (const boundary of ['1', '168']) {
        await input.fill(boundary);
        assert.equal(await dialog.getByRole('button', { name: p.save, exact: true }).isEnabled(), true);
      }
      await input.fill('7'); f.saveError = 'busy';
      await dialog.getByRole('button', { name: p.save, exact: true }).click();
      await dialog.getByText(p.busy, { exact: true }).waitFor();
      assert.equal(await input.inputValue(), '7', 'saving errors must preserve the selected interval');
      assert.equal(count(f, 'restartschedulesave'), 1, 'failed writes are never retried automatically');
      f.saveError = null; f.holdSave = true;
      await dialog.getByRole('button', { name: p.save, exact: true }).click();
      await page.waitForFunction(() => document.querySelector('[role="dialog"] [role="progressbar"]'));
      await dialog.getByRole('button', { name: p.save, exact: true }).evaluate(button => { button.click(); button.click(); });
      await settle(page); assert.equal(count(f, 'restartschedulesave'), 2, 'pending save must coalesce repeated clicks');
      assert.equal(await input.isDisabled(), true);
      assert.equal(await dialog.getByRole('button', { name: p.cancel, exact: true }).isDisabled(), true, 'an active Save mutation must still prevent dismissal');
      await page.keyboard.press('Escape'); await settle(page);
      assert.equal(await dialog.isVisible(), true, 'Escape must not dismiss an active Save mutation');
      f.schedule = schedule({ enabled: true, interval_hours: 7 }); f.held.splice(0).forEach(held => held.respond(f.schedule));
      await dialog.waitFor({ state: 'hidden' });
      f.holdSave = false;
      const reopened = await open(page);
      assert.equal(await reopened.getByRole('radio', { name: p.custom, exact: true }).isChecked(), true);
      assert.equal(await reopened.getByRole('spinbutton', { name: p.hours, exact: true }).inputValue(), '7');
    });
    await run('read-error-and-session-change', { readError: true }, async (page, f) => {
      let dialog = await open(page);
      assert.equal(await dialog.getByRole('button', { name: p.save, exact: true }).isDisabled(), true);
      f.readError = false; f.holdRead = true;
      await dialog.getByRole('button', { name: p.retry, exact: true }).click();
      f.csrf = 'session-b'; await page.evaluate(() => window.fixture.refresh());
      await settle(page);
      assert.equal(f.held.filter(held => held.csrf === 'session-b').length, 1, 'session changes must load settings under the new token');
      f.held.filter(held => held.csrf === 'session-b').forEach(held => held.respond(schedule({ enabled: true, interval_hours: 12 })));
      f.held = f.held.filter(held => held.csrf !== 'session-b');
      dialog = page.getByRole('dialog', { name: p.timer });
      await dialog.getByRole('radio', { name: p.every(12), exact: true }).waitFor();
      f.held.splice(0).forEach(held => held.respond(schedule()));
      await settle(page);
      assert.equal(await dialog.getByRole('radio', { name: p.every(12), exact: true }).isChecked(), true, 'old session replies must not replace current choices');
      assert.equal(count(f, 'restartschedulesave'), 0);
    });
    await run('session-recovery-held-status-cancel', {}, async (page, f) => {
      const dialog = await open(page);
      await dialog.getByRole('radio', { name: p.custom, exact: true }).check();
      await dialog.getByRole('spinbutton', { name: p.hours, exact: true }).fill('7');
      f.saveUnauthorized = 403;
      await dialog.getByRole('button', { name: p.save, exact: true }).click();
      f.holdStatus = true;
      const sent = page.waitForRequest(request => request.postData()?.includes('name="cmd"\r\n\r\nstatus\r\n'));
      await dialog.getByRole('button', { name: p.recover, exact: true }).click();
      await sent; await settle(page);
      assert.equal(await dialog.getByRole('button', { name: p.cancel, exact: true }).isEnabled(), true, 'a stalled session read must not trap the timer modal');
      await dialog.getByRole('button', { name: p.cancel, exact: true }).click();
      await dialog.waitFor({ state: 'hidden' });
      const reads = count(f, 'restartschedule');
      f.holdStatus = false; f.csrf = 'session-b';
      f.held.splice(f.held.findIndex(held => held.cmd === 'status'), 1)[0].respond();
      await settle(page);
      assert.equal(await page.getByRole('dialog').count(), 0, 'a late status response cannot reopen the dismissed dialog');
      assert.equal(count(f, 'restartschedule'), reads, 'a dismissed recovery cannot continue its schedule read');
      assert.equal(count(f, 'restartschedulesave'), 1, 'cancel and the late response must not replay Save');
    });
    await run('session-recovery-held-local-login-cancel', {}, async (page, f) => {
      const dialog = await open(page);
      await dialog.getByRole('radio', { name: p.custom, exact: true }).check();
      await dialog.getByRole('spinbutton', { name: p.hours, exact: true }).fill('7');
      f.auth = false; f.anonym = false; f.saveUnauthorized = 401;
      await dialog.getByRole('button', { name: p.save, exact: true }).click();
      await dialog.getByRole('button', { name: p.recover, exact: true }).click();
      const login = page.getByRole('dialog').filter({ has: page.getByLabel(p.password, { exact: true }) });
      await login.getByRole('textbox', { name: p.username, exact: true }).fill('fixture-user');
      await login.getByLabel(p.password, { exact: true }).fill('fixture-password');
      f.holdLogin = true;
      const sent = page.waitForRequest(request => request.postData()?.includes('name="cmd"\r\n\r\nlogin\r\n'));
      await login.getByRole('button', { name: p.login, exact: true }).click();
      await sent; await settle(page);
      assert.equal(await login.getByRole('button', { name: p.cancel, exact: true }).isEnabled(), true, 'a stalled local sign-in must remain cancellable');
      await login.getByRole('button', { name: p.cancel, exact: true }).click();
      await login.waitFor({ state: 'hidden' });
      assert.equal(await dialog.getByRole('spinbutton', { name: p.hours, exact: true }).inputValue(), '7', 'canceling sign-in preserves the timer draft');
      await dialog.getByRole('button', { name: p.cancel, exact: true }).click();
      await dialog.waitFor({ state: 'hidden' });
      const statuses = count(f, 'status'), reads = count(f, 'restartschedule');
      f.holdLogin = false;
      f.held.splice(f.held.findIndex(held => held.cmd === 'login'), 1)[0].respond();
      await settle(page);
      assert.equal(await page.getByRole('dialog').count(), 0, 'late sign-in success cannot reopen either dismissed dialog');
      assert.equal(count(f, 'status'), statuses, 'an unmounted sign-in must not invoke its recovery callback');
      assert.equal(count(f, 'restartschedule'), reads);
      assert.equal(count(f, 'restartschedulesave'), 1, 'late sign-in success must not replay Save');
    });
    await run('session-recovery-expired-save-keeps-draft', {}, async (page, f) => {
      const dialog = await open(page);
      await dialog.getByRole('radio', { name: p.custom, exact: true }).check();
      await dialog.getByRole('spinbutton', { name: p.hours, exact: true }).fill('7');
      await dialog.getByRole('switch', { name: p.watchdog, exact: true }).check();
      f.auth = false; f.anonym = false; f.saveUnauthorized = 401;
      await dialog.getByRole('button', { name: p.save, exact: true }).click();
      await dialog.getByRole('button', { name: p.recover, exact: true }).click();
      await page.getByRole('textbox', { name: p.username, exact: true }).fill('fixture-user');
      await page.getByLabel(p.password, { exact: true }).fill('fixture-password');
      await page.getByRole('button', { name: p.login, exact: true }).click();
      await page.getByLabel(p.password, { exact: true }).waitFor({ state: 'hidden' });
      assert.equal(await dialog.getByRole('spinbutton', { name: p.hours, exact: true }).inputValue(), '7');
      assert.equal(await dialog.getByRole('switch', { name: p.watchdog, exact: true }).isChecked(), true);
      assert.equal(count(f, 'restartschedulesave'), 1, 'sign-in must not replay the failed save');
      assert.ok(f.calls.slice(f.calls.findIndex(call => call.cmd === 'login') + 1).filter(call => call.cmd === 'restartschedule').every(call => call.csrf_token === 'session-b'), 'post-login reads must use the refreshed token');
      await dialog.getByRole('button', { name: p.save, exact: true }).click();
      await dialog.waitFor({ state: 'hidden' });
      assert.deepEqual(f.calls.filter(call => call.cmd === 'restartschedulesave').at(-1), { cmd: 'restartschedulesave', csrf_token: 'session-b', enabled: '1', interval_hours: '7', watchdog_enabled: '1' });
    });
    await run('session-recovery-rotated-token-keeps-draft', {}, async (page, f) => {
      const dialog = await open(page);
      await dialog.getByRole('radio', { name: p.custom, exact: true }).check();
      await dialog.getByRole('spinbutton', { name: p.hours, exact: true }).fill('7');
      await dialog.getByRole('switch', { name: p.watchdog, exact: true }).check();
      f.saveUnauthorized = 403; f.csrf = 'session-b';
      await dialog.getByRole('button', { name: p.save, exact: true }).click();
      await dialog.getByRole('button', { name: p.recover, exact: true }).click();
      await settle(page);
      assert.equal(await page.getByLabel(p.password, { exact: true }).count(), 0, 'a rotated CSRF token does not require another login');
      assert.equal(await dialog.getByRole('spinbutton', { name: p.hours, exact: true }).inputValue(), '7');
      assert.equal(await dialog.getByRole('switch', { name: p.watchdog, exact: true }).isChecked(), true);
      assert.equal(count(f, 'restartschedulesave'), 1, 'refreshing a token must not replay the failed save');
      f.saveUnauthorized = false;
      await dialog.getByRole('button', { name: p.save, exact: true }).click();
      await dialog.waitFor({ state: 'hidden' });
      assert.equal(f.calls.filter(call => call.cmd === 'restartschedulesave').at(-1).csrf_token, 'session-b');
    });
    await run('session-refresh-read-cannot-overwrite-dirty-draft', {}, async (page, f) => {
      const dialog = await open(page);
      await dialog.getByRole('radio', { name: p.custom, exact: true }).check();
      await dialog.getByRole('spinbutton', { name: p.hours, exact: true }).fill('7');
      await dialog.getByRole('switch', { name: p.watchdog, exact: true }).check();
      f.holdRead = true; f.csrf = 'session-b';
      await page.evaluate(() => window.fixture.refresh());
      await settle(page);
      f.held.splice(0).forEach(held => held.respond(schedule({ enabled: true, interval_hours: 12 })));
      await settle(page);
      assert.equal(await dialog.getByRole('spinbutton', { name: p.hours, exact: true }).inputValue(), '7', 'fresh server metadata must not replace a dirty draft');
      assert.equal(await dialog.getByRole('switch', { name: p.watchdog, exact: true }).isChecked(), true);
      assert.equal(count(f, 'restartschedulesave'), 0);
    });
    await run('session-recovery-global-login-keeps-draft', {}, async (page, f) => {
      const dialog = await open(page);
      await dialog.getByRole('radio', { name: p.custom, exact: true }).check();
      await dialog.getByRole('spinbutton', { name: p.hours, exact: true }).fill('7');
      await dialog.getByRole('switch', { name: p.watchdog, exact: true }).check();
      f.saveUnauthorized = 401; f.statusUnauthorized = true;
      await dialog.getByRole('button', { name: p.save, exact: true }).click();
      await dialog.getByRole('button', { name: p.recover, exact: true }).click();
      await page.getByRole('textbox', { name: p.username, exact: true }).fill('fixture-user');
      assert.equal(await page.getByLabel(p.password, { exact: true }).count(), 1, 'the existing global login must not compete with a second modal');
      await page.getByLabel(p.password, { exact: true }).fill('fixture-password');
      await page.getByRole('button', { name: p.login, exact: true }).click();
      await page.getByLabel(p.password, { exact: true }).waitFor({ state: 'hidden' });
      assert.equal(await dialog.getByRole('spinbutton', { name: p.hours, exact: true }).inputValue(), '7');
      assert.equal(await dialog.getByRole('switch', { name: p.watchdog, exact: true }).isChecked(), true);
      assert.equal(count(f, 'restartschedulesave'), 1);
      await dialog.getByRole('button', { name: p.save, exact: true }).click();
      await dialog.waitFor({ state: 'hidden' });
      assert.equal(f.calls.filter(call => call.cmd === 'restartschedulesave').at(-1).csrf_token, 'session-b');
    });
    await run('session-recovery-rejected-login-hands-off-once', {}, async (page, f) => {
      const dialog = await open(page);
      await dialog.getByRole('radio', { name: p.custom, exact: true }).check();
      await dialog.getByRole('spinbutton', { name: p.hours, exact: true }).fill('7');
      await dialog.getByRole('switch', { name: p.watchdog, exact: true }).check();
      f.auth = false; f.anonym = false; f.saveUnauthorized = 401; f.loginFailures = 1;
      await dialog.getByRole('button', { name: p.save, exact: true }).click();
      await dialog.getByRole('button', { name: p.recover, exact: true }).click();
      await page.getByRole('textbox', { name: p.username, exact: true }).fill('fixture-user');
      await page.getByLabel(p.password, { exact: true }).fill('incorrect-fixture-password');
      await page.getByRole('button', { name: p.login, exact: true }).click();
      await settle(page);
      assert.equal(await page.getByLabel(p.password, { exact: true }).count(), 1);
      await page.getByRole('textbox', { name: p.username, exact: true }).fill('fixture-user');
      await page.getByLabel(p.password, { exact: true }).fill('fixture-password');
      await page.getByRole('button', { name: p.login, exact: true }).click();
      await page.getByLabel(p.password, { exact: true }).waitFor({ state: 'hidden' });
      assert.equal(await dialog.getByRole('spinbutton', { name: p.hours, exact: true }).inputValue(), '7');
      assert.equal(await dialog.getByRole('switch', { name: p.watchdog, exact: true }).isChecked(), true);
      assert.equal(count(f, 'restartschedulesave'), 1);
    });
    await run('session-refresh-old-save-cannot-close-draft', {}, async (page, f) => {
      const dialog = await open(page);
      await dialog.getByRole('radio', { name: p.custom, exact: true }).check();
      await dialog.getByRole('spinbutton', { name: p.hours, exact: true }).fill('7');
      await dialog.getByRole('switch', { name: p.watchdog, exact: true }).check();
      f.holdSave = true;
      await dialog.getByRole('button', { name: p.save, exact: true }).click();
      await settle(page);
      f.csrf = 'session-b'; await page.evaluate(() => window.fixture.refresh());
      await settle(page);
      f.held.splice(0).forEach(held => held.respond(schedule({ enabled: true, interval_hours: 12 })));
      await settle(page);
      assert.equal(await dialog.isVisible(), true, 'a success from the old token must not close the current draft');
      assert.equal(await dialog.getByRole('spinbutton', { name: p.hours, exact: true }).inputValue(), '7');
      assert.equal(await dialog.getByRole('switch', { name: p.watchdog, exact: true }).isChecked(), true);
      assert.equal(count(f, 'restartschedulesave'), 1);
      f.holdSave = false;
      await dialog.getByRole('button', { name: p.save, exact: true }).click();
      await dialog.waitFor({ state: 'hidden' });
      assert.equal(f.calls.filter(call => call.cmd === 'restartschedulesave').at(-1).csrf_token, 'session-b');
    });
    await run('watchdog-explicit-save-and-locked-state', {}, async (page, f) => {
      let dialog = await open(page);
      let watchdog = dialog.getByRole('switch', { name: p.watchdog, exact: true });
      assert.equal(await watchdog.isChecked(), false, 'service recovery must be disabled by default');
      await dialog.getByRole('button', { name: p.watchdogHelp, exact: true }).hover();
      await page.getByRole('tooltip', { name: p.watchdogTooltip, exact: true }).waitFor();
      if (process.env.NFQWS_RESTART_PREVIEW_DIR) await page.screenshot({ path: join(process.env.NFQWS_RESTART_PREVIEW_DIR, `${lang}-watchdog-help.png`), animations: 'disabled' });
      await watchdog.check();
      assert.equal(count(f, 'restartschedulesave'), 0, 'toggling recovery must not autosave');
      f.saveError = 'busy';
      await dialog.getByRole('button', { name: p.save, exact: true }).click();
      await dialog.getByText(p.busy, { exact: true }).waitFor();
      assert.equal(await watchdog.isChecked(), true, 'failed writes preserve recovery choice');
      assert.deepEqual(f.calls.filter(call => call.cmd === 'restartschedulesave').at(-1), { cmd: 'restartschedulesave', csrf_token: 'session-a', enabled: '0', interval_hours: '24', watchdog_enabled: '1' });
      f.saveError = null;
      await dialog.getByRole('button', { name: p.save, exact: true }).click();
      await dialog.waitFor({ state: 'hidden' });
      f.schedule = schedule({ watchdog_enabled: true, watchdog_state: 'locked', watchdog_attempts: 3 });
      dialog = await open(page);
      await dialog.getByText(p.locked, { exact: true }).waitFor();
      if (process.env.NFQWS_RESTART_PREVIEW_DIR) await page.screenshot({ path: join(process.env.NFQWS_RESTART_PREVIEW_DIR, `${lang}-watchdog-locked.png`), animations: 'disabled' });
      watchdog = dialog.getByRole('switch', { name: p.watchdog, exact: true });
      assert.equal(await watchdog.isChecked(), true);
      await watchdog.uncheck();
      await dialog.getByRole('button', { name: p.save, exact: true }).click();
      await dialog.waitFor({ state: 'hidden' });
      assert.deepEqual(f.schedule, schedule(), 'explicitly saving recovery OFF disables it');
    });
    await run('off-does-not-submit-invalid-custom-draft', { schedule: schedule({ enabled: true, interval_hours: 12 }) }, async (page, f) => {
      const dialog = await open(page);
      await dialog.getByRole('radio', { name: p.custom, exact: true }).check();
      await dialog.getByRole('spinbutton', { name: p.hours, exact: true }).fill('');
      await dialog.getByRole('radio', { name: p.off, exact: true }).check();
      await dialog.getByRole('button', { name: p.save, exact: true }).click();
      await dialog.waitFor({ state: 'hidden' });
      assert.deepEqual(f.calls.filter(call => call.cmd === 'restartschedulesave').at(-1), { cmd: 'restartschedulesave', csrf_token: 'session-a', enabled: '0', interval_hours: '12', watchdog_enabled: '0' }, 'turning the timer OFF preserves its last valid saved interval');
    });
    await run('scheduler-unavailable-allows-off', { schedule: schedule({ enabled: true, interval_hours: 12, watchdog_enabled: true, watchdog_state: 'ready', scheduler_available: false }) }, async (page, f) => {
      let dialog = await open(page);
      const warning = lang === 'ru' ? 'Планировщик недоступен. Можно отключить таймер и восстановление.' : 'The scheduler is unavailable. You can turn off the timer and recovery.';
      await dialog.getByText(warning, { exact: true }).waitFor();
      assert.equal(await dialog.getByRole('radio', { name: p.every(12), exact: true }).isChecked(), true);
      assert.equal(await dialog.getByRole('switch', { name: p.watchdog, exact: true }).isChecked(), true);
      await dialog.getByRole('radio', { name: p.off, exact: true }).check();
      await dialog.getByRole('switch', { name: p.watchdog, exact: true }).uncheck();
      await dialog.getByRole('button', { name: p.save, exact: true }).click();
      await dialog.waitFor({ state: 'hidden' });
      assert.deepEqual(f.calls.filter(call => call.cmd === 'restartschedulesave').at(-1), { cmd: 'restartschedulesave', csrf_token: 'session-a', enabled: '0', interval_hours: '12', watchdog_enabled: '0' });
      assert.equal(f.schedule.enabled || f.schedule.watchdog_enabled, false);
      dialog = await open(page);
      await dialog.getByRole('radio', { name: p.every(4), exact: true }).check();
      await dialog.getByRole('button', { name: p.save, exact: true }).click();
      await dialog.getByText(lang === 'ru' ? 'На устройстве недоступен планировщик. Перезапуск по таймеру не включён.' : 'A scheduler is unavailable on this device. Scheduled restart was not enabled.', { exact: true }).waitFor();
      assert.equal(await dialog.getByRole('radio', { name: p.every(4), exact: true }).isChecked(), true);
      assert.equal(f.schedule.enabled || f.schedule.watchdog_enabled, false, 'failed enabling must leave both saved features OFF');
      if (process.env.NFQWS_RESTART_PREVIEW_DIR) await page.screenshot({ path: join(process.env.NFQWS_RESTART_PREVIEW_DIR, `${lang}-scheduler-unavailable.png`), animations: 'disabled' });
    });
    await run('scheduler-field-optional-for-compatibility', { schedule: schedule({ scheduler_available: undefined }) }, async page => {
      const dialog = await open(page);
      assert.equal(await dialog.getByRole('button', { name: p.save, exact: true }).isEnabled(), true);
      assert.equal(await dialog.getByRole('radio', { name: p.off, exact: true }).isChecked(), true);
    });
    for (const stage of ['read', 'save']) {
      await run(`empty-auth-response-${stage}`, { readUnauthorized: stage === 'read' }, async (page, f) => {
        const dialog = await open(page);
        if (stage === 'save') {
          await dialog.getByRole('radio', { name: p.every(4), exact: true }).check();
          f.saveUnauthorized = true;
          await dialog.getByRole('button', { name: p.save, exact: true }).click();
        }
        await dialog.getByText(stage === 'read' ? p.session : p.csrf, { exact: true }).waitFor();
        assert.equal(count(f, 'restartschedulesave'), stage === 'save' ? 1 : 0, 'auth failures must never replay writes');
        if (stage === 'save') assert.equal(await dialog.getByRole('radio', { name: p.every(4), exact: true }).isChecked(), true, 'session errors preserve the failed draft');
        else assert.equal(await dialog.getByRole('button', { name: p.save, exact: true }).isDisabled(), true);
      });
    }
    await run('manual-restart-single-request-and-error', { holdRestart: true }, async (page, f) => {
      const restart = page.getByRole('button', { name: p.restart, exact: true });
      await restart.click();
      await page.getByRole('dialog').getByRole('button', { name: p.close, exact: true }).click();
      assert.equal(await restart.isDisabled(), true);
      await restart.evaluate(button => { button.click(); button.click(); });
      await settle(page); assert.equal(count(f, 'restart'), 1);
      f.held.splice(0).forEach(held => held.respond({ status: 0, output: ['Restarting NFQWS2', 'Done'] }));
      await page.getByText('Done', { exact: true }).waitFor();
      await page.getByRole('dialog').getByRole('button', { name: p.close, exact: true }).click();
      f.holdRestart = false; f.restartError = true;
      await restart.click(); await page.getByText(p.failed, { exact: true }).waitFor();
      assert.equal(count(f, 'restart'), 2);
    });
    await run('auth-and-stopped', { auth: false }, async (page, f) => {
      await settle(page);
      assert.equal(await page.getByRole('button', { name: p.timer, exact: true }).isEnabled(), true, 'a password-free panel can configure the timer using its CSRF session');
      assert.equal(await page.getByRole('button', { name: p.restart, exact: true }).isEnabled(), true, 'basic service restart remains available when the panel intentionally has no password');
      assert.equal(count(f, 'restartschedule') + count(f, 'restartschedulesave'), 0);
      f.auth = true; f.running = false;
      await page.evaluate(() => window.fixture.refresh());
      await page.getByRole('button', { name: p.timer, exact: true }).waitFor();
      assert.equal(await page.getByRole('button', { name: p.restart, exact: true }).isDisabled(), true);
    });
    await run('anonymous-basic-service-controls', { auth: false, running: false }, async (page, f) => {
      const common = locales[lang].common;
      const menu = () => page.getByRole('button', { name: locales[lang].restart_schedule.menu, exact: true });
      for (const width of [1280, 360]) {
        await page.setViewportSize({ width, height: 800 });
        await menu().click();
        await page.getByRole('menuitem', { name: common.start, exact: true }).click();
        await page.getByText('Done', { exact: true }).waitFor();
        await page.getByRole('dialog').getByRole('button', { name: p.close, exact: true }).click();
        await page.waitForFunction(label => [...document.querySelectorAll('button')].some(b => b.getAttribute('aria-label') === label && !b.disabled), p.restart);
        const starts = count(f, 'start');
        assert.equal(starts, width === 1280 ? 1 : 2, 'Start dispatches exactly once in the anonymous mode allowed by the router');
        await page.getByRole('button', { name: p.restart, exact: true }).click();
        await page.getByText('Done', { exact: true }).waitFor();
        await page.getByRole('dialog').getByRole('button', { name: p.close, exact: true }).click();
        await menu().click();
        await page.getByRole('menuitem', { name: common.stop, exact: true }).click();
        await page.getByText('Done', { exact: true }).waitFor();
        await page.getByRole('dialog').getByRole('button', { name: p.close, exact: true }).click();
        await page.waitForFunction(label => [...document.querySelectorAll('button')].some(b => b.getAttribute('aria-label') === label && b.disabled), p.restart);
        assert.equal(await page.getByRole('button', { name: p.timer, exact: true }).isEnabled(), true);
      }
      assert.equal(count(f, 'stop'), 2);
      assert.equal(count(f, 'restart'), 2);
      assert.equal(count(f, 'restartschedule') + count(f, 'restartschedulesave'), 0);
    });
    await run('anonymous-timer-watchdog-explicit-save', { auth: false, running: false }, async (page, f) => {
      const dialog = await open(page);
      await dialog.getByRole('radio', { name: p.every(4), exact: true }).check();
      await dialog.getByRole('switch', { name: p.watchdog, exact: true }).check();
      assert.equal(count(f, 'restartschedulesave'), 0);
      await dialog.getByRole('button', { name: p.save, exact: true }).click();
      await dialog.waitFor({ state: 'hidden' });
      assert.deepEqual(f.calls.filter(call => call.cmd === 'restartschedulesave').at(-1), { cmd: 'restartschedulesave', csrf_token: 'session-a', enabled: '1', interval_hours: '4', watchdog_enabled: '1' });
      const reopened = await open(page);
      assert.equal(await reopened.getByRole('radio', { name: p.every(4), exact: true }).isChecked(), true);
      assert.equal(await reopened.getByRole('switch', { name: p.watchdog, exact: true }).isChecked(), true);
      await reopened.getByRole('radio', { name: p.off, exact: true }).check();
      await reopened.getByRole('switch', { name: p.watchdog, exact: true }).uncheck();
      await reopened.getByRole('button', { name: p.save, exact: true }).click();
      await reopened.waitFor({ state: 'hidden' });
      assert.deepEqual(f.schedule, schedule({ interval_hours: 4 }));
      assert.equal(count(f, 'login'), 0, 'intentional anonymous mode never asks for an unnecessary password');
      assert.equal(count(f, 'start') + count(f, 'restart'), 0, 'saving a schedule never starts a stopped service');
    });
    await run('anonymous-timer-refreshes-csrf-without-login', { auth: false }, async (page, f) => {
      const dialog = await open(page);
      await dialog.getByRole('radio', { name: p.custom, exact: true }).check();
      await dialog.getByRole('spinbutton', { name: p.hours, exact: true }).fill('7');
      await dialog.getByRole('switch', { name: p.watchdog, exact: true }).check();
      f.saveUnauthorized = 403;
      await dialog.getByRole('button', { name: p.save, exact: true }).click();
      await dialog.getByText(p.csrf, { exact: true }).waitFor();
      f.saveUnauthorized = false; f.csrf = 'anonymous-b';
      await dialog.getByRole('button', { name: p.recover, exact: true }).click();
      await page.waitForFunction(() => !document.querySelector('[role="dialog"] [role="progressbar"]'));
      assert.equal(await dialog.getByRole('spinbutton', { name: p.hours, exact: true }).inputValue(), '7');
      assert.equal(await dialog.getByRole('switch', { name: p.watchdog, exact: true }).isChecked(), true);
      assert.equal(count(f, 'restartschedulesave'), 1, 'refreshing a session never replays Save');
      await dialog.getByRole('button', { name: p.save, exact: true }).click();
      await dialog.waitFor({ state: 'hidden' });
      assert.equal(f.calls.filter(call => call.cmd === 'restartschedulesave').at(-1).csrf_token, 'anonymous-b');
      assert.equal(count(f, 'login'), 0);
    });
    await run('expired-session-does-not-offer-service-actions', {}, async (page, f) => {
      f.statusUnauthorized = true;
      await page.evaluate(() => window.fixture.refresh());
      await page.getByRole('dialog').getByRole('textbox', { name: p.username, exact: true }).waitFor();
      assert.equal(await page.getByRole('button', { name: p.restart, exact: true, includeHidden: true }).count(), 0);
      assert.equal(count(f, 'start') + count(f, 'stop') + count(f, 'restart'), 0);
    });
    for (const statusFailure of [200, 503]) {
      await run(`failed-status-${statusFailure}-does-not-offer-service-actions`, { auth: false }, async (page, f) => {
        f.statusFailure = statusFailure;
        await page.evaluate(() => window.fixture.refresh());
        assert.equal(await page.getByRole('button', { name: p.restart, exact: true, includeHidden: true }).count(), 0, 'an unknown service status is never treated as an intentionally password-free panel');
        assert.equal(await page.getByRole('button', { name: p.timer, exact: true, includeHidden: true }).count(), 0);
        assert.equal(count(f, 'start') + count(f, 'stop') + count(f, 'restart'), 0);
        f.statusFailure = false;
        await page.evaluate(() => window.fixture.refresh());
        assert.equal(await page.getByRole('button', { name: p.restart, exact: true }).isEnabled(), true, 'a successful status restores ordinary controls');
      });
    }
    await run('mobile-and-preview', {}, async page => {
      if (process.env.NFQWS_RESTART_PREVIEW_DIR) {
        await mkdir(process.env.NFQWS_RESTART_PREVIEW_DIR, { recursive: true });
        await page.screenshot({ path: join(process.env.NFQWS_RESTART_PREVIEW_DIR, `${lang}-desktop-controls.png`), animations: 'disabled' });
      }
      let dialog = await open(page);
      if (process.env.NFQWS_RESTART_PREVIEW_DIR) await page.screenshot({ path: join(process.env.NFQWS_RESTART_PREVIEW_DIR, `${lang}-desktop-dialog.png`), animations: 'disabled' });
      await dialog.getByRole('button', { name: p.cancel, exact: true }).click();
      await page.setViewportSize({ width: 360, height: 740 });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'header fits a phone viewport');
      if (process.env.NFQWS_RESTART_PREVIEW_DIR) await page.screenshot({ path: join(process.env.NFQWS_RESTART_PREVIEW_DIR, `${lang}-mobile-controls.png`), animations: 'disabled' });
      dialog = await open(page);
      await dialog.getByRole('radio', { name: p.custom, exact: true }).check();
      await dialog.getByRole('spinbutton', { name: p.hours, exact: true }).fill('7');
      const bounds = await dialog.boundingBox();
      assert.ok(bounds.x >= 0 && bounds.x + bounds.width <= 360, 'dialog fits a phone viewport');
      assert.equal(await dialog.getByRole('button', { name: p.save, exact: true }).isVisible(), true);
      if (process.env.NFQWS_RESTART_PREVIEW_DIR) await page.screenshot({ path: join(process.env.NFQWS_RESTART_PREVIEW_DIR, `${lang}-mobile-dialog.png`), animations: 'disabled' });
    });
  }
  assert.deepEqual(failures, [], 'scheduled restart browser regressions');
} finally { await browser?.close(); if (server) await new Promise(resolve => server.close(resolve)); }

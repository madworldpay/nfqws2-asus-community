/**
 * Focused browser verification of the isolated draft UI; no router or real API.
 * Run: node source/project/experimental/device-profiles/test_frontend.mjs
 */
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import { fileURLToPath } from 'node:url';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');

const directory = fileURLToPath(new URL('.', import.meta.url));
const empty = () => ({ schema_version: 1, mode: 'common', devices: [], profiles: [] });
let saved = empty();
let revision = 'a'.repeat(64);
let token = 0;
let fail = '';
let discoveryReads = 0;
const requests = [];
const discovered = [
  { id: 'mac-001122334455', name: 'Ноутбук <img src=x onerror=alert(1)>', mac: '00:11:22:33:44:55', addresses: ['192.168.50.22'], sources: ['dhcp', 'neighbor'], seen: 'known' },
  { id: 'mac-aabbccddeeff', name: 'Телефон', mac: 'aa:bb:cc:dd:ee:ff', addresses: ['192.168.50.24'], sources: ['dhcp'], seen: 'known' },
];
const status = () => ({
  schema_version: 1, experimental: true, applied: false, revision, draft: saved,
  discovery: { state: 'partial', checked_at: '2026-11-07T08:00:00Z', interfaces: ['br-lan'], devices: discovered },
  templates: [{ id: 'current', name: 'Текущая стратегия' }, { id: 'stock', name: 'Стоковая стратегия' }],
});
const server = createServer(async (request, response) => {
  try {
    if (request.url === '/index.php') {
      assert.equal(request.method, 'POST');
      const chunks = [];
      for await (const chunk of request) chunks.push(chunk);
      const params = new URLSearchParams(Buffer.concat(chunks).toString());
      const cmd = params.get('cmd');
      requests.push(cmd);
      response.setHeader('Content-Type', 'application/json');
      if (fail === 'unauthorized') { response.statusCode = 401; response.end(JSON.stringify({ error: 'unauthorized' })); return; }
      if (cmd === 'status') { token += 1; response.end(JSON.stringify({ csrf_token: 'csrf-' + token })); return; }
      assert.equal(params.get('csrf_token'), 'csrf-' + token, 'fresh same-origin CSRF used');
      if (cmd === 'deviceprofilesstatus') { discoveryReads += 1; response.end(JSON.stringify(status())); return; }
      if (cmd === 'deviceprofilessave') {
        if (fail === 'stale' || params.get('revision') !== revision) { response.statusCode = 409; response.end(JSON.stringify({ error: 'stale_revision' })); return; }
        if (fail === 'storage') { response.statusCode = 503; response.end(JSON.stringify({ error: 'storage_unavailable' })); return; }
        saved = JSON.parse(params.get('draft')); revision = revision === 'a'.repeat(64) ? 'b'.repeat(64) : 'c'.repeat(64);
        response.end(JSON.stringify(status())); return;
      }
      if (cmd === 'deviceprofilespreview') {
        const draft = JSON.parse(params.get('draft'));
        const profiles = draft.profiles.map((p, i) => ({ ...p, priority: i + 1 }));
        response.end(JSON.stringify({
          schema_version: 1, applied: false, mode: draft.mode, profiles,
          assignments: draft.devices.map((d) => ({ device_id: d.id, profile_ids: profiles.filter((p) => p.enabled && p.device_ids.includes(d.id)).map((p) => p.id), fallback: 'current' })),
          warnings: draft.devices.some((d) => !d.addresses.length) ? ['unresolved_mac'] : [],
        })); return;
      }
      throw new Error('Unexpected command: ' + cmd);
    }
    const file = request.url?.split('/').pop();
    const types = { 'device-profiles-lab.html': 'text/html; charset=utf-8', 'device-profiles-lab.js': 'text/javascript; charset=utf-8', 'device-profiles-lab.css': 'text/css; charset=utf-8' };
    if (!Object.hasOwn(types, file)) { response.statusCode = 404; response.end(); return; }
    response.setHeader('Content-Type', types[file]);
    response.end(await readFile(directory + file));
  } catch (error) {
    response.statusCode = 500;
    response.end(JSON.stringify({ error: String(error) }));
  }
});
await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
const url = `http://127.0.0.1:${server.address().port}/device-profiles-lab/device-profiles-lab.html`;
let browser;
const pageErrors = [];
async function ready(page, text = 'Черновик сохранён') {
  await page.locator('#save-state').filter({ hasText: text }).waitFor();
  await page.waitForFunction(() => !document.querySelector('#editor').disabled);
}
try {
  browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  const page = await browser.newPage({ viewport: { width: 1180, height: 900 } });
  page.setDefaultTimeout(10000);
  page.on('pageerror', (error) => pageErrors.push(String(error)));
  await page.goto(url);
  await ready(page);
  assert.deepEqual(requests.slice(0, 2), ['status', 'deviceprofilesstatus']);
  assert.equal(await page.locator('#profiles-section').isVisible(), false, 'common hides profile complexity');
  assert.equal(await page.locator('#draft-devices .device-row').count(), 0, 'discovered devices are not silently added');
  assert.equal(await page.locator('img').count(), 0, 'untrusted device name stays text');
  await page.locator('#discovery-devices .device-row').first().getByRole('button').click();
  await ready(page, 'Есть несохранённые изменения');
  await page.locator('#manual-section summary').click();
  await page.locator('#manual-name').fill('Телевизор');
  await page.locator('#manual-ip').fill('192.168.1.999');
  await page.getByRole('button', { name: 'Добавить устройство', exact: true }).click();
  assert.match(await page.locator('#manual-error').textContent(), /IPv4/);
  await page.locator('#manual-ip').fill('2001:0db8::10');
  await page.locator('#manual-mac').fill('12-34-56-78-9A-BC');
  await page.getByRole('button', { name: 'Добавить устройство', exact: true }).click();
  assert.equal(await page.locator('#draft-devices .device-row').count(), 2);
  assert.match(await page.locator('#draft-devices').textContent(), /2001:db8::10/);
  assert.match(await page.locator('#draft-devices').textContent(), /12:34:56:78:9a:bc/);
  await page.locator('input[value="split"]').check();
  await page.locator('#add-profile').click();
  await page.locator('.profile-card').first().getByLabel('Название профиля', { exact: true }).fill('Видео');
  await page.locator('.profile-card').first().locator('.device-choice input').nth(1).check();
  await page.locator('.profile-card').first().getByLabel('Стратегия', { exact: true }).selectOption('stock');
  await page.locator('#add-profile').click();
  await page.locator('.profile-card').nth(1).getByLabel('Название профиля', { exact: true }).fill('Обход');
  await page.locator('.profile-card').nth(1).locator('.device-choice input').nth(1).check();
  const names = () => page.locator('.profile-fields input').evaluateAll((inputs) => inputs.map((input) => input.value));
  await page.locator('.profile-card').nth(1).locator('.move-up').click();
  assert.deepEqual(await names(), ['Обход', 'Видео'], 'mobile/keyboard button reorders priority');
  await page.locator('.profile-card').first().locator('.drag-handle').press('Alt+ArrowDown');
  assert.deepEqual(await names(), ['Видео', 'Обход'], 'keyboard drag-handle equivalent works');
  await page.locator('.profile-card').nth(1).locator('.drag-handle').dragTo(page.locator('.profile-card').first());
  assert.deepEqual(await names(), ['Обход', 'Видео'], 'mouse drag reorders profile priority');
  await page.locator('#preview').click();
  await page.locator('#preview-section').waitFor();
  await ready(page, 'Есть несохранённые изменения');
  assert.match(await page.locator('#preview-content').textContent(), /1\. Обход.*2\. Видео.*по умолчанию/s);
  assert.equal(saved.profiles.length, 0, 'preview does not save');
  if (process.env.LAB_SCREENSHOT_DIR) await page.screenshot({ path: process.env.LAB_SCREENSHOT_DIR + '/device-profiles-desktop.png', fullPage: true });
  await page.locator('#save').click();
  await ready(page);
  assert.equal(saved.mode, 'split');
  assert.deepEqual(saved.profiles.map((p) => p.name), ['Обход', 'Видео']);
  assert.equal(saved.devices[1].id.startsWith('manual-'), true);
  await page.reload(); await ready(page);
  assert.deepEqual(await names(), ['Обход', 'Видео'], 'saved order restored after reload');
  assert.equal(await page.locator('.device-choice input:checked').count(), 2);
  const reads = discoveryReads;
  await page.locator('#refresh').click(); await ready(page);
  assert.equal(discoveryReads, reads + 1, 'refresh actually requests discovery');
  await page.locator('.profile-card').first().getByLabel('Название профиля', { exact: true }).fill('Правки этой вкладки');
  fail = 'stale';
  await page.locator('#save').click();
  await page.locator('#stale-notice').waitFor();
  await ready(page, 'Есть несохранённые изменения');
  assert.equal((await names())[0], 'Правки этой вкладки', 'stale save preserves local edits');
  assert.equal(await page.locator('#save').isDisabled(), true);
  page.once('dialog', (dialog) => dialog.dismiss());
  await page.locator('#reload').click();
  assert.equal((await names())[0], 'Правки этой вкладки', 'cancelled reload preserves edits');
  fail = '';
  page.once('dialog', (dialog) => dialog.accept());
  await page.locator('#reload').click(); await ready(page);
  assert.equal((await names())[0], 'Обход', 'explicit reload restores saved draft');
  await page.setViewportSize({ width: 375, height: 812 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'no mobile horizontal overflow');
  if (process.env.LAB_SCREENSHOT_DIR) await page.screenshot({ path: process.env.LAB_SCREENSHOT_DIR + '/device-profiles-mobile.png', fullPage: true });
  await page.locator('.profile-card').nth(1).locator('.move-up').click();
  assert.deepEqual(await names(), ['Видео', 'Обход']);
  fail = 'storage';
  await page.locator('#save').click();
  await ready(page, 'Есть несохранённые изменения');
  assert.match(await page.locator('#notice').textContent(), /Хранилище/);
  assert.equal(await page.locator('#save').isEnabled(), true, 'failed save is retryable');
  assert.deepEqual(await names(), ['Видео', 'Обход'], 'failed save retains reorder');
  const loginPage = await browser.newPage();
  loginPage.on('pageerror', (error) => pageErrors.push(String(error)));
  fail = 'unauthorized';
  await loginPage.goto(url);
  await loginPage.locator('#notice').filter({ hasText: 'Сеанс панели истёк' }).waitFor();
  assert.equal(await loginPage.locator('input[value="common"]').isDisabled(), true);
  assert.equal(await loginPage.locator('#reload').isEnabled(), true);
  await loginPage.close();
  assert.deepEqual(pageErrors, []);
  console.log('PASS: common/split, discovery, safe text, manual validation, profile selection, mouse/mobile/keyboard priorities, preview/save separation, persistence, stale edits, retryable errors, auth and mobile overflow.');
} finally {
  if (browser) await browser.close();
  await new Promise((resolve) => server.close(resolve));
}

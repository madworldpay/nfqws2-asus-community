// Real panel behavior; only the router's HTTP boundary and the shared auth hook are fixtures.
// Catches lost/stale mutation retries, incorrect request fields, false readiness/empty success,
// destructive disabled mode, overlapping/background polling, and mobile overflow.
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { mkdtemp, mkdir, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "../webui/web/node_modules/esbuild/lib/main.js";

const { chromium } = await import(
  process.env.NFQWS_PLAYWRIGHT_MODULE || "playwright"
);
const web = fileURLToPath(new URL("../webui/web/", import.meta.url));
const dir = await mkdtemp(join(tmpdir(), "nfqws-ip-health-"));
const now = Math.floor(Date.now() / 1000);
const rows = [
  {
    id: "a".repeat(32),
    ip: "198.51.100.24",
    port: 443,
    host: "media.example.com",
    until: now + 79000,
    first_seen: now - 7400,
    incident: 1,
    last_check: now - 300,
    check_state: "silent",
  },
  {
    id: "b".repeat(32),
    ip: "2001:db8:ffff:ffff:ffff:ffff:ffff:1234",
    port: 443,
    host: "very-long-hostname-for-mobile.media.example.com",
    until: now + 540000,
    first_seen: now - 1000,
    incident: 2,
    last_check: null,
    check_state: "due",
  },
];
let data,
  sequence,
  mode,
  delay,
  statusCalls,
  mutations,
  activeRequests,
  maxActive;
function reset() {
  sequence = 1;
  mode = "";
  delay = 0;
  statusCalls = 0;
  mutations = [];
  activeRequests = 0;
  maxActive = 0;
  data = {
    schema_version: 1,
    revision: "1".repeat(64),
    enabled: true,
    runtime: {
      state: "active",
      code: null,
      updated_at: now,
      dns: "router_udp",
    },
    entries: structuredClone(rows),
  };
}
function revised() {
  data.revision = (++sequence).toString(16).padStart(64, "0");
}
let server, browser;
try {
  await build({
    stdin: {
      resolveDir: web,
      loader: "tsx",
      contents: `
    import React from 'react'; import {createRoot} from 'react-dom/client';
    import {Box} from '@mui/material'; import {Layout} from './src/components/Layout';
    import {IpHealthPanel} from './src/components/IpHealthPanel';
    createRoot(document.getElementById('root')).render(<Layout><Box sx={{position:'relative',height:'100svh'}}><IpHealthPanel/></Box></Layout>);
  `,
    },
    bundle: true,
    platform: "browser",
    format: "iife",
    jsx: "automatic",
    outfile: join(dir, "fixture.js"),
    tsconfig: join(web, "tsconfig.app.json"),
    logLevel: "silent",
    define: { "process.env.APP_VERSION": '"0.1.4"' },
    plugins: [
      {
        name: "auth-fixture",
        setup(b) {
          b.onResolve({ filter: /hooks\/useStatus$/ }, () => ({
            path: "status",
            namespace: "fixture",
          }));
          b.onLoad({ filter: /.*/, namespace: "fixture" }, () => ({
            contents: `export const useStatus=()=>({csrfToken:'fixture',platform:'asus-entware',isPending:false});`,
          }));
        },
      },
    ],
  });
  const js = await readFile(join(dir, "fixture.js"));
  server = createServer(async (req, res) => {
    if (req.method !== "POST") {
      res.setHeader(
        "Content-Type",
        req.url.startsWith("/fixture.js") ? "text/javascript" : "text/html",
      );
      res.end(
        req.url.startsWith("/fixture.js")
          ? js
          : '<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script src="/fixture.js"></script></body></html>',
      );
      return;
    }
    let raw = "";
    for await (const chunk of req) raw += chunk;
    const p = new URLSearchParams(raw),
      cmd = p.get("cmd");
    assert.equal(p.get("csrf_token"), "fixture");
    assert.equal(req.url, "/index.php");
    activeRequests++;
    maxActive = Math.max(maxActive, activeRequests);
    res.once("close", () => activeRequests--);
    if (delay) await new Promise((resolve) => setTimeout(resolve, delay));
    res.setHeader("Content-Type", "application/json");
    if (cmd === "iphealthstatus") {
      statusCalls++;
      assert.deepEqual([...p.keys()].sort(), ["cmd", "csrf_token"]);
      if (mode === "timeout") return; // AbortController in the real request helper ends this request.
      if (mode === "load_error") {
        res.statusCode = 503;
        res.end(JSON.stringify({ error: "unavailable" }));
        return;
      }
      if (mode === "malformed_time") {
        res.end(
          JSON.stringify({
            ...data,
            entries: [{ ...rows[0], until: Number.MAX_SAFE_INTEGER }],
          }),
        );
        return;
      }
      if (mode === "malformed") {
        res.end(
          JSON.stringify({ ...data, entries: [{ ...rows[0], port: 80 }] }),
        );
        return;
      }
      res.end(JSON.stringify(data));
      return;
    }
    mutations.push(Object.fromEntries(p));
    if (process.env.NFQWS_IP_HEALTH_DEBUG)
      console.log(
        cmd,
        p.get("revision")?.slice(-2),
        data.revision.slice(-2),
        mode,
      );
    assert.ok(
      [
        "iphealthconfigure",
        "iphealthremove",
        "iphealthclear",
        "iphealthrecheck",
      ].includes(cmd),
    );
    assert.equal(p.get("revision"), data.revision);
    const keys = ["cmd", "csrf_token", "revision"];
    if (cmd === "iphealthconfigure") keys.push("enabled");
    if (["iphealthremove", "iphealthrecheck"].includes(cmd)) keys.push("id");
    assert.deepEqual([...p.keys()].sort(), keys.sort());
    if (mode === "stale") {
      mode = "";
      data.entries = data.entries.slice(1);
      revised();
      res.statusCode = 409;
      res.end(JSON.stringify({ error: "stale_revision" }));
      return;
    }
    if (cmd === "iphealthconfigure") {
      assert.ok(["0", "1"].includes(p.get("enabled")));
      data.enabled = p.get("enabled") === "1";
      data.runtime.state = data.enabled ? "active" : "stopped";
    } else if (cmd === "iphealthremove") {
      assert.ok(data.entries.some((entry) => entry.id === p.get("id")));
      data.entries = data.entries.filter((entry) => entry.id !== p.get("id"));
    } else if (cmd === "iphealthclear") data.entries = [];
    else {
      assert.ok(
        p.get("id") === "all" ||
          data.entries.some((entry) => entry.id === p.get("id")),
      );
      data.entries = data.entries.map((entry) =>
        p.get("id") === "all" || entry.id === p.get("id")
          ? { ...entry, check_state: "checking" }
          : entry,
      );
    }
    revised();
    // Lose a response after headers, so Chromium cannot transparently replay a
    // reused connection before fetch receives a response. The application must not retry.
    if (mode === "lost") {
      mode = "";
      res.flushHeaders();
      res.write("{");
      setTimeout(() => res.destroy(), 10);
      return;
    }
    res.end(JSON.stringify(data));
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  browser = await chromium.launch({
    headless: true,
    executablePath:
      process.env.NFQWS_CHROMIUM_EXECUTABLE || "/usr/bin/google-chrome",
  });
  const origin = `http://127.0.0.1:${server.address().port}`;
  for (const lang of process.env.NFQWS_IP_HEALTH_ERRORS_ONLY
    ? []
    : ["ru", "en"]) {
    reset();
    delay = 200;
    const page = await browser.newPage({
      viewport: { width: 390, height: 844 },
      locale: lang,
    });
    page.setDefaultTimeout(6000);
    await page.addInitScript(() => {
      localStorage.setItem("nfqws2-appearance", "rabbit");
      localStorage.setItem("theme", "dark");
    });
    const pack = JSON.parse(
      await readFile(join(web, `src/translations/${lang}.json`), "utf8"),
    ).ip_health;
    // First assertion also provides the initial RED while the panel does not exist.
    await page.goto(origin);
    const toggle = page.getByRole("switch", { name: pack.toggle });
    await page.getByText(pack.loading, { exact: true }).waitFor();
    assert.equal(await toggle.isDisabled(), true);
    await page.getByText(rows[0].ip, { exact: true }).waitFor();
    delay = 0;
    await page.getByText(pack.runtime.active, { exact: true }).waitFor();
    await page.getByText(pack.dns_limit, { exact: true }).waitFor();
    const refresh = page.getByRole("button", {
      name: pack.refresh,
      exact: true,
    });
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      true,
    );
    if (process.env.NFQWS_IP_HEALTH_SCREENSHOTS) {
      await mkdir(process.env.NFQWS_IP_HEALTH_SCREENSHOTS, { recursive: true });
      await page.screenshot({
        path: join(
          process.env.NFQWS_IP_HEALTH_SCREENSHOTS,
          `${lang}-mobile.png`,
        ),
        fullPage: true,
      });
      await page.locator("main").evaluate((element) => {
        element.scrollTop = element.scrollHeight;
      });
      await page.screenshot({
        path: join(
          process.env.NFQWS_IP_HEALTH_SCREENSHOTS,
          `${lang}-mobile-list.png`,
        ),
        fullPage: true,
      });
      await page.locator("main").evaluate((element) => {
        element.scrollTop = 0;
      });
      await page.setViewportSize({ width: 1280, height: 900 });
      await page.screenshot({
        path: join(
          process.env.NFQWS_IP_HEALTH_SCREENSHOTS,
          `${lang}-desktop.png`,
        ),
        fullPage: true,
      });
      await page.setViewportSize({ width: 390, height: 844 });
    }
    await toggle.click();
    await page.getByText(pack.disabled_note, { exact: true }).waitFor();
    assert.equal(
      data.entries.length,
      2,
      "Disable preserves saved entries/history",
    );
    assert.equal(await toggle.isChecked(), false);
    assert.equal(mutations.at(-1).enabled, "0");
    await toggle.click();
    await page.getByText(pack.runtime.active, { exact: true }).waitFor();
    const rowAction = (key, ip) =>
      page.getByRole("button", { name: `${pack[key]} ${ip}`, exact: true });
    await rowAction("recheck", rows[0].ip).click();
    await page
      .getByText(pack.check.checking, { exact: true })
      .first()
      .waitFor();
    assert.equal(mutations.at(-1).id, rows[0].id);
    assert.equal(mutations.at(-1).cmd, "iphealthrecheck");
    await page
      .getByRole("button", { name: pack.recheck_all, exact: true })
      .click();
    await page.waitForFunction(
      () =>
        [...document.querySelectorAll('[data-check-state="checking"]')]
          .length === 2,
    );
    assert.equal(mutations.at(-1).id, "all");
    await rowAction("remove", rows[0].ip).click();
    await page
      .getByText(rows[0].ip, { exact: true })
      .waitFor({ state: "detached" });
    assert.equal(mutations.at(-1).cmd, "iphealthremove");
    const before = mutations.length;
    await page.getByRole("button", { name: pack.clear, exact: true }).click();
    await page
      .getByRole("dialog", { name: pack.clear_title, exact: true })
      .waitFor();
    assert.equal(mutations.length, before, "Clear needs confirmation");
    await page.getByRole("button", { name: pack.cancel, exact: true }).click();
    assert.equal(mutations.length, before);
    await page.getByRole("button", { name: pack.clear, exact: true }).click();
    await page
      .getByRole("button", { name: pack.confirm_clear, exact: true })
      .click();
    await page.getByText(pack.empty, { exact: true }).waitFor();
    assert.equal(mutations.length, before + 1);
    assert.equal(mutations.at(-1).cmd, "iphealthclear");
    data.entries = structuredClone(rows);
    revised();
    await refresh.click();
    await page.getByText(rows[0].ip, { exact: true }).waitFor();
    mode = "stale";
    const staleCount = mutations.length;
    await rowAction("remove", rows[0].ip).click();
    await page.getByText(pack.errors.stale_revision, { exact: true }).waitFor();
    await page
      .getByText(rows[0].ip, { exact: true })
      .waitFor({ state: "detached" });
    assert.equal(
      mutations.length,
      staleCount + 1,
      "A stale action reloads without resending",
    );
    mode = "lost";
    const lostCount = mutations.length;
    await rowAction("remove", rows[1].ip).click();
    await page.getByText(pack.errors.action_unknown, { exact: true }).waitFor();
    await page.getByText(pack.empty, { exact: true }).waitFor();
    assert.equal(
      mutations.length,
      lostCount + 1,
      "Lost reply reloads state; never repeats mutation",
    );
    data.entries = structuredClone(rows);
    data.runtime = {
      state: "unavailable",
      code: "socket_unavailable",
      updated_at: now,
      dns: "unavailable",
    };
    revised();
    await refresh.click();
    await page
      .getByText(pack.runtime.socket_unavailable, { exact: true })
      .waitFor();
    assert.equal(
      await page.getByText(pack.runtime.active, { exact: true }).count(),
      0,
      "Configured is not runtime readiness",
    );
    assert.equal(await page.getByText(rows[0].ip, { exact: true }).count(), 1);
    data.runtime.code = "future_code";
    await refresh.click();
    await page.getByText(pack.runtime.unavailable, { exact: true }).waitFor();
    for (const code of [
      "core_stopped",
      "socket_unavailable",
      "socket_preparing",
      "socket_setup_failed",
      "multiwan_unsupported",
      "queue_in_use",
      "clock_unavailable",
      "starting",
    ]) {
      data.runtime.code = code;
      data.runtime.state =
        code === "starting" || code === "socket_preparing"
          ? "starting"
          : code === "core_stopped"
            ? "stopped"
            : "unavailable";
      await refresh.click();
      await page.getByText(pack.runtime[code], { exact: true }).waitFor();
      assert.equal(
        await page.getByText(pack.runtime.active, { exact: true }).count(),
        0,
      );
    }
    // Background tabs do not poll; returning to the panel refreshes once, with no overlap.
    await page.evaluate(() => {
      Object.defineProperty(document, "visibilityState", {
        configurable: true,
        value: "hidden",
      });
      document.dispatchEvent(new Event("visibilitychange"));
    });
    const hiddenCount = statusCalls;
    await page.waitForTimeout(5300);
    assert.equal(statusCalls, hiddenCount);
    await page.evaluate(() => {
      Object.defineProperty(document, "visibilityState", {
        configurable: true,
        value: "visible",
      });
      document.dispatchEvent(new Event("visibilitychange"));
    });
    await page.waitForFunction(
      () => !document.querySelector('[aria-busy="true"]'),
    );
    await page.waitForTimeout(100);
    assert.equal(statusCalls, hiddenCount + 1);
    // Visibility changes while the initial foreground refresh is in flight must not
    // create two independent polling loops after that request completes.
    await page.evaluate(() => {
      Object.defineProperty(document, "visibilityState", {
        configurable: true,
        value: "hidden",
      });
      document.dispatchEvent(new Event("visibilitychange"));
    });
    delay = 300;
    await page.evaluate(() => {
      Object.defineProperty(document, "visibilityState", {
        configurable: true,
        value: "visible",
      });
      document.dispatchEvent(new Event("visibilitychange"));
    });
    await page.waitForFunction(() =>
      document.querySelector('[aria-busy="true"]'),
    );
    await page.evaluate(() => {
      Object.defineProperty(document, "visibilityState", {
        configurable: true,
        value: "hidden",
      });
      document.dispatchEvent(new Event("visibilitychange"));
      Object.defineProperty(document, "visibilityState", {
        configurable: true,
        value: "visible",
      });
      document.dispatchEvent(new Event("visibilitychange"));
    });
    await page.waitForFunction(
      () => !document.querySelector('[aria-busy="true"]'),
    );
    delay = 0;
    const foregroundCount = statusCalls;
    await page.waitForTimeout(5400);
    assert.equal(
      statusCalls,
      foregroundCount + 1,
      "Rapid visibility changes must leave only one polling timer",
    );
    assert.equal(maxActive, 1, "Polling and actions must never overlap");
    await page.close();
  }
  for (const invalid of [
    "malformed_time",
    "load_error",
    "malformed",
    "timeout",
  ]) {
    reset();
    mode = invalid;
    const page = await browser.newPage({ locale: "en" });
    const pack = JSON.parse(
      await readFile(join(web, "src/translations/en.json"), "utf8"),
    ).ip_health;
    await page.goto(origin);
    await page
      .getByRole("alert")
      .waitFor({ timeout: invalid === "timeout" ? 18000 : 6000 });
    if (invalid === "timeout")
      await page.getByText(pack.errors.timeout, { exact: true }).waitFor();
    assert.equal(
      await page.getByText(pack.empty, { exact: true }).count(),
      0,
      "A failed status is never an empty-success list",
    );
    assert.equal(
      await page.getByRole("switch", { name: pack.toggle }).isDisabled(),
      true,
    );
    mode = "";
    await page.getByRole("button", { name: pack.refresh, exact: true }).click();
    await page.getByText(rows[0].ip, { exact: true }).waitFor();
    await page.close();
  }
  console.log(
    "PASS real IP Health panel RU/EN, mobile/desktop, exact actions, disabled history, asynchronous checks, confirmation, stale/lost replies, malformed/load failure, readiness and visible non-overlapping polling",
  );
} finally {
  await browser?.close();
  if (server) await new Promise((resolve) => server.close(resolve));
  await rm(dir, { recursive: true, force: true });
}

import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "../webui/web/node_modules/esbuild/lib/main.js";

const { chromium } = await import(
  process.env.NFQWS_PLAYWRIGHT_MODULE || "playwright"
);
const web = fileURLToPath(new URL("../webui/web/", import.meta.url));
const compact = await readFile(join(web, "public/compact-viewport.css"));
const fixtures = new Map();
const song = { title: "Я один гуляю — Opera", url: "https://youtu.be/QYr32Sgwtxk" };
let browser, server;
try {
  const bundle = await build({
    stdin: {
      resolveDir: web,
      loader: "tsx",
      contents: `
    import React from'react';import{createRoot}from'react-dom/client';
    import{QueryClientProvider}from'@tanstack/react-query';
    import{createRootRoute,createRouter,RouterProvider}from'@tanstack/react-router';
    import{queryClient,API}from'./src/api/client';import{Header}from'./src/components/Header';
    import{Layout}from'./src/components/Layout';import{useAppStore}from'./src/store/useAppStore';
    useAppStore.setState({auth:true});
    window.fixture={loseAuth:()=>useAppStore.getState().setAuth(false),refreshStatus:()=>API.invalidateStatus(),refreshOverview:()=>queryClient.refetchQueries({queryKey:['package-update-overview'],type:'active'})};
    const routeTree=createRootRoute({component:()=> <Header/>}),router=createRouter({routeTree});
    createRoot(document.getElementById('root')).render(<QueryClientProvider client={queryClient}><Layout><RouterProvider router={router}/></Layout></QueryClientProvider>);
  `,
    },
    bundle: true,
    platform: "browser",
    format: "iife",
    write: false,
    outfile: "/fixture.js",
    jsx: "automatic",
    external: ["/community/*"],
    tsconfig: join(web, "tsconfig.app.json"),
    logLevel: "silent",
    define: {
      "process.env.APP_VERSION": '"0.1.4"',
      "process.env.NODE_ENV": '"production"',
    },
  });
  server = createServer(async (req, res) => {
    if (req.method !== "POST") {
      if (/^\/community\/[A-Za-z0-9_.-]+$/.test(req.url)) {
        res.setHeader(
          "Content-Type",
          req.url.endsWith(".webp") ? "image/webp" : "image/png",
        );
        res.end(await readFile(join(web, "public", req.url)));
        return;
      }
      const file = bundle.outputFiles.find((file) =>
        file.path.endsWith(req.url),
      );
      res.setHeader(
        "Content-Type",
        req.url.endsWith(".js")
          ? "text/javascript"
          : req.url.endsWith(".css")
            ? "text/css"
            : "text/html",
      );
      res.end(
        req.url === "/compact.css"
          ? compact
          : file
            ? file.contents
            : '<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/fixture.css"><link rel="stylesheet" href="/compact.css"></head><body><div id="root"></div><script src="/fixture.js"></script></body></html>',
      );
      return;
    }
    const f = fixtures.get(req.headers["x-fixture"]);
    let raw = "";
    for await (const part of req) raw += part;
    const params = req.headers["content-type"]?.startsWith(
      "multipart/form-data",
    )
      ? new URLSearchParams(
          [
            ...(await new Response(raw, {
              headers: { "Content-Type": req.headers["content-type"] },
            }).formData()),
          ].map(([key, value]) => [key, String(value)]),
        )
      : new URLSearchParams(raw);
    const cmd = params.get("cmd");
    f.calls.push(cmd);
    const check = {
      state: f.checkState || "current",
      code: f.checkState === "failed" ? "request_failed" : null,
      candidate: null,
      installed_version: "1.3.2-asus6+b94",
    };
    res.setHeader("Content-Type", "application/json");
    if (cmd === "status") {
      if (f.holdStatus)
        await new Promise((resolve) => {
          f.releaseStatus = resolve;
        });
      if (f.statusFailure) {
        res.statusCode = 503;
        res.end(JSON.stringify({ error: "request_failed" }));
        return;
      }
      res.end(
        JSON.stringify({
          status: 0,
          platform: "asus-entware",
          nfqws2: true,
          anonym: true,
          authenticated: false,
          csrf_token: "fixture",
          version: check.installed_version,
          service: f.service,
        }),
      );
    } else if (cmd === "packageupdatestatus")
      res.end(JSON.stringify({ check, operation: null }));
    else if (cmd === "packageupdatecheck") res.end(JSON.stringify(check));
    else {
      res.statusCode = 400;
      res.end(JSON.stringify({ error: "unexpected_command" }));
    }
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  browser = await chromium.launch({
    headless: true,
    ...(process.env.NFQWS_CHROMIUM_EXECUTABLE
      ? { executablePath: process.env.NFQWS_CHROMIUM_EXECUTABLE }
      : {}),
  });
  for (const language of ["ru", "en"]) {
    const f = { calls: [], service: false };
    fixtures.set(language, f);
    const context = await browser.newContext({
      viewport: { width: 1306, height: 900 },
      extraHTTPHeaders: { "x-fixture": language },
    });
    const external = [],
      errors = [];
    await context.route(/^https:\/\//, (route) => {
      const request = route.request();
      external.push({ url: request.url(), referer: request.headers().referer });
      return route.fulfill({
        status: 200,
        contentType: "text/html",
        body: "<!doctype html><title>Selected video</title>",
      });
    });
    await context.addInitScript(
      ({ language }) => {
        localStorage.setItem("lang", JSON.stringify(language));
        localStorage.setItem("nfqws2-appearance", "rabbit");
      },
      { language },
    );
    const page = await context.newPage();
    page.setDefaultTimeout(4000);
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("console", (message) => {
      if (
        ["error", "warning"].includes(message.type()) &&
        /anchorEl/.test(message.text())
      )
        errors.push(message.text());
    });
    const texts = JSON.parse(
      await readFile(join(web, "src/translations", language + ".json"), "utf8"),
    );
    const label = texts.rabbit_videos.open;
    await page.clock.install();
    await page.goto(`http://127.0.0.1:${server.address().port}/`);
    await page.waitForResponse(
      (response) =>
        response.url().endsWith("/index.php") &&
        new URLSearchParams(response.request().postData()).get("cmd") ===
          "packageupdatecheck",
    );
    let baseline = [...f.calls];
    const trigger = page.getByRole("button", { name: label, exact: true });
    await trigger.waitFor();
    const originalTrigger = await trigger.elementHandle();
    await trigger.click();
    const menu = page.getByRole("menu", { name: label, exact: true });
    await menu.waitFor();
    assert.equal(await menu.getByRole("menuitem").count(), 1);
    assert.equal(
      await page.getByRole("dialog").count(),
      0,
      "rabbit click does not open the package updater",
    );
    assert.equal(
      context.pages().length,
      1,
      "opening the menu never opens a video",
    );
    assert.deepEqual(
      external,
      [],
      "opening the panel/menu never contacts YouTube",
    );
    assert.deepEqual(
      f.calls,
      [...baseline, "status"],
      "opening confirms actual OFF with one read-only status request",
    );
    f.service = true;
    await page.evaluate(() => window.fixture.refreshStatus());
    await page.locator('.rabbit-build-stage[data-state="idle"]').waitFor();
    assert.equal(
      await originalTrigger.evaluate((node) => node.isConnected),
      true,
      "a background service-state update must retain the menu's live anchor",
    );
    await menu.waitFor({ state: "hidden" });
    assert.equal(
      await trigger.count() === 0,
      true,
      "ON service must disable the video trigger and close its already-open menu",
    );
    f.service = false;
    await page.evaluate(() => window.fixture.refreshStatus());
    await page.locator('.rabbit-build-stage[data-state="off"]').waitFor();
    await trigger.click();
    await menu.waitFor();
    baseline = [...f.calls];
    const item = menu.getByRole("menuitem", { name: song.title, exact: true });
    assert.equal(await item.getAttribute("href"), song.url);
    assert.equal(await item.getAttribute("target"), "_blank");
    assert.deepEqual((await item.getAttribute("rel")).split(/\s+/).sort(), [
      "noopener", "noreferrer",
    ]);
    const firstPopup = context.waitForEvent("page");
    await menu
      .getByRole("menuitem", { name: song.title, exact: true })
      .click();
    const first = await firstPopup;
    await first.waitForURL(song.url, { waitUntil: "domcontentloaded" });
    assert.equal(first.url(), song.url);
    assert.equal(await first.evaluate(() => window.opener), null);
    await first.close();
    await menu.waitFor({ state: "hidden" });
    await trigger.focus();
    await page.keyboard.press("Enter");
    await menu.waitFor();
    await page.keyboard.press("ArrowDown");
    const secondPopup = context.waitForEvent("page");
    await page.keyboard.press("Enter");
    const second = await secondPopup;
    await second.waitForURL(song.url, { waitUntil: "domcontentloaded" });
    assert.equal(second.url(), song.url);
    assert.equal(await second.evaluate(() => window.opener), null);
    await second.close();
    await menu.waitFor({ state: "hidden" });
    await trigger.focus();
    await page.keyboard.press("Space");
    await menu.waitFor();
    await page.keyboard.press("Escape");
    await menu.waitFor({ state: "hidden" });
    assert.equal(
      await trigger.evaluate((node) => node === document.activeElement),
      true,
      "Escape restores keyboard focus",
    );
    assert.deepEqual(
      external,
      [song, song].map(({ url }) => ({ url, referer: undefined })),
      "only the one song loads via mouse and keyboard, without a referrer",
    );
    assert.deepEqual(
      f.calls,
      [...baseline, "status", "status"],
      "each opening confirms OFF; no update/config/service action is sent",
    );
    assert.equal(await page.getByRole("dialog").count(), 0);
    // A cached OFF is insufficient: a fresh failing read must never open links.
    f.statusFailure = true;
    await trigger.click();
    await page.waitForFunction(
      () => !document.querySelector(".rabbit-build-video-trigger"),
    );
    assert.equal(await menu.count(), 0);
    f.statusFailure = false;
    for (const malformed of [null, undefined]) {
      f.service = malformed;
      await page.evaluate(() => window.fixture.refreshStatus());
      await trigger.waitFor({ state: "hidden" });
      assert.equal(
        await trigger.count() === 0,
        true,
        "missing/null service is not confirmed OFF",
      );
      assert.equal(await menu.count(), 0);
    }
    f.service = false;
    await page.evaluate(() => window.fixture.refreshStatus());
    await trigger.waitFor({ state: "visible" });
    // A pending confirmation cannot expose a menu before its actual ON response.
    f.holdStatus = true;
    await trigger.click();
    await page.waitForTimeout(100);
    assert.equal(await menu.count(), 0);
    assert.equal(typeof f.releaseStatus, "function");
    f.service = true;
    f.holdStatus = false;
    f.releaseStatus();
    await page.locator('.rabbit-build-stage[data-state="idle"]').waitFor();
    assert.equal(await trigger.count() === 0, true);
    assert.equal(await menu.count(), 0);
    f.service = false;
    await page.evaluate(() => window.fixture.refreshStatus());
    await trigger.click();
    await menu.waitFor();
    await page.clock.fastForward(30_001);
    await menu.waitFor({ state: "hidden" });
    assert.equal(context.pages().length, 1, "expiry never opens a video");
    const reviewFailures = [];
    await trigger.click();
    await menu.waitFor();
    await page.evaluate(() => window.fixture.loseAuth());
    await page.waitForTimeout(350);
    if (await menu.isVisible())
      reviewFailures.push("auth loss retained open menu");
    if (!(await page.locator(".rabbit-build-video-trigger").isDisabled()))
      reviewFailures.push("auth loss left enabled trigger");
    await page.keyboard.press("Escape");
    await menu.waitFor({ state: "hidden" });
    await page.evaluate(() => window.fixture.refreshStatus());
    delete f.releaseStatus;
    f.holdStatus = true;
    await trigger.click();
    await page.waitForTimeout(100);
    assert.equal(typeof f.releaseStatus, "function");
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
    const delayed = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        response.url().endsWith("/index.php"),
    );
    f.holdStatus = false;
    f.releaseStatus();
    await (await delayed).finished();
    await page.waitForTimeout(350);
    if (await menu.isVisible())
      reviewFailures.push("pending OFF request survived page hiding");
    await page.keyboard.press("Escape");
    await menu.waitFor({ state: "hidden" });
    assert.deepEqual(
      reviewFailures,
      [],
      "session loss and hiding cancel both open and pending menus",
    );
    f.service = true;
    await page.evaluate(() => window.fixture.refreshStatus());
    f.checkState = "failed";
    await page.evaluate(() => window.fixture.refreshOverview());
    await page.locator('.rabbit-build-stage[data-state="unknown"]').waitFor();
    await menu.waitFor({ state: "hidden" });
    assert.equal(
      await trigger.count(),
      0,
      "losing the artwork closes its video menu",
    );
    f.checkState = "current";
    await page.evaluate(() => window.fixture.refreshOverview());
    await page.locator('.rabbit-build-stage[data-state="idle"]').waitFor();
    assert.equal(await trigger.count(), 0);
    assert.equal(
      await menu.count(),
      0,
      "restoring the artwork does not reopen the old menu",
    );
    f.service = false;
    await page.evaluate(() => window.fixture.refreshStatus());
    await page.locator('.rabbit-build-stage[data-state="off"]').waitFor();
    await page.locator("header .MuiChip-root").click();
    await page
      .getByRole("dialog", { name: texts.package_update.title, exact: true })
      .waitFor();
    await page
      .getByRole("button", { name: texts.common.close, exact: true })
      .last()
      .click();
    await page.getByRole("dialog").waitFor({ state: "hidden" });
    for (const viewport of [
      { width: 390, height: 844 },
      { width: 844, height: 390 },
    ]) {
      await page.setViewportSize({ width: 1306, height: 900 });
      await trigger.click();
      await menu.waitFor();
      await page.setViewportSize(viewport);
      await menu.waitFor({ state: "hidden" });
      assert.equal(
        await trigger.isVisible(),
        false,
        "compact views retain the hidden rabbit",
      );
      await page.setViewportSize({ width: 1306, height: 900 });
      await trigger.waitFor({ state: "visible" });
      assert.equal(
        await menu.count(),
        0,
        "returning to desktop does not reopen the hidden menu",
      );
    }
    assert.deepEqual(errors, []);
    await context.close();
    console.log(
      `PASS ${language}: only the OFF rabbit offers its song, keyboard/Escape, no eager media or updater action, version button and compact visibility`,
    );
  }
} finally {
  await browser?.close();
  if (server) await new Promise((resolve) => server.close(resolve));
}

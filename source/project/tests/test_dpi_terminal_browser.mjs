import assert from "node:assert/strict";
import { createServer } from "node:http";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "../webui/web/node_modules/esbuild/lib/main.js";
const { chromium } = await import(
  process.env.NFQWS_PLAYWRIGHT_MODULE || "playwright"
);
const web = fileURLToPath(new URL("../webui/web/", import.meta.url));
const dir = await mkdtemp(join(tmpdir(), "dpi-terminal-browser-"));
let browser, server;
try {
  await build({
    stdin: {
      resolveDir: web,
      loader: "tsx",
      contents: `
    import React,{StrictMode,useState}from'react';import{createRoot}from'react-dom/client';
    import{DpiTerminalDialog}from'./src/components/DpiTerminalDialog';
    import{Layout}from'./src/components/Layout';
    const Fixture=()=>{const[open,setOpen]=useState(true);return <Layout>{open&&<DpiTerminalDialog csrfToken="fixture-csrf" onClose={()=>setOpen(false)}/>}</Layout>};
    createRoot(document.getElementById('root')).render(<StrictMode><Fixture/></StrictMode>);
  `,
    },
    bundle: true,
    platform: "browser",
    format: "iife",
    outfile: join(dir, "fixture.js"),
    jsx: "automatic",
    tsconfig: join(web, "tsconfig.app.json"),
    logLevel: "silent",
    define: {
      "process.env.NODE_ENV": JSON.stringify(
        process.env.NFQWS_TERMINAL_REACT_MODE || "production",
      ),
    },
  });
  const js = await readFile(join(dir, "fixture.js")),
    css = await readFile(join(dir, "fixture.css"));
  server = createServer((req, res) => {
    const type =
      req.url === "/fixture.js"
        ? "text/javascript"
        : req.url === "/fixture.css"
          ? "text/css"
          : "text/html";
    res.setHeader("Content-Type", type);
    res.end(
      req.url === "/fixture.js"
        ? js
        : req.url === "/fixture.css"
          ? css
          : '<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/fixture.css"></head><body><div id="root"></div><script src="/fixture.js"></script></body></html>',
    );
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  browser = await chromium.launch({
    headless: true,
    ...(process.env.NFQWS_CHROMIUM_EXECUTABLE
      ? { executablePath: process.env.NFQWS_CHROMIUM_EXECUTABLE }
      : {}),
  });
  for (const viewport of [
    { width: 1366, height: 768 },
    { width: 1024, height: 600 },
    { width: 390, height: 844 },
  ]) {
    const page = await browser.newPage({ viewport });
    page.setDefaultTimeout(5000);
    const calls = [],
      errors = [],
      consoleErrors = [],
      sizes = [],
      input = [],
      stoppedIds = [];
    let offset = 0,
      owner = null,
      nativeState = "running",
      issued = 0,
      terminalId;
    const result = (state = nativeState, text = "") => ({
      terminal_id: terminalId,
      state,
      offset: (offset += Buffer.byteLength(text)),
      data: Buffer.from(text).toString("base64"),
      exit_code: state === "running" ? null : 0,
    });
    page.on("pageerror", (error) => {
      errors.push(error.message);
      if (process.env.NFQWS_TERMINAL_DEBUG)
        console.log("PAGEERROR", error.message);
    });
    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text());
    });
    await page.addInitScript(() =>
      localStorage.setItem("lang", JSON.stringify("en")),
    );
    await page.route("**/index.php", async (route) => {
      const post = new URLSearchParams(route.request().postData()),
        cmd = post.get("cmd");
      calls.push(cmd);
      let body,
        status = 200;
      if (cmd === "dpiterminalinfo")
        body = { available: true, installed: true, code: null };
      else if (cmd === "sharesavedrefresh")
        body = { code: "ok", reports: [], skipped: 0, scan_truncated: false };
      else if (cmd === "dpiterminalstart") {
        if (owner) {
          status = 409;
          body = { error: "terminal_busy" };
        } else {
          owner = post.get("request_id");
          terminalId = (++issued === 1 ? "a" : "b").repeat(32);
          offset = 0;
          nativeState = "running";
          sizes.push({
            type: "start",
            cols: Number(post.get("cols")),
            rows: Number(post.get("rows")),
          });
          body = result(
            "running",
            "\u001b[2J\u001b[HNative Detector menu\r\n1 DNS\r\n2 TLS\r\n3 QUIC\r\nPress Enter to run\r\n",
          );
        }
      } else if (cmd === "dpiterminalpoll") {
        await new Promise((resolve) => setTimeout(resolve, 10));
        body = result();
      } else if (cmd === "dpiterminalresize") {
        sizes.push({
          type: "resize",
          cols: Number(post.get("cols")),
          rows: Number(post.get("rows")),
        });
        body = result();
      } else if (cmd === "dpiterminalinput") {
        const key = Buffer.from(post.get("data"), "base64").toString();
        input.push(key);
        if (key === "q") nativeState = "exited";
        body = result();
      } else if (cmd === "dpiterminalstop") {
        stoppedIds.push(post.get("terminal_id"));
        if (post.get("terminal_id") === terminalId) owner = null;
        body = { ...result("stopped"), terminal_id: post.get("terminal_id") };
      } else throw Error("Unexpected mutation: " + cmd);
      await route.fulfill({
        status,
        contentType: "application/json",
        body: JSON.stringify(body),
      });
    });
    await page.goto(`http://127.0.0.1:${server.address().port}/`);
    await page
      .getByRole("button", { name: "Enter: confirm", exact: true })
      .waitFor();
    await page.waitForFunction(() =>
      document
        .querySelector(".xterm-rows")
        ?.textContent.includes("Native Detector menu"),
    );
    await page.waitForTimeout(500);
    if (process.env.NFQWS_TERMINAL_DEBUG) {
      console.log(
        "INITIAL",
        JSON.stringify({
          calls,
          errors,
          consoleErrors,
          terminalCount: await page.locator(".xterm").count(),
          screenCount: await page.locator(".xterm-screen").count(),
        }),
      );
      await page.screenshot({ path: "/tmp/dpi-terminal-initial.png" });
    }
    assert.equal(
      await page.locator(".xterm").count(),
      1,
      "opening the dialog must not duplicate terminal DOM after its own state updates",
    );
    await page
      .getByRole("button", { name: "Enter: confirm", exact: true })
      .click();
    const before = await page.locator(".xterm").evaluateAll((nodes) =>
      nodes.map((n) => ({
        width: n.getBoundingClientRect().width,
        height: n.getBoundingClientRect().height,
      })),
    );
    await page
      .getByRole("button", { name: "DPI Detector help", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Refresh list", exact: true })
      .click();
    await page.setViewportSize({
      width: viewport.width - 20,
      height: viewport.height - 20,
    });
    await page.waitForTimeout(500);
    const after = await page.locator(".xterm").evaluateAll((nodes) =>
      nodes.map((n) => ({
        width: n.getBoundingClientRect().width,
        height: n.getBoundingClientRect().height,
      })),
    );
    if (process.env.NFQWS_TERMINAL_DEBUG) {
      console.log(
        JSON.stringify({ viewport, calls, sizes, errors, before, after }),
      );
      await page.screenshot({
        path: `/tmp/dpi-terminal-${viewport.width}.png`,
      });
    }
    assert.equal(
      await page.locator(".xterm").count(),
      1,
      "StrictMode and rerenders must keep one terminal DOM",
    );
    assert.equal(
      await page.locator(".xterm-screen").count(),
      1,
      "help and reports must not append another native screen",
    );
    assert.equal(
      calls.filter((cmd) => cmd === "dpiterminalstart").length,
      1,
      "state updates and help/fit must not restart the native owner",
    );
    assert.equal(
      calls.includes("dpiterminalstop"),
      false,
      "a mounted terminal must not stop its running native session",
    );
    assert.deepEqual(input, ["\r"], "the native menu can receive the run key");
    assert.deepEqual(errors, [], "xterm setup and fit must not throw");
    assert.deepEqual(
      consoleErrors,
      [],
      "sibling reconciliation must not report duplicate keys",
    );
    assert.ok(sizes.length < 20, "fit must converge without a resize loop");
    await page
      .getByRole("button", { name: "Q: quit Detector", exact: true })
      .click();
    const reopen = page.getByRole("button", {
      name: "Reopen terminal",
      exact: true,
    });
    await reopen.waitFor();
    await reopen.click();
    await page.waitForFunction(() =>
      document.querySelector('[aria-label="Enter: confirm"]:not(:disabled)'),
    );
    await page.waitForTimeout(300);
    assert.equal(
      await page.locator(".xterm").count(),
      1,
      "explicit reopen replaces the old terminal DOM",
    );
    assert.equal(await page.locator(".xterm-screen").count(), 1);
    assert.equal(
      calls.filter((cmd) => cmd === "dpiterminalstart").length,
      2,
      "explicit reopen creates exactly one new native session",
    );
    assert.deepEqual(
      stoppedIds,
      ["a".repeat(32)],
      "reopen releases only the previous native owner",
    );
    await Promise.all([
      page.waitForResponse(
        (response) =>
          response.url().endsWith("/index.php") &&
          new URLSearchParams(response.request().postData()).get("cmd") ===
            "dpiterminalstop",
      ),
      page.getByRole("button", { name: "Close", exact: true }).last().click(),
    ]);
    await page.waitForFunction(() => !document.querySelector(".xterm"));
    assert.deepEqual(
      stoppedIds,
      ["a".repeat(32), "b".repeat(32)],
      "closing disposes the replacement owned native session",
    );
    assert.deepEqual(errors, []);
    assert.deepEqual(consoleErrors, []);
    console.log(
      `PASS real xterm ${viewport.width}x${viewport.height}: single DOM/session, StrictMode, state polling, help/reports, resize, input, explicit reopen and cleanup`,
    );
    await page.close();
  }
} finally {
  await browser?.close();
  if (server) await new Promise((resolve) => server.close(resolve));
  await rm(dir, { recursive: true, force: true });
}

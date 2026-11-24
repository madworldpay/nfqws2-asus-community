import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { build } from "../webui/web/node_modules/esbuild/lib/main.js";
const { chromium } = await import(
  process.env.NFQWS_PLAYWRIGHT_MODULE || "playwright"
);
const web = fileURLToPath(new URL("../webui/web/", import.meta.url));
let browser, server;
try {
  const bundle = await build({
    stdin: {
      resolveDir: web,
      loader: "tsx",
      contents: `
    import React from'react';import{createRoot}from'react-dom/client';
    import{Layout}from'./src/components/Layout';import{MtprotoInstallDialog}from'./src/components/MtprotoInstallDialog';
    createRoot(document.getElementById('root')).render(<Layout><MtprotoInstallDialog onClose={()=>{}} csrfToken="fixture"/></Layout>);
  `,
    },
    bundle: true,
    platform: "browser",
    format: "iife",
    write: false,
    jsx: "automatic",
    tsconfig: web + "tsconfig.app.json",
    logLevel: "silent",
    loader: { ".sh": "text", ".py": "text" },
  });
  server = createServer((req, res) => {
    if (req.method === "POST") {
      res.setHeader("Content-Type", "application/json");
      res.end(JSON.stringify({ router: "192.0.2.1", docker: "192.0.2.2" }));
      return;
    }
    res.setHeader(
      "Content-Type",
      req.url === "/fixture.js" ? "text/javascript" : "text/html",
    );
    res.end(
      req.url === "/fixture.js"
        ? bundle.outputFiles[0].contents
        : '<!doctype html><html><body><div id="root"></div><script src="/fixture.js"></script></body></html>',
    );
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  browser = await chromium.launch({
    headless: true,
    ...(process.env.NFQWS_CHROMIUM_EXECUTABLE
      ? { executablePath: process.env.NFQWS_CHROMIUM_EXECUTABLE }
      : {}),
  });
  for (const lang of ["ru", "en"]) {
    const page = await browser.newPage();
    page.setDefaultTimeout(4000);
    await page.addInitScript(
      (language) => localStorage.setItem("lang", JSON.stringify(language)),
      lang,
    );
    const ru = lang === "ru";
    await page.goto(`http://127.0.0.1:${server.address().port}/`);
    const secretLabel = ru ? "Секрет" : "Secret";
    const freshKey = await page
      .getByLabel(secretLabel, { exact: true })
      .inputValue();
    await page
      .getByRole("button", { name: ru ? "Обновить" : "Update", exact: true })
      .click();
    assert.equal(
      await page.getByLabel(secretLabel, { exact: true }).count(),
      0,
      "update must not present a newly generated key as the installed secret",
    );
    assert.equal(
      await page
        .getByLabel(ru ? "TCP-порт" : "TCP port", { exact: true })
        .count(),
      0,
    );
    const checkScript = async (method) => {
      const script = await page
        .getByLabel(ru ? "Команда установки" : "Installation command", {
          exact: true,
        })
        .inputValue();
      assert.ok(script.includes(`NFQWS_MT_METHOD='${method}'`));
      assert.ok(script.includes("NFQWS_MT_ACTION='update'"));
      assert.equal(
        script.includes(freshKey.slice(2)),
        false,
        "update command has no candidate secret capable of replacing the installed one",
      );
      assert.equal(
        await page
          .getByLabel(ru ? "Ссылка подключения" : "Connection link", {
            exact: true,
          })
          .count(),
        0,
        "only the installer can report the preserved connection values",
      );
      const downloaded = page.waitForEvent("download");
      await page
        .getByRole("button", {
          name: ru ? "Скачать скрипт .sh" : "Download .sh script",
          exact: true,
        })
        .click();
      const file = await downloaded;
      assert.equal(
        file.suggestedFilename(),
        `nfqws-mtproto-${method}.sh`,
        "an update shell is never named compose.yaml",
      );
      assert.equal(await readFile(await file.path(), "utf8"), script);
    };
    await checkScript("entware");
    await page
      .getByRole("button", {
        name: ru ? "С Docker" : "With Docker",
        exact: true,
      })
      .click();
    assert.equal(
      await page
        .getByLabel(ru ? "Конфигурация Portainer" : "Portainer configuration", {
          exact: true,
        })
        .count(),
      0,
      "updating an existing stack must not offer fresh compose credentials",
    );
    await page
      .getByLabel(
        ru
          ? "Образ для обновления существующего стека"
          : "Image for updating an existing stack",
        { exact: true },
      )
      .waitFor();
    await page
      .getByRole("button", { name: ru ? "Терминал" : "Terminal", exact: true })
      .click();
    await checkScript("docker");
    await page
      .getByRole("button", {
        name: ru ? "Без Docker" : "Without Docker",
        exact: true,
      })
      .click();
    await page
      .getByRole("combobox", {
        name: ru ? "Устройство" : "Device",
        exact: true,
      })
      .click();
    await page
      .getByRole("option", { name: "Linux / systemd", exact: true })
      .click();
    await page
      .getByLabel(ru ? "Адрес сервера Linux" : "Linux server address", {
        exact: true,
      })
      .fill("proxy.example.org");
    await checkScript("linux");
    await page
      .getByRole("button", { name: ru ? "Установить" : "Install", exact: true })
      .click();
    assert.equal(
      await page.getByLabel(secretLabel, { exact: true }).inputValue(),
      freshKey,
      "returning to fresh install reuses its one generated draft key",
    );
    await page.close();
    console.log(
      `PASS ${lang}: panel update preserves installed connection authority for Entware/Linux/Docker/Portainer; fresh install keeps one draft key`,
    );
  }
} finally {
  await browser?.close();
  if (server) await new Promise((resolve) => server.close(resolve));
}

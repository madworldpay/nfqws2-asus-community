import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { build } from "../webui/web/node_modules/esbuild/lib/main.js";

assert.ok(
  existsSync(
    new URL("../webui/web/src/utils/arkReadiness.ts", import.meta.url),
  ),
  "Explicit ARK readiness classification is missing",
);
const { classifyArkReadiness, normalizeArkDiagnostics } =
  await import("../webui/web/src/utils/arkReadiness.ts");
const keys = [
  "ark_qoe_enable",
  "ark_iam_enable",
  "ark_limiter_enable",
  "ark_log_enable",
  "ark_hyqos_enable",
  "ark_mals_enable",
  "ark_adblock_enable",
  "ark_tracker_enable",
  "ark_ids_enable",
];
const snapshot = (changes = {}) => ({
  status: 0,
  model: "GT-BE19000AI",
  ready: true,
  revision: "test-revision",
  backup: null,
  ark_loaded: false,
  flags: keys.map((key) => ({
    key,
    present: true,
    value: "0",
    enabled: false,
  })),
  diagnostics: {
    ark: { present: "present", loaded: "unloaded" },
    nfqueue: { queue_number: 300, state: "bound", sequence: 0 },
    process_running: true,
  },
  ...changes,
});

const ready = classifyArkReadiness(snapshot());
assert.equal(ready.result, "ready");
assert.equal(ready.disabled, 9);
assert.equal(ready.enabled, 0);
assert.equal(ready.unknown, 0);
assert.equal(ready.runtime, "unloaded");
assert.ok(ready.flags.every((flag) => flag.state === "disabled"));
assert.equal(
  classifyArkReadiness(snapshot({ ark_loaded: true, diagnostics: undefined }))
    .result,
  "reboot_required",
);
assert.equal(
  classifyArkReadiness(snapshot({ ark_loaded: null, diagnostics: undefined }))
    .result,
  "runtime_unknown",
);
assert.equal(
  classifyArkReadiness(
    snapshot({
      ark_loaded: false,
      diagnostics: { ark: { present: "present", loaded: "loaded" } },
    }),
  ).result,
  "runtime_unknown",
);

const active = snapshot();
active.flags[0] = { ...active.flags[0], value: "1", enabled: true };
const activeResult = classifyArkReadiness(active);
assert.equal(activeResult.result, "flags_enabled");
assert.equal(activeResult.enabled, 1);
assert.equal(activeResult.disabled, 8);

const negative = snapshot();
negative.flags[0] = { ...negative.flags[0], value: "-1", enabled: true };
assert.equal(classifyArkReadiness(negative).result, "flags_enabled");
assert.equal(classifyArkReadiness(negative).enabled, 1);
assert.equal(classifyArkReadiness(negative).flags[0].state, "enabled");
const negativeZero = snapshot();
negativeZero.flags[0] = { ...negativeZero.flags[0], value: "-0" };
assert.equal(classifyArkReadiness(negativeZero).result, "ready");

for (const flag of [
  { present: false, value: "", enabled: false },
  { present: true, value: "", enabled: false },
  { present: true, value: "garbage", enabled: false },
  { present: true, value: "0", enabled: true },
  { present: true, value: "1", enabled: false },
  { present: true, value: "0.1", enabled: false },
  { present: true, value: "00000000000", enabled: false },
  { present: true, value: "0\n", enabled: false },
  { present: true, value: "0", enabled: undefined },
]) {
  const data = snapshot();
  data.flags[0] = { key: keys[0], ...flag };
  const result = classifyArkReadiness(data);
  assert.equal(result.result, "flags_unknown");
  assert.equal(result.disabled, 8);
  assert.equal(result.unknown, 1);
  assert.equal(result.flags[0].state, "unknown");
}
const missing = snapshot();
missing.flags.pop();
assert.equal(classifyArkReadiness(missing).result, "flags_unknown");
assert.equal(classifyArkReadiness(missing).unknown, 1);
const duplicate = snapshot();
duplicate.flags[8] = { ...duplicate.flags[0] };
assert.equal(classifyArkReadiness(duplicate).result, "flags_unknown");
assert.equal(classifyArkReadiness(duplicate).unknown, 2);
for (const data of [
  undefined,
  null,
  {},
  { status: 1, error: "stale" },
  snapshot({ flags: null }),
  snapshot({ flags: [{}] }),
  snapshot({ flags: [...snapshot().flags, { key: "unexpected" }] }),
]) {
  assert.equal(classifyArkReadiness(data).result, "unavailable");
}
assert.equal(
  classifyArkReadiness(
    snapshot({ ark_loaded: "false", diagnostics: undefined }),
  ).result,
  "runtime_unknown",
);
assert.equal(
  classifyArkReadiness(
    snapshot({
      diagnostics: { ark: { present: "absent", loaded: "unloaded" } },
    }),
  ).result,
  "ready",
);
assert.equal(
  classifyArkReadiness(
    snapshot({
      diagnostics: { ark: { present: "invalid", loaded: "unloaded" } },
    }),
  ).result,
  "runtime_unknown",
);
const malformedPresence = snapshot({
  diagnostics: { ark: { present: { toString: null }, loaded: "unloaded" } },
});
assert.doesNotThrow(() => classifyArkReadiness(malformedPresence));
assert.equal(classifyArkReadiness(malformedPresence).result, "runtime_unknown");

assert.equal(
  typeof normalizeArkDiagnostics,
  "function",
  "Diagnostic display normalization is missing",
);
const unknownDiagnostics = {
  ark: { present: "unknown", loaded: "unknown" },
  nfqueue: { queue_number: null, state: "unknown", sequence: null },
  process_running: null,
};
assert.deepEqual(
  normalizeArkDiagnostics(snapshot().diagnostics),
  snapshot().diagnostics,
);
assert.deepEqual(normalizeArkDiagnostics({}), unknownDiagnostics);
assert.deepEqual(
  normalizeArkDiagnostics({
    ark: { present: { toString: null }, loaded: { toString: null } },
    nfqueue: {
      queue_number: { toString: null },
      state: { toString: null },
      sequence: { toString: null },
    },
    process_running: "false",
  }),
  unknownDiagnostics,
);
assert.deepEqual(
  normalizeArkDiagnostics({
    ark: null,
    nfqueue: { queue_number: -1, state: "invalid", sequence: 4294967296 },
    process_running: 1,
  }),
  unknownDiagnostics,
);
assert.deepEqual(
  normalizeArkDiagnostics({
    nfqueue: { queue_number: 65535, state: "bound", sequence: 4294967295 },
    process_running: false,
  }),
  {
    ...unknownDiagnostics,
    nfqueue: { queue_number: 65535, state: "bound", sequence: 4294967295 },
    process_running: false,
  },
);
assert.equal(normalizeArkDiagnostics(undefined), undefined);

// Render the actual summary shown at the top of ArkDialog in each locale.
const temporary = await mkdtemp(join(tmpdir(), "nfqws-ark-readiness-"));
try {
  const outfile = join(temporary, "render.cjs");
  await build({
    stdin: {
      resolveDir: fileURLToPath(new URL("../webui/web/", import.meta.url)),
      contents: String.raw`
        import { createElement } from 'react';
        import { renderToStaticMarkup } from 'react-dom/server';
        import { ArkReadinessSummary, ArkDiagnosticsTable, ArkFlagsTable } from '@/components/ArkDialog';
        import { TranslationContext } from '@/context/TranslationContext';
        import { classifyArkReadiness } from '@/utils/arkReadiness';
        import en from '@/translations/en.json';
        import ru from '@/translations/ru.json';

        function renderComponent(Component, props, language) {
          const pack = language === 'ru' ? ru : en;
          const t = (path, params = {}) => path.split('.').reduce((value, key) => value[key], pack)
            .replace(/\{\{(\w+)}}/g, (_, key) => String(params[key]));
          return renderToStaticMarkup(createElement(TranslationContext.Provider,
            { value: { t, langcode: language, setLanguage() {} } },
            createElement(Component, props)));
        }
        export function renderReadiness(status, language, checking = false) {
          return renderComponent(ArkReadinessSummary, { readiness: classifyArkReadiness(status), checking }, language);
        }
        export function renderDiagnostics(diagnostics, language) {
          return renderComponent(ArkDiagnosticsTable, { diagnostics }, language);
        }
        export function renderFlags(status, language) {
          return renderComponent(ArkFlagsTable, { flags: classifyArkReadiness(status).flags }, language);
        }
      `,
    },
    tsconfig: fileURLToPath(
      new URL("../webui/web/tsconfig.app.json", import.meta.url),
    ),
    define: {
      "window.location.origin": '"http://localhost"',
      "process.env.APP_VERSION": '"0.1.4"',
    },
    bundle: true,
    platform: "node",
    format: "cjs",
    outfile,
    logLevel: "silent",
  });
  const { renderReadiness, renderDiagnostics, renderFlags } = await import(
    pathToFileURL(outfile).href
  );
  const visible = (markup) =>
    markup
      .replace(/<style[^>]*>[\s\S]*?<\/style>/g, "")
      .replace(/<[^>]+>/g, "");
  const readyMarkup = renderReadiness(snapshot(), "ru");
  assert.match(readyMarkup, /MuiAlert-standardSuccess/);
  assert.match(
    visible(readyMarkup),
    /Все 9 функций ARK выключены, модуль ARK не загружен/,
  );
  assert.match(
    visible(readyMarkup),
    /Приём пакетов и обход проверьте отдельно/,
  );
  const rebootMarkup = renderReadiness(
    snapshot({ ark_loaded: true, diagnostics: undefined }),
    "ru",
  );
  assert.match(rebootMarkup, /MuiAlert-standardWarning/);
  assert.match(visible(rebootMarkup), /Перезагрузите ASUS вручную/);
  assert.match(visible(rebootMarkup), /Проверить ARK/);
  assert.match(
    visible(renderReadiness(missing, "ru")),
    /Подтверждено выключение 8 из 9/,
  );
  // Missing NVRAM keys do not make a confirmed unloaded runtime alarming.
  for (const language of ["ru", "en"]) {
    const clearRuntime = renderReadiness(missing, language);
    assert.match(clearRuntime, /MuiAlert-standardSuccess/);
    assert.doesNotMatch(clearRuntime, /MuiAlert-standardWarning/);
    assert.doesNotMatch(
      visible(clearRuntime),
      /Повторите проверку|Repeat the check|not confirmed/i,
    );
    assert.match(
      visible(clearRuntime),
      language === "ru" ? /Модуль ARK не загружен/ : /ARK module is not loaded/,
    );
    assert.match(visible(clearRuntime), /8/);
  }
  const uncertainMissing = {
    ...missing,
    ark_loaded: null,
    diagnostics: undefined,
  };
  assert.match(
    renderReadiness(uncertainMissing, "ru"),
    /MuiAlert-standardWarning/,
  );
  const conflictingMissing = {
    ...missing,
    diagnostics: { ark: { present: "present", loaded: "loaded" } },
  };
  assert.match(
    renderReadiness(conflictingMissing, "en"),
    /MuiAlert-standardWarning/,
  );
  assert.match(
    visible(renderReadiness(active, "ru")),
    /Включены функции ARK: 1 из 9/,
  );
  assert.match(
    visible(
      renderReadiness(
        snapshot({ ark_loaded: null, diagnostics: undefined }),
        "en",
      ),
    ),
    /module state is unknown/,
  );
  const refreshing = renderReadiness(snapshot(), "ru", true);
  assert.match(refreshing, /MuiAlert-standardInfo/);
  assert.doesNotMatch(visible(refreshing), /Подготовка подтверждена/);
  assert.match(
    visible(renderReadiness({ status: 1, error: "stale" }, "ru")),
    /Нет актуальных данных/,
  );
  assert.match(
    visible(renderReadiness(negative, "ru")),
    /Включены функции ARK: 1 из 9/,
  );
  const malformedDiagnostics = {
    ark: { present: { toString: null }, loaded: { toString: null } },
    nfqueue: {
      queue_number: { toString: null },
      state: { toString: null },
      sequence: { toString: null },
    },
    process_running: "false",
  };
  const unknownTable = visible(renderDiagnostics(malformedDiagnostics, "ru"));
  assert.equal(unknownTable.match(/Неизвестно/g)?.length, 6);
  assert.doesNotMatch(unknownTable, /__MISSING__/);
  assert.equal(
    visible(renderDiagnostics({}, "en")).match(/Unknown/g)?.length,
    6,
  );
  assert.match(
    visible(renderDiagnostics(snapshot().diagnostics, "ru")),
    /Запущен/,
  );
  const unloadedTable = renderDiagnostics(snapshot().diagnostics, "ru");
  assert.match(unloadedTable, /MuiSvgIcon-colorSuccess/);
  assert.match(unloadedTable, /CheckCircleOutlineIcon/);
  const processRow = (table) =>
    table
      .match(/<tr\b[^>]*>[\s\S]*?<\/tr>/g)
      .find((row) => /Процесс NFQWS2|NFQWS2 process/.test(row));
  assert.match(processRow(unloadedTable), /MuiSvgIcon-colorSuccess/);
  for (const process_running of [false, null]) {
    assert.doesNotMatch(
      processRow(
        renderDiagnostics({ ...snapshot().diagnostics, process_running }, "ru"),
      ),
      /MuiSvgIcon-colorSuccess/,
    );
  }
  for (const loaded of ["loaded", "unknown"]) {
    const table = renderDiagnostics(
      {
        ...snapshot().diagnostics,
        ark: { present: "present", loaded },
        process_running: false,
        nfqueue: { queue_number: 300, state: "unbound", sequence: 0 },
      },
      "en",
    );
    assert.doesNotMatch(table, /MuiSvgIcon-colorSuccess/);
    assert.doesNotMatch(table, /CheckCircleOutlineIcon/);
  }
  const rowNamed = (table, name) =>
    table
      .match(/<tr\b[^>]*>[\s\S]*?<\/tr>/g)
      .find((row) => visible(row).includes(name));
  const activeQueue = {
    ...snapshot().diagnostics,
    nfqueue: { queue_number: 300, state: "bound", sequence: 7 },
  };
  const receptionTable = renderDiagnostics(activeQueue, "ru");
  assert.match(
    rowNamed(receptionTable, "Привязка очереди"),
    /MuiSvgIcon-colorSuccess/,
  );
  assert.match(
    rowNamed(receptionTable, "Счётчик принятых пакетов"),
    /MuiSvgIcon-colorSuccess/,
  );
  assert.doesNotMatch(
    rowNamed(unloadedTable, "Счётчик принятых пакетов"),
    /MuiSvgIcon-colorSuccess/,
  );
  const absentArk = {
    ...snapshot().diagnostics,
    ark: { present: "absent", loaded: "unloaded" },
  };
  assert.match(
    rowNamed(renderDiagnostics(absentArk, "ru"), "ARK в прошивке"),
    /MuiSvgIcon-colorSuccess/,
  );
  assert.equal(
    (
      renderFlags(snapshot(), "ru").match(
        /data-testid="CheckCircleOutlineIcon"/g,
      ) ?? []
    ).length,
    9,
  );
  assert.equal(
    (
      renderFlags(missing, "en").match(
        /data-testid="CheckCircleOutlineIcon"/g,
      ) ?? []
    ).length,
    8,
  );
  assert.equal(
    (
      renderFlags({ status: 1 }, "ru").match(
        /data-testid="CheckCircleOutlineIcon"/g,
      ) ?? []
    ).length,
    0,
  );
} finally {
  await rm(temporary, { recursive: true, force: true });
}
console.log(
  "PASS: explicit ARK readiness and real RU/EN summaries; incomplete/malformed/stale snapshots fail closed",
);

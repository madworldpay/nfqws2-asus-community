import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";
import { build } from "../webui/web/node_modules/esbuild/lib/main.js";

const dir = await mkdtemp(join(tmpdir(), "nfqws-config-settings-"));
try {
  await build({
    entryPoints: [
      fileURLToPath(
        new URL("../webui/web/src/utils/configParser.ts", import.meta.url),
      ),
    ],
    outfile: join(dir, "config.mjs"),
    bundle: true,
    platform: "node",
    format: "esm",
    logLevel: "silent",
  });
  const api = await import(pathToFileURL(join(dir, "config.mjs")));
  assert.equal(
    typeof api.resetStrategyConfig,
    "function",
    "the strategy reset must use the package template",
  );
  assert.equal(typeof api.changedConfigKeys, "function");
  assert.equal(typeof api.configSectionStarts, "function");

  const template =
    'NFQWS_ARGS="--default-tcp"\nNFQWS_ARGS_QUIC="--default-quic"\nNFQWS_ARGS_UDP="--default-udp"\nNFQWS_ARGS_CUSTOM=""\n';
  const original =
    '# keep this comment\nISP_INTERFACE="eth0"\nNFQWS_BASE_ARGS="$LOCAL_STARTUP"\nNFQWS_ARGS="old tcp"\nNFQWS_ARGS_QUIC="old quic"\nNFQWS_ARGS_UDP="old udp"\nNFQWS_ARGS_CUSTOM="custom first"\nMODE_ALL="--hostlist-exclude=custom.list"\nNFQWS_EXTRA_ARGS="$MODE_ALL"\nTCP_PORTS=""\nUDP_PORTS="443,123"\nASUS_CLIENT_MODE="include"\nASUS_CLIENTS4="192.0.2.4"\nASUS_CLIENTS6="2001:db8::4"\nIPV6_ENABLED=1\nUNRELATED="untouched"\n';
  const baseline = api.parseConfig(original);
  const form = { ...baseline, ISP_INTERFACE: "ppp0" };
  const reset = api.resetStrategyConfig(form, template);
  assert.deepEqual(reset, {
    ...form,
    NFQWS_ARGS: "--default-tcp",
    NFQWS_ARGS_QUIC: "--default-quic",
    NFQWS_ARGS_UDP: "--default-udp",
    NFQWS_ARGS_CUSTOM: "",
  });
  assert.equal(
    form.NFQWS_ARGS_CUSTOM,
    "custom first",
    "reset does not mutate the current form",
  );
  for (const mode of ["MODE_AUTO", "MODE_LIST", "MODE_ALL"]) {
    assert.equal(
      api.resetStrategyConfig({ ...form, NFQWS_EXTRA_ARGS: mode }, template)
        .NFQWS_EXTRA_ARGS,
      mode,
    );
  }
  const packageTemplate = await readFile(
    new URL("../core/etc/nfqws2/nfqws2.conf", import.meta.url),
    "utf8",
  );
  const stock = api.resetStrategyConfig(form, packageTemplate);
  assert.match(stock.NFQWS_ARGS, /--filter-tcp=443,80,1984,5222/);
  assert.match(stock.NFQWS_ARGS_QUIC, /--filter-udp=443/);
  assert.match(
    stock.NFQWS_ARGS_UDP,
    /--filter-l7=wireguard,stun,discord,mtproto,unknown/,
  );
  assert.equal(stock.NFQWS_ARGS_CUSTOM, "");
  const saved = api.formatConfig(
    original,
    reset,
    api.changedConfigKeys(baseline, reset),
  );
  const multiline =
    'NFQWS_BASE_ARGS="--first\nNFQWS_ARGS=inside-another-value\n--last"\nNFQWS_ARGS="old"\n';
  assert.equal(
    api.formatConfig(
      multiline,
      { ...api.parseConfig(multiline), NFQWS_ARGS: "--default-tcp" },
      ["NFQWS_ARGS"],
    ),
    'NFQWS_BASE_ARGS="--first\nNFQWS_ARGS=inside-another-value\n--last"\nNFQWS_ARGS="--default-tcp"\n',
    "saving one strategy cannot rewrite an apparent assignment inside another value",
  );
  const escaped =
    'NFQWS_BASE_ARGS="--name=\\"quoted\\"\nNFQWS_ARGS=inside-another-value\n--last"\nNFQWS_ARGS="old"\n';
  assert.equal(
    api.formatConfig(
      escaped,
      { ...api.parseConfig(escaped), NFQWS_ARGS: "--default-tcp" },
      ["NFQWS_ARGS"],
    ),
    'NFQWS_BASE_ARGS="--name=\\"quoted\\"\nNFQWS_ARGS=inside-another-value\n--last"\nNFQWS_ARGS="--default-tcp"\n',
    "escaped quotes cannot end a preserved multiline value",
  );
  for (const prefix of [
    "UNRELATED=prefix\\\nNFQWS_ARGS=inside-unrelated\n",
    "UNRELATED='prefix'\"open\nNFQWS_ARGS=inside-unrelated\nend\"\n",
    'UNRELATED=#"open\nNFQWS_ARGS=inside-unrelated\nend"\n',
    'UNKNOWN= # ordinary comment with an unmatched "\n',
  ]) {
    const source =
      prefix +
      'NFQWS_ARGS="old tcp"\nNFQWS_ARGS_QUIC="old quic"\nNFQWS_ARGS_UDP="old udp"\nNFQWS_ARGS_CUSTOM="custom first"\n';
    const before = api.parseConfig(source);
    const next = api.resetStrategyConfig(before, template);
    const output = api.formatConfig(
      source,
      next,
      api.changedConfigKeys(before, next),
    );
    assert.equal(
      output,
      prefix +
        'NFQWS_ARGS="--default-tcp"\nNFQWS_ARGS_QUIC="--default-quic"\nNFQWS_ARGS_UDP="--default-udp"\nNFQWS_ARGS_CUSTOM=""\n',
      "strategy reset preserves shell continuations and concatenated quoted values in other fields",
    );
  }
  assert.equal(
    saved,
    '# keep this comment\nISP_INTERFACE="ppp0"\nNFQWS_BASE_ARGS="$LOCAL_STARTUP"\nNFQWS_ARGS="--default-tcp"\nNFQWS_ARGS_QUIC="--default-quic"\nNFQWS_ARGS_UDP="--default-udp"\nNFQWS_ARGS_CUSTOM=""\nMODE_ALL="--hostlist-exclude=custom.list"\nNFQWS_EXTRA_ARGS="$MODE_ALL"\nTCP_PORTS=""\nUDP_PORTS="443,123"\nASUS_CLIENT_MODE="include"\nASUS_CLIENTS4="192.0.2.4"\nASUS_CLIENTS6="2001:db8::4"\nIPV6_ENABLED=1\nUNRELATED="untouched"\n',
  );
  for (const invalid of [
    "",
    template.replace('NFQWS_ARGS_UDP="--default-udp"\n', ""),
    template.replace('"--default-quic"', '""'),
    template + 'UNFINISHED="',
  ]) {
    assert.throws(
      () => api.resetStrategyConfig(form, invalid),
      /default_strategy_unavailable/,
    );
    assert.equal(form.NFQWS_ARGS_CUSTOM, "custom first");
  }
  const missing = 'ISP_INTERFACE=""\nNFQWS_EXTRA_ARGS="$MODE_LIST"\n';
  const added = api.resetStrategyConfig(api.parseConfig(missing), template);
  const appended = api.formatConfig(
    missing,
    added,
    api.changedConfigKeys(api.parseConfig(missing), added),
  );
  assert.equal(
    api.parseConfig(appended).NFQWS_ARGS,
    "--default-tcp",
    "reset also restores a strategy removed from an imported config",
  );
  assert.equal(api.parseConfig(appended).NFQWS_ARGS_QUIC, "--default-quic");
  assert.equal(api.parseConfig(appended).NFQWS_ARGS_UDP, "--default-udp");
  assert.equal(api.parseConfig(appended).NFQWS_EXTRA_ARGS, "MODE_LIST");
  const defaults = api.parseConfig(template);
  assert.deepEqual(
    api.changedConfigKeys(
      defaults,
      api.resetStrategyConfig(defaults, template),
    ),
    [],
    "already-default strategies do not create a dirty form",
  );
  assert.deepEqual(
    api.changedConfigKeys(
      defaults,
      api.resetStrategyConfig({ ...defaults, ISP_INTERFACE: "eth2" }, template),
    ),
    ["ISP_INTERFACE"],
    "an unrelated pending edit stays dirty",
  );

  const source =
    '# WAN\nISP_INTERFACE=""\n\n# Startup\nNFQWS_BASE_ARGS="--one\nTCP_PORTS=inside-value\n--two"\n\n# TCP\nNFQWS_ARGS="--filter-tcp=443"\n\n# Modes\nMODE_LIST="--hostlist=user.list"\nMODE_ALL="--hostlist-exclude=exclude.list"\nNFQWS_EXTRA_ARGS="$MODE_ALL"\n\n# Ports\nTCP_PORTS="443"\nUDP_PORTS="443"\n';
  const starts = api.configSectionStarts(source);
  assert.deepEqual(
    starts.map((p) => source.slice(p).split("\n")[0]),
    ["# WAN", "# Startup", "# TCP", "# Modes", "# Ports"],
  );
  assert.deepEqual(
    api.configSectionStarts(
      'NFQWS_ARGS="unterminated\nTCP_PORTS=inside-value\n',
    ),
    [0],
  );
  const web = fileURLToPath(new URL("../webui/web/", import.meta.url));
  await build({
    stdin: {
      contents:
        "export { EditorState } from '@codemirror/state'; export { configSectionSpacing } from './src/utils/configSectionSpacing.ts';",
      resolveDir: web,
      sourcefile: "config-spacing-test.ts",
      loader: "ts",
    },
    tsconfig: join(web, "tsconfig.app.json"),
    outfile: join(dir, "spacing.mjs"),
    bundle: true,
    platform: "node",
    format: "esm",
    logLevel: "silent",
  });
  const { EditorState, configSectionSpacing } = await import(
    pathToFileURL(join(dir, "spacing.mjs"))
  );
  const editor = EditorState.create({
    doc: source,
    extensions: [configSectionSpacing],
  });
  assert.equal(
    editor.field(configSectionSpacing).size,
    4,
    "the raw editor separates major blocks",
  );
  const selected = editor.update({
    selection: { anchor: 0, head: editor.doc.length },
  }).state;
  assert.equal(
    selected.sliceDoc(selected.selection.main.from, selected.selection.main.to),
    source,
    "select all and copy include the whole original text without spacing characters",
  );
  const edited = editor.update({
    changes: { from: 0, insert: "# edit\n" },
  }).state;
  assert.equal(edited.doc.toString(), "# edit\n" + source);
  assert.equal(
    edited.field(configSectionSpacing).size,
    4,
    "spacing follows edits without adding document content",
  );
  console.log(
    "PASS config settings: four strategy defaults, invalid template, pending edits, precise save, missing keys and view-only section positions",
  );
} finally {
  await rm(dir, { recursive: true, force: true });
}

import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import {
  chmod,
  mkdir,
  mkdtemp,
  readFile,
  rm,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { spawn, spawnSync } from "node:child_process";
import { createServer } from "node:net";
import {
  createCipheriv,
  createDecipheriv,
  createHash,
  randomBytes,
} from "node:crypto";
import { createRequire } from "node:module";
import { build } from "../webui/web/node_modules/esbuild/lib/main.js";

const requireWeb = createRequire(
  new URL("../webui/web/package.json", import.meta.url),
);
const { parse: parseYaml } = requireWeb("yaml");
const fixedKey = "0102030405060708090a0b0c0d0e0f10";
async function dockerRuntime(
  script,
  directory,
  mode = "reply",
  existing = false,
) {
  await mkdir(directory);
  await mkdir(join(directory, "proxy"));
  await writeFile(join(directory, "proxy", "__init__.py"), "");
  await writeFile(
    join(directory, "proxy", "_aes.py"),
    "from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes\n",
  );
  const state = join(directory, "state.json");
  await writeFile(state, JSON.stringify({ calls: [], existing }));
  const executable = join(directory, "docker");
  await writeFile(
    executable,
    `#!/usr/bin/python3
import json,os,sys,subprocess
p=os.environ['MTPROTO_FIXTURE_STATE'];s=json.load(open(p));a=sys.argv[1:];s['calls'].append(a);json.dump(s,open(p,'w'))
if a[:2]==['container','inspect']:sys.exit(0 if s['existing'] else 1)
if a[0]=='create':s['created']=a;json.dump(s,open(p,'w'));print('owned-new-container')
elif a[0]=='inspect':print('true')
elif a[0]=='exec':
 i=a.index('owned-new-container');cmd=a[i+1:];cmd[0]=sys.executable
 if '-c' in cmd:
  j=cmd.index('-c');cmd[j+1]=cmd[j+1].replace('1443',os.environ['MTPROTO_FIXTURE_PORT']);cmd[j+2:]=['127.0.0.1',os.environ['MTPROTO_FIXTURE_PORT'],'0.4']
 e=os.environ.copy();e['PROXY_SECRET']='${fixedKey}';e['PYTHONPATH']=os.path.dirname(p)
 sys.exit(subprocess.run(cmd,env=e).returncode)
`,
  );
  await chmod(executable, 0o755);
  const sockets = new Set();
  const server = createServer((socket) => {
    sockets.add(socket);
    socket.on("close", () => sockets.delete(socket));
    if (mode === "blackhole") return;
    let bytes = Buffer.alloc(0),
      decode,
      encode,
      plain = Buffer.alloc(0);
    socket.on("data", (chunk) => {
      bytes = Buffer.concat([bytes, chunk]);
      if (!decode && bytes.length >= 64) {
        const h = bytes.subarray(0, 64),
          k = h.subarray(8, 56),
          rev = Buffer.from(k).reverse();
        decode = createDecipheriv(
          "aes-256-ctr",
          createHash("sha256")
            .update(
              Buffer.concat([k.subarray(0, 32), Buffer.from(fixedKey, "hex")]),
            )
            .digest(),
          k.subarray(32),
        );
        decode.update(h);
        encode = createCipheriv(
          "aes-256-ctr",
          createHash("sha256")
            .update(
              Buffer.concat([
                rev.subarray(0, 32),
                Buffer.from(fixedKey, "hex"),
              ]),
            )
            .digest(),
          rev.subarray(32),
        );
        bytes = bytes.subarray(64);
      }
      if (!decode || !bytes.length) return;
      plain = Buffer.concat([plain, decode.update(bytes)]);
      bytes = Buffer.alloc(0);
      if (plain.length < 44) return;
      const nonce = Buffer.from(plain.subarray(28, 44));
      if (mode === "wrong-nonce") nonce[0] ^= 1;
      const body = Buffer.concat([
        Buffer.from("63241605", "hex"),
        nonce,
        randomBytes(16),
        Buffer.from([8]),
        randomBytes(8),
        Buffer.alloc(3),
        Buffer.from("15c4b51c01000000", "hex"),
        randomBytes(8),
      ]);
      const envelope = Buffer.alloc(20);
      envelope.writeUInt32LE(body.length, 16);
      const payload = Buffer.concat([envelope, body, randomBytes(12)]),
        length = Buffer.alloc(4);
      length.writeUInt32LE(payload.length);
      socket.end(encode.update(Buffer.concat([length, payload])));
    });
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  let result;
  try {
    result = await new Promise((resolve) => {
      const child = spawn("/bin/sh", ["-s"], {
        env: {
          ...process.env,
          PATH: directory + ":" + process.env.PATH,
          MTPROTO_FIXTURE_STATE: state,
          MTPROTO_FIXTURE_PORT: String(server.address().port),
        },
      });
      let stdout = "",
        stderr = "";
      child.stdout.on("data", (b) => (stdout += b));
      child.stderr.on("data", (b) => (stderr += b));
      child.on("close", (status) => resolve({ status, stdout, stderr }));
      // Stub the external Docker boundary before running the artifact: never contact a real daemon.
      const isolated = script.replace(
        "findexe docker >/dev/null",
        "type docker >/dev/null",
      );
      child.stdin.end(
        "sleep() { :; }\ndocker() { " +
          JSON.stringify(executable) +
          ' \"$@\"; }\n' +
          isolated,
      );
    });
  } finally {
    for (const socket of sockets) socket.destroy();
    await new Promise((resolve) => server.close(resolve));
  }
  return { ...result, state: JSON.parse(await readFile(state, "utf8")) };
}

const source = fileURLToPath(
  new URL("../webui/web/src/utils/mtprotoInstall.ts", import.meta.url),
);
assert.ok(existsSync(source), "MTProto install generator is implemented");
const dir = await mkdtemp(join(tmpdir(), "nfqws-mtproto-test-"));
try {
  await build({
    entryPoints: [source],
    outfile: join(dir, "install.mjs"),
    bundle: true,
    platform: "node",
    format: "esm",
    logLevel: "silent",
    loader: { ".sh": "text" },
  });
  const api = await import(pathToFileURL(join(dir, "install.mjs")));
  const bytes = Uint8Array.from({ length: 16 }, (_, i) => i + 1);
  const secret = api.createMtprotoSecret(bytes);
  assert.equal(secret, "dd0102030405060708090a0b0c0d0e0f10");
  assert.notEqual(
    api.createMtprotoSecret(),
    api.createMtprotoSecret(),
    "Fresh secrets use independent secure random bytes",
  );
  assert.throws(() => api.createMtprotoSecret(new Uint8Array(4)));
  assert.equal(
    api.suggestMtprotoServer(
      "entware",
      { router: "192.168.8.1", docker: "192.168.8.20" },
      "router.example.org",
    ),
    "192.168.8.1",
  );
  assert.equal(
    api.suggestMtprotoServer(
      "docker",
      { router: "192.168.8.1", docker: "192.168.8.20" },
      "router.example.org",
    ),
    "192.168.8.20",
  );
  assert.equal(
    api.suggestMtprotoServer(
      "docker",
      { router: null, docker: null },
      "192.168.8.1",
    ),
    "",
  );
  assert.equal(
    api.suggestMtprotoServer(
      "entware",
      { router: null, docker: null },
      "router.example.org",
    ),
    "router.example.org",
  );
  assert.equal(
    api.suggestMtprotoServer(
      "entware",
      { router: null, docker: null },
      "localhost",
    ),
    "",
  );
  assert.equal(
    api.suggestMtprotoServer(
      "entware",
      { router: null, docker: null },
      "127.0.0.1",
    ),
    "",
  );
  const input = { server: "proxy.example.org", port: "8443", secret };
  assert.deepEqual(api.validateMtproto(input), {});
  for (const value of [
    "https://proxy.example.org",
    "host;id",
    "$(id)",
    "a\nb",
    "--help",
    "host:443",
    "user@host",
    "host/path",
    "a..b",
    "a#b",
  ]) {
    assert.ok(
      api.validateMtproto({ ...input, server: value }).server,
      "Reject unsafe host: " + JSON.stringify(value),
    );
  }
  for (const value of ["0", "65536", "443;id", "1e3", "-1", "443\n", ""]) {
    assert.ok(
      api.validateMtproto({ ...input, port: value }).port,
      "Reject invalid port: " + JSON.stringify(value),
    );
  }
  assert.ok(api.validateMtproto({ ...input, secret: secret + "';id" }).secret);
  for (const host of [
    "203.0.113.10",
    "proxy.example.org",
    "2001:db8::1",
    "[2001:db8::1]",
  ]) {
    const values = { ...input, server: host };
    assert.deepEqual(api.validateMtproto(values), {});
    const url = new URL(api.mtprotoLink(values));
    assert.equal(url.origin, "https://t.me");
    assert.equal(url.pathname, "/proxy");
    assert.equal(url.searchParams.get("server"), host.replace(/^\[|\]$/g, ""));
    assert.equal(url.searchParams.get("port"), "8443");
    assert.equal(url.searchParams.get("secret"), secret);
  }
  for (const method of ["docker", "entware", "linux"]) {
    const script = api.buildMtprotoInstall(method, input, "ru");
    assert.equal(
      spawnSync("/bin/sh", ["-n"], { input: script }).status,
      0,
      method + " is valid POSIX shell",
    );
    assert.ok(
      script.includes(secret.slice(2)),
      "Configuration contains displayed secret",
    );
    assert.ok(
      script.includes(api.mtprotoLink(input)),
      "Installer prints the same connection link",
    );
    assert.ok(
      !/curl\s+[^|\n]*\|\s*(?:sh|bash)/.test(script),
      "No execution of an unverified downloaded installer",
    );
    assert.ok(
      !/iptables|nvram|ufw|firewall-cmd/.test(script),
      "No unsolicited changes to firewall or router configuration",
    );
    assert.throws(() =>
      api.buildMtprotoInstall(method, { ...input, server: "host;id" }, "ru"),
    );
    const path = join(dir, method + ".sh");
    await writeFile(path, script);
    if (process.env.NFQWS_MTPROTO_SCRIPTS)
      await writeFile(
        join(process.env.NFQWS_MTPROTO_SCRIPTS, method + ".sh"),
        script,
      );
  }
  for (const method of ["entware", "linux"])
    assert.throws(
      () => api.buildMtprotoInstall(method, { ...input, port: "443" }, "en"),
      "Unprivileged native service rejects reserved ports",
    );
  const docker = api.buildMtprotoInstall("docker", input, "en");
  assert.ok(docker.includes("docker pull"));
  assert.ok(!docker.includes("docker build"));
  assert.ok(docker.includes(api.MTPROTO_DOCKER_IMAGE));
  assert.ok(docker.includes("PROXY_SECRET=$NFQWS_MT_KEY"));

  // A local listener without Telegram's nonce-bearing response must never commit.
  const good = await dockerRuntime(docker, join(dir, "docker-good"));
  assert.equal(
    good.status,
    0,
    "A verified upstream fixture must start successfully: " + good.stderr,
  );
  const definition = parseYaml(api.buildMtprotoCompose(input)).services.mtproto;
  assert.ok(
    Array.isArray(definition.entrypoint),
    "Override the pinned image entrypoint: its default set -- discards Docker Cmd",
  );
  const created = good.state.created;
  const imageIndex = created.indexOf(api.MTPROTO_DOCKER_IMAGE);
  const dockerEntrypoint = created[created.indexOf("--entrypoint") + 1];
  const dockerCommand = [dockerEntrypoint, ...created.slice(imageIndex + 1)];
  const composeExpand = (value) =>
    value.replace(/\$\$|\$[A-Za-z_][A-Za-z0-9_]*/g, (token) =>
      token === "$$" ? "$" : "HOST_ENV_MUST_NOT_REPLACE_CONTAINER_ENV",
    );
  assert.deepEqual(
    dockerCommand,
    [...definition.entrypoint, ...definition.command.map(composeExpand)],
    "Docker and Compose must override the image entrypoint identically; Cmd alone is ignored by the pinned image",
  );
  const launch = dockerCommand.at(-1);
  const spy = join(dir, "python-spy");
  await writeFile(
    spy,
    "#!/usr/bin/python3\nimport sys,json; print(json.dumps(sys.argv[1:]))\n",
  );
  await chmod(spy, 0o755);
  const app = spawnSync(
    "/bin/sh",
    ["-c", launch.replace("/opt/venv/bin/python", spy)],
    {
      env: {
        ...process.env,
        ...definition.environment,
        CFPROXY_DOMAIN: "owner.example.org",
      },
      encoding: "utf8",
    },
  );
  assert.equal(app.status, 0, app.stderr);
  const appArgs = JSON.parse(app.stdout);
  assert.ok(
    appArgs.includes("--no-secure"),
    "Use the verified WS port-80 route, without changing HTTPS certificate verification",
  );
  assert.equal(
    appArgs[appArgs.indexOf("--cfproxy-domain") + 1],
    "owner.example.org",
    "The owner can override the existing CF relay through ENV",
  );
  assert.equal(appArgs[appArgs.indexOf("--secret") + 1], fixedKey);
  assert.equal(definition.environment.CFPROXY_DOMAIN, "pclead.co.uk");
  assert.ok(
    definition.healthcheck?.test?.length,
    "Compose must test genuine upstream readiness",
  );
  const probeExec = good.state.calls.find((a) => a[0] === "exec");
  assert.deepEqual(
    probeExec.slice(probeExec.indexOf("owned-new-container") + 1),
    definition.healthcheck.test.slice(1),
    "Install-time readiness and recurring Compose health checks must run the same probe",
  );
  const health = created[created.indexOf("--health-cmd") + 1];
  const healthArgs = spawnSync(
    "/bin/sh",
    ["-c", health.replace("/opt/venv/bin/python", spy)],
    { encoding: "utf8" },
  );
  assert.equal(healthArgs.status, 0, healthArgs.stderr);
  assert.deepEqual(
    JSON.parse(healthArgs.stdout),
    definition.healthcheck.test.slice(2),
    "Docker health command shell quoting must preserve the exact Python program",
  );

  assert.match(good.stdout, /Telegram.*verified|проверен.*Telegram/i);
  assert.ok(
    !good.state.calls.some((a) => a[0] === "rm"),
    "Successful upstream readiness retains the new container",
  );
  for (const mode of ["blackhole", "wrong-nonce"]) {
    const bad = await dockerRuntime(docker, join(dir, "docker-" + mode), mode);
    assert.notEqual(bad.status, 0, mode + " must fail upstream readiness");
    assert.ok(
      bad.state.calls.some(
        (a) => a[0] === "rm" && a.at(-1) === "owned-new-container",
      ),
      "Only the newly created container is rolled back",
    );
    assert.ok(
      !bad.stdout.includes(api.mtprotoLink(input)),
      "Failed readiness must not print a working-proxy claim/link",
    );
  }
  const occupied = await dockerRuntime(
    docker,
    join(dir, "docker-existing"),
    "reply",
    true,
  );
  assert.notEqual(occupied.status, 0);
  assert.ok(
    !occupied.state.calls.some((a) => ["create", "start", "rm"].includes(a[0])),
    "Existing services must be left untouched",
  );

  const compose = api.buildMtprotoCompose(input);
  assert.ok(compose.includes(api.MTPROTO_DOCKER_IMAGE));
  assert.ok(
    compose.includes("PROXY_SECRET: " + JSON.stringify(secret.slice(2))),
  );
  assert.ok(compose.includes(JSON.stringify(input.port + ":1443")));
  assert.ok(!compose.includes("privileged: true"));
  assert.throws(() => api.buildMtprotoCompose({ ...input, secret: "bad" }));
  assert.ok(docker.includes("Flowseal/tg-ws-proxy"));
  assert.ok(docker.includes("docker info"));
  assert.ok(docker.includes("docker create"));
  assert.ok(docker.includes("docker start"));
  assert.ok(docker.includes("unless-stopped"));
  const linux = api.buildMtprotoInstall("linux", input, "en");
  assert.ok(
    linux.includes(
      "87a38c235d7a4a66d8a3fa50d64e42cc962c11c210a9e65df1469302a6521613",
    ),
  );
  assert.ok(
    linux.indexOf("sha256sum -c") < linux.indexOf("tar -x"),
    "Verify source before extracting",
  );
  assert.ok(linux.includes("os.setuid"), "Drop root before importing proxy");
  assert.ok(linux.includes("/run/systemd/system"));
  for (const method of ["docker", "entware", "linux"]) {
    const ru = api.buildMtprotoInstall(method, input, "ru");
    const en = api.buildMtprotoInstall(method, input, "en");
    assert.ok(ru.includes("MTProto"));
    assert.notEqual(ru, en, "Installer feedback is localized");
  }
  console.log(
    "PASS MTProto: secure secret, input/shell injection rejection, IPv4/IPv6 links, matching Docker/native config, pinned verified downloads and POSIX shell",
  );
} finally {
  await rm(dir, { recursive: true, force: true });
}

import installer from './mtproto-install.sh?raw';
import logRedaction from './mtproto-log-redaction.py?raw';

export type MtprotoMethod = 'docker' | 'entware' | 'linux';
export type MtprotoValues = { server: string; port: string; secret: string };
export type MtprotoAddresses = { router: string | null; docker: string | null };

export function suggestMtprotoServer(
  method: MtprotoMethod,
  addresses: MtprotoAddresses,
  panelHost: string,
) {
  const detected =
    method === 'docker'
      ? addresses.docker
      : method === 'entware'
        ? addresses.router
        : null;
  if (detected && validServer(detected)) return detected;
  if (
    method !== 'entware' ||
    panelHost.toLowerCase() === 'localhost' ||
    /^(127|0)\./.test(panelHost) ||
    /^\[?::1\]?$/.test(panelHost)
  )
    return '';
  return validServer(panelHost) ? panelHost : '';
}

// Multi-architecture image used by the reference installation (amd64 / arm64).
export const MTPROTO_DOCKER_IMAGE =
  'lordarrin/tg-ws-proxy@sha256:3561fe079f358a6266bfb7aac6bcd273ef2489c6d6ed7f27d235ca9bcffb3382';

// The pinned image's entrypoint resets argv; override it for the verified WS/80 route.
// pclead.co.uk is already in that image's relay pool. Owners can change the ENV
// value if this relay is unavailable. MTProto payload encryption is unchanged.
export const MTPROTO_DOCKER_LAUNCHER =
  'set -eu; set -- --host "$PROXY_HOST" --port "$PROXY_PORT" --secret "$PROXY_SECRET" --pool-size "$PROXY_POOL_SIZE" --no-secure --cfproxy-domain "$CFPROXY_DOMAIN"; for dc in $PROXY_DC_IPS; do set -- "$@" --dc-ip "$dc"; done; exec /opt/venv/bin/python -u -c ' +
  shellQuote('import os, sys, runpy\nsecret = os.environ["PROXY_SECRET"]\n' + logRedaction + '\nsys.path.insert(0, os.path.abspath("proxy"))\nrunpy.run_path("proxy/tg_ws_proxy.py", run_name="__main__")\n') +
  ' "$@"';

// This asks Telegram for an unauthenticated resPQ and checks its nonce. An open
// listener alone cannot pass. No Telegram account, owner key or nonce is logged.
export const MTPROTO_READINESS = String.raw`import hashlib, json, os, socket, struct, sys, time
root = os.environ.get('NFQWS_MT_PROBE_ROOT')
if root:
    sys.path[:0] = [root + '/app', root + '/app/vendor']
from proxy._aes import Cipher, algorithms, modes
host, port = sys.argv[1], int(sys.argv[2])
budget = float(sys.argv[3])
if not 0.1 <= budget <= 30:
    raise SystemExit('Invalid readiness deadline')
deadline = time.monotonic() + budget
s = None
try:
    secret = bytes.fromhex(os.environ.get('PROXY_SECRET') or os.environ['NFQWS_MT_PROBE_SECRET'])
    if len(secret) != 16:
        raise ValueError('Invalid proxy key')
    while True:
        h = bytearray(os.urandom(64))
        if h[0] not in (0xef, 0x16) and bytes(h[:4]) not in (b'HEAD', b'POST', b'GET ', b'\xee' * 4, b'\xdd' * 4) and h[4:8] != b'\x00' * 4:
            break
    h[56:60] = b'\xdd' * 4
    h[60:62] = struct.pack('<h', 2)
    k = bytes(h[8:56])
    rev = k[::-1]
    enc = Cipher(algorithms.AES(hashlib.sha256(k[:32] + secret).digest()), modes.CTR(k[32:])).encryptor()
    dec = Cipher(algorithms.AES(hashlib.sha256(rev[:32] + secret).digest()), modes.CTR(rev[32:])).encryptor()
    encrypted = enc.update(bytes(h))
    nonce = os.urandom(16)
    body = struct.pack('<I', 0xbe7e8ef1) + nonce
    message = b'\x00' * 8 + struct.pack('<QI', int(time.time() * (1 << 32)) & ~3, len(body)) + body
    payload = message + os.urandom(12)
    s = socket.create_connection((host, port), timeout=min(3, budget))
    s.settimeout(max(0.01, deadline - time.monotonic()))
    s.sendall(bytes(h[:56]) + encrypted[56:] + enc.update(struct.pack('<I', len(payload)) + payload))
    def receive(size):
        data = b''
        while len(data) < size:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Telegram readiness deadline')
            s.settimeout(remaining)
            part = s.recv(size - len(data))
            if not part:
                raise EOFError('Telegram response missing')
            data += part
        return data
    length = struct.unpack('<I', dec.update(receive(4)))[0]
    if not 56 <= length <= 8192:
        raise ValueError('Invalid Telegram frame')
    data = dec.update(receive(length))
    size = struct.unpack('<I', data[16:20])[0]
    response = data[20:20 + size]
    if data[:8] != b'\x00' * 8 or size < 36 or size > len(data) - 20:
        raise ValueError('Invalid Telegram envelope')
    if response[:4] != b'\x63\x24\x16\x05' or response[4:20] != nonce:
        raise ValueError('Telegram resPQ nonce mismatch')
    print('Telegram resPQ verified (DC2)')
except Exception as error:
    print('Telegram readiness failed: ' + type(error).__name__, file=sys.stderr)
    raise SystemExit(1)
finally:
    if s:
        s.close()`;

function shellQuote(value: string) {
  return "'" + value.replace(/'/g, "'\\''") + "'";
}

export function createMtprotoSecret(
  bytes = crypto.getRandomValues(new Uint8Array(16)),
) {
  if (bytes.length !== 16) throw new Error('Invalid key length');
  return (
    'dd' + Array.from(bytes, (n) => n.toString(16).padStart(2, '0')).join('')
  );
}

function validServer(input: string) {
  if (!input || input.length > 253 || /[^a-zA-Z0-9.:[\]-]/.test(input))
    return false;
  const host = input.replace(/^\[|\]$/g, '');
  if (
    (input.includes('[') || input.includes(']')) &&
    (!input.startsWith('[') || !input.endsWith(']') || !host.includes(':'))
  )
    return false;
  if (host.includes(':')) {
    try {
      return new URL(`http://[${host}]/`).hostname !== '';
    } catch {
      return false;
    }
  }
  if (/^[\d.]+$/.test(host))
    return (
      host.split('.').length === 4 &&
      host
        .split('.')
        .every((p) => /^(0|[1-9]\d{0,2})$/.test(p) && Number(p) <= 255)
    );
  return host
    .split('.')
    .every((p) => /^[a-z\d](?:[a-z\d-]{0,61}[a-z\d])?$/i.test(p));
}

export function validateMtproto(v: MtprotoValues) {
  const errors: Partial<Record<keyof MtprotoValues, boolean>> = {};
  if (!validServer(v.server)) errors.server = true;
  if (!/^[1-9]\d{0,4}$/.test(v.port) || Number(v.port) > 65535)
    errors.port = true;
  if (!/^dd[\da-f]{32}$/.test(v.secret)) errors.secret = true;
  return errors;
}

export function mtprotoLink(v: MtprotoValues) {
  if (Object.keys(validateMtproto(v)).length)
    throw new Error('Invalid MTProto values');
  const query = new URLSearchParams({
    server: v.server.replace(/^\[|\]$/g, ''),
    port: v.port,
    secret: v.secret,
  });
  return 'https://t.me/proxy?' + query.toString();
}

export function buildMtprotoInstall(
  method: MtprotoMethod,
  v: MtprotoValues,
  language: string,
) {
  if (
    !['docker', 'entware', 'linux'].includes(method) ||
    Object.keys(validateMtproto(v)).length
  )
    throw new Error('Invalid MTProto values');
  if (method !== 'docker' && Number(v.port) < 1024)
    throw new Error('Native service requires port >= 1024');
  return `#!/bin/sh\n(\nset -eu\nNFQWS_MT_METHOD='${method}'\nNFQWS_MT_LANG='${language === 'ru' ? 'ru' : 'en'}'\nNFQWS_MT_PORT='${v.port}'\nNFQWS_MT_KEY='${v.secret.slice(2)}'\nNFQWS_MT_LINK='${mtprotoLink(v)}'\n${installer
    .replace('@@MTPROTO_DOCKER_IMAGE@@', MTPROTO_DOCKER_IMAGE)
    .replace('@@MTPROTO_DOCKER_LAUNCHER@@', MTPROTO_DOCKER_LAUNCHER)
    .replace('@@MTPROTO_READINESS@@', MTPROTO_READINESS)
    .replace('@@MTPROTO_LOG_REDACTION@@', logRedaction)
    .replace(
      '@@MTPROTO_HEALTH_COMMAND@@',
      'exec /opt/venv/bin/python -c ' +
        shellQuote(MTPROTO_READINESS) +
        ' 127.0.0.1 1443 15',
    )}\n)\n`;
}

export function buildMtprotoCompose(v: MtprotoValues) {
  if (Object.keys(validateMtproto(v)).length)
    throw new Error('Invalid MTProto values');
  return `services:
  mtproto:
    image: ${MTPROTO_DOCKER_IMAGE}
    container_name: nfqws-mtproto
    restart: unless-stopped
    entrypoint: ["/sbin/tini", "--", "/bin/sh", "-c"]
    command: ${JSON.stringify([MTPROTO_DOCKER_LAUNCHER.replace(/\$/g, () => '$$')])}
    ports:
      - "${v.port}:1443"
    environment:
      PROXY_HOST: "0.0.0.0"
      PROXY_PORT: "1443"
      PROXY_SECRET: "${v.secret.slice(2)}"
      PROXY_DC_IPS: "2:149.154.167.220 4:149.154.167.220"
      PROXY_POOL_SIZE: "2"
      # Existing image relay; override this ENV value if the relay is unavailable.
      # WS uses HTTP/80; MTProto payload encryption remains end-to-end.
      CFPROXY_DOMAIN: "pclead.co.uk"
    healthcheck:
      test: ${JSON.stringify(['CMD', '/opt/venv/bin/python', '-c', MTPROTO_READINESS, '127.0.0.1', '1443', '15'])}
      interval: 5m
      timeout: 20s
      start_period: 10s
      retries: 3
    cap_drop:
      - ALL
    security_opt:
      - "no-new-privileges:true"
    logging:
      driver: json-file
      options:
        max-size: "5m"
        max-file: "2"
`;
}

export function mtprotoDiagnostics(method: MtprotoMethod) {
  if (method === 'docker')
    return 'docker inspect --format="{{.State.Status}}" nfqws-mtproto\ndocker logs --tail 40 nfqws-mtproto';
  if (method === 'entware')
    return '/opt/etc/init.d/S98nfqws-mtproto status\ntail -n 40 /opt/var/log/nfqws-mtproto.log';
  return 'sudo systemctl status nfqws-mtproto --no-pager\nsudo journalctl -u nfqws-mtproto -n 40 --no-pager';
}

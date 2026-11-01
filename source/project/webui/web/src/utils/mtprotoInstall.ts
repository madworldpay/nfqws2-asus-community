import installer from './mtproto-install.sh?raw';

export type MtprotoMethod = 'docker' | 'entware' | 'linux';
export type MtprotoValues = { server: string; port: string; secret: string };

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
  return `#!/bin/sh\n(\nset -eu\nNFQWS_MT_METHOD='${method}'\nNFQWS_MT_LANG='${language === 'ru' ? 'ru' : 'en'}'\nNFQWS_MT_PORT='${v.port}'\nNFQWS_MT_KEY='${v.secret.slice(2)}'\nNFQWS_MT_LINK='${mtprotoLink(v)}'\n${installer}\n)\n`;
}

export function mtprotoDiagnostics(method: MtprotoMethod) {
  if (method === 'docker')
    return 'docker inspect --format="{{.State.Status}}" nfqws-mtproto\ndocker logs --tail 40 nfqws-mtproto';
  if (method === 'entware')
    return '/opt/etc/init.d/S98nfqws-mtproto status\ntail -n 40 /opt/var/log/nfqws-mtproto.log';
  return 'sudo systemctl status nfqws-mtproto --no-pager\nsudo journalctl -u nfqws-mtproto -n 40 --no-pager';
}

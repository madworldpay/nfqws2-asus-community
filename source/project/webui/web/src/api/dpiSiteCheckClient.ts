import { DpiError, request } from '@/api/dpiClient';

export const DPI_SITE_SERVICES = {
  facebook: ['facebook-main', 'facebook-mobile', 'facebook-cdn'],
  youtube: ['youtube-main', 'youtube-images', 'youtube-static'],
  discord: ['discord-main', 'discord-cdn', 'discord-gateway'],
} as const;
export type DpiSiteService = keyof typeof DPI_SITE_SERVICES;
export const DPI_SITE_TARGETS = {
  'facebook-main': 'https://www.facebook.com/',
  'facebook-mobile': 'https://m.facebook.com/',
  'facebook-cdn': 'https://static.xx.fbcdn.net/',
  'youtube-main': 'https://www.youtube.com/',
  'youtube-images': 'https://i.ytimg.com/',
  'youtube-static': 'https://www.gstatic.com/',
  'discord-main': 'https://discord.com/',
  'discord-cdn': 'https://cdn.discordapp.com/',
  'discord-gateway': 'https://gateway.discord.gg/',
} as const;
export type DpiSiteTarget = keyof typeof DPI_SITE_TARGETS;
export type DpiSiteDnsScope = 'system_resolver' | 'local_resolver';
export type DpiSiteContext = {
  nfqws: 'running' | 'stopped' | 'unknown';
  mode: 'auto' | 'all' | 'list' | 'unknown';
  config_sha256: string | null;
};
export type DpiSiteCheck = {
  type: 'nfqws2_dpi_site_check';
  schema_version: 1;
  target: DpiSiteTarget;
  url: string;
  started_at: number;
  finished_at: number;
  context: {
    before: DpiSiteContext;
    after: DpiSiteContext;
    changed: boolean | null;
  };
  response: {
    outcome:
      | 'response'
      | 'timeout'
      | 'tls_error'
      | 'connection_error'
      | 'read_limited'
      | 'unavailable'
      | 'blocked_address';
    http_status: number | null;
    bytes_read: number;
    body_limited: boolean;
    redirect: string | null;
    elapsed_ms: number | null;
    error_code: string | null;
  };
  full_service_verified: false;
  dns_scope: DpiSiteDnsScope;
};

function shape(
  value: unknown,
  keys: string[],
): value is Record<string, unknown> {
  return (
    !!value &&
    typeof value === 'object' &&
    !Array.isArray(value) &&
    Object.keys(value).length === keys.length &&
    keys.every((key) => Object.prototype.hasOwnProperty.call(value, key))
  );
}
function integer(
  value: unknown,
  max = Number.MAX_SAFE_INTEGER,
): value is number {
  return (
    Number.isSafeInteger(value) && Number(value) >= 0 && Number(value) <= max
  );
}
function context(value: unknown): value is DpiSiteContext {
  return (
    shape(value, ['nfqws', 'mode', 'config_sha256']) &&
    typeof value.nfqws === 'string' &&
    ['running', 'stopped', 'unknown'].includes(value.nfqws) &&
    typeof value.mode === 'string' &&
    ['auto', 'all', 'list', 'unknown'].includes(value.mode) &&
    (value.config_sha256 === null ||
      (typeof value.config_sha256 === 'string' &&
        /^[a-f0-9]{64}$/.test(value.config_sha256)))
  );
}
function contextChange(before: DpiSiteContext, after: DpiSiteContext) {
  let unknown = false;
  for (const key of ['nfqws', 'mode', 'config_sha256'] as const) {
    if (
      before[key] === null ||
      after[key] === null ||
      before[key] === 'unknown' ||
      after[key] === 'unknown'
    ) {
      unknown = true;
    } else if (before[key] !== after[key]) {
      return true;
    }
  }
  return unknown ? null : false;
}

export function validateDpiSiteCheck(
  value: unknown,
  target: DpiSiteTarget,
  expectedScope?: DpiSiteDnsScope,
): DpiSiteCheck {
  if (
    !shape(value, [
      'type',
      'schema_version',
      'target',
      'url',
      'started_at',
      'finished_at',
      'context',
      'response',
      'full_service_verified',
      'dns_scope',
    ])
  )
    throw new DpiError('invalid_response');
  const c = value.context;
  const r = value.response;
  if (
    value.type !== 'nfqws2_dpi_site_check' ||
    value.schema_version !== 1 ||
    value.target !== target ||
    value.url !== DPI_SITE_TARGETS[target] ||
    !integer(value.started_at) ||
    !integer(value.finished_at) ||
    value.full_service_verified !== false ||
    typeof value.dns_scope !== 'string' ||
    !['system_resolver', 'local_resolver'].includes(value.dns_scope) ||
    (expectedScope !== undefined && value.dns_scope !== expectedScope) ||
    !shape(c, ['before', 'after', 'changed']) ||
    !context(c.before) ||
    !context(c.after) ||
    c.changed !== contextChange(c.before, c.after) ||
    !shape(r, [
      'outcome',
      'http_status',
      'bytes_read',
      'body_limited',
      'redirect',
      'elapsed_ms',
      'error_code',
    ]) ||
    typeof r.outcome !== 'string' ||
    ![
      'response',
      'timeout',
      'tls_error',
      'connection_error',
      'read_limited',
      'unavailable',
      'blocked_address',
    ].includes(r.outcome) ||
    (r.http_status !== null &&
      (!integer(r.http_status, 599) || r.http_status < 100)) ||
    !integer(r.bytes_read, 262144) ||
    typeof r.body_limited !== 'boolean' ||
    r.body_limited !== (r.outcome === 'read_limited') ||
    (['response', 'read_limited'].includes(r.outcome) &&
      r.http_status === null) ||
    (r.redirect !== null &&
      (typeof r.redirect !== 'string' ||
        r.redirect.length > 2048 ||
        Array.from(r.redirect).some(
          (char) => char.charCodeAt(0) < 32 || char.charCodeAt(0) === 127,
        ))) ||
    (r.elapsed_ms !== null && !integer(r.elapsed_ms)) ||
    (r.error_code !== null &&
      (typeof r.error_code !== 'string' ||
        !/^[a-z0-9_]{1,64}$/.test(r.error_code)))
  )
    throw new DpiError('invalid_response');
  return value as DpiSiteCheck;
}

export async function checkDpiSite(
  csrfToken: string,
  target: DpiSiteTarget,
  dnsScope?: DpiSiteDnsScope,
): Promise<DpiSiteCheck> {
  if (
    typeof target !== 'string' ||
    !Object.prototype.hasOwnProperty.call(DPI_SITE_TARGETS, target) ||
    (dnsScope !== undefined && !['system_resolver', 'local_resolver'].includes(dnsScope))
  )
    throw new DpiError('invalid_request');
  // The server owns the 10 second probe deadline; the common transport bounds
  // JSON size and gives the server up to 15 seconds to return/clean up.
  const fields: Record<string, string> = dnsScope === undefined ? { target } : { target, dns_scope: dnsScope };
  const { value } = await request(csrfToken, 'dpisitecheck', fields, 16384);
  return validateDpiSiteCheck(value, target, dnsScope ?? 'system_resolver');
}

import { DpiError, request } from '@/api/dpiClient';

export const DPI_SITE_SERVICES = {
  facebook: ['facebook-main', 'facebook-mobile', 'facebook-cdn'],
  youtube: ['youtube-main', 'youtube-images', 'youtube-static'],
  discord: ['discord-main', 'discord-cdn', 'discord-gateway'],
} as const;
export type DpiSiteService = keyof typeof DPI_SITE_SERVICES | 'custom';
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

export type DpiNetworkObservation = {
  state: 'done' | 'partial' | 'unavailable' | 'not_run';
  output: string;
};
export type DpiCustomSiteCheck = Omit<DpiSiteCheck, 'schema_version' | 'target'> & {
  schema_version: 2;
  target: string;
  host: string;
  kind: 'domain' | 'ipv4';
  operation: 'https' | 'route';
  addresses: string[];
  dns: { rcode: number | null; answers: string[]; reason: string };
  network: null | Record<'ping' | 'route' | 'trace', DpiNetworkObservation>;
};
export type DpiSiteObservation = DpiSiteCheck | DpiCustomSiteCheck;

function ipv4(value: unknown): value is string {
  return typeof value === 'string' && /^(?:0|[1-9][0-9]{0,2})(?:\.(?:0|[1-9][0-9]{0,2})){3}$/.test(value) && value.split('.').every(part => Number(part) <= 255);
}
function requestedHost(target: string): string | null {
  const input = target.replace(/^custom-(https|route):/, '');
  try { return new URL(/^[a-z][a-z0-9+.-]*:\/\//i.test(input) ? input : `https://${input}`).hostname.toLowerCase().replace(/\.$/, ''); }
  catch { return null; }
}
function network(value: unknown): value is DpiCustomSiteCheck['network'] {
  return shape(value, ['ping','route','trace']) && (['ping','route','trace'] as const).every(kind => {
    const row = value[kind];
    return shape(row, ['state','output']) && typeof row.state === 'string' && ['done','partial','unavailable','not_run'].includes(row.state) && typeof row.output === 'string' && row.output.length <= (kind === 'trace' ? 6144 : 1536) && !/[^\x09\x0a\x0d\x20-\x7e]/.test(row.output);
  });
}

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

function validateObservation(
  value: unknown,
  target: string,
  expectedScope: DpiSiteDnsScope | undefined,
  custom: boolean,
): DpiSiteObservation {
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
      ...(custom ? ['host','kind','operation','addresses','network','dns'] : []),
    ])
  )
    throw new DpiError('invalid_response');
  const c = value.context;
  const r = value.response;
  if (
    value.type !== 'nfqws2_dpi_site_check' ||
    value.schema_version !== (custom ? 2 : 1) ||
    value.target !== target ||
    (custom ? typeof value.host !== 'string' || value.host !== requestedHost(target) || value.url !== `https://${value.host}/` : value.url !== DPI_SITE_TARGETS[target as DpiSiteTarget]) ||
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
  if (custom && (
    !shape(value.dns, ['rcode','answers','reason']) ||
    !(value.dns.rcode === null || integer(value.dns.rcode, 15)) ||
    !Array.isArray(value.dns.answers) || value.dns.answers.length > 64 || !value.dns.answers.every(ipv4) ||
    typeof value.dns.reason !== 'string' || !['not_requested','ready','no_address','rcode','timed_out','invalid_response','invalid_arguments','system_answer','system_no_address','answer_limit','unavailable'].includes(value.dns.reason) ||
    !['domain','ipv4'].includes(String(value.kind)) ||
    (value.kind === 'ipv4' && !ipv4(value.host)) ||
    value.operation !== /^custom-(https|route):/.exec(target)?.[1] ||
    !Array.isArray(value.addresses) || value.addresses.length > 16 || !value.addresses.every(ipv4) ||
    new Set(value.addresses).size !== value.addresses.length ||
    (value.kind === 'ipv4' && value.addresses.length > 0 && (value.addresses.length !== 1 || value.addresses[0] !== value.host)) ||
    (value.operation === 'https' ? value.network !== null : !network(value.network))
  )) throw new DpiError('invalid_response');
  return value as DpiSiteObservation;
}
export function validateDpiSiteCheck(value: unknown, target: DpiSiteTarget, expectedScope?: DpiSiteDnsScope): DpiSiteCheck {
  return validateObservation(value, target, expectedScope, false) as DpiSiteCheck;
}
export async function checkDpiTarget(csrfToken: string, input: string, operation: 'https' | 'route', dnsScope: DpiSiteDnsScope): Promise<DpiCustomSiteCheck> {
  if (typeof input !== 'string' || !input.trim() || input.length > 4096 || /[\r\n\0]/.test(input) || !['https','route'].includes(operation) || !['local_resolver','system_resolver'].includes(dnsScope)) throw new DpiError('invalid_request');
  const target = `custom-${operation}:${input.trim()}`;
  if (requestedHost(target) === null) throw new DpiError('invalid_request');
  const { value } = await request(csrfToken, 'dpisitecheck', { target, dns_scope: dnsScope }, 16384);
  return validateObservation(value, target, dnsScope, true) as DpiCustomSiteCheck;
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

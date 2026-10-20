import { DpiError, request } from '@/api/dpiClient';
import type { DnsPreview, Profile } from '@/api/smartDnsProfile';

export type ConfigStatus = {
  schema_version: 1;
  state:
    | 'idle'
    | 'validating'
    | 'preview_ready'
    | 'applying'
    | 'awaiting_confirmation'
    | 'confirmed'
    | 'rolling_back'
    | 'rolled_back'
    | 'failed'
    | 'conflict';
  request_id: string | null;
  preview_id: string | null;
  code: string | null;
  active_profile_hash: string | null;
  deadline_remaining_s: number | null;
  checks: { ok: boolean; code?: string }[];
  conflicts: string[];
};
export type Checkup = {
  schema_version: 1;
  items: {
    id: string;
    state: 'ready' | 'attention' | 'info';
    facts: Record<string, unknown>;
    action_code: string;
  }[];
  readiness: Record<
    'nfqws2' | 'smartdns_install' | 'smartdns_connect',
    { ready: boolean; codes: string[] }
  >;
};
export type ConfigView = {
  status: ConfigStatus;
  draft: Profile | null;
  active_profile: Profile | null;
  resume_code?: string | null;
  confirmed_profile?: Profile | null;
};
const ID = /^[a-f0-9]{32}$/;
const HASH = /^[a-f0-9]{64}$/;
function status(v: unknown): ConfigStatus {
  const s = v as ConfigStatus;
  if (
    !s ||
    s.schema_version !== 1 ||
    ![
      'idle',
      'validating',
      'preview_ready',
      'applying',
      'awaiting_confirmation',
      'confirmed',
      'rolling_back',
      'rolled_back',
      'failed',
      'conflict',
    ].includes(s.state) ||
    (s.request_id !== null && !ID.test(s.request_id)) ||
    (s.preview_id !== null && !ID.test(s.preview_id)) ||
    (s.deadline_remaining_s !== null &&
      (!Number.isFinite(s.deadline_remaining_s) ||
        s.deadline_remaining_s < 0 ||
        s.deadline_remaining_s > 120))
  )
    throw new DpiError('invalid_response');
  return s;
}
async function call(
  csrf: string,
  cmd: string,
  params: Record<string, string> = {},
) {
  return (await request(csrf, cmd, params, 524288)).value;
}
export async function getRouterCheckup(csrf: string): Promise<Checkup> {
  const c = (await call(csrf, 'routercheckup')) as Checkup;
  if (
    !c ||
    c.schema_version !== 1 ||
    !Array.isArray(c.items) ||
    !c.readiness?.smartdns_connect ||
    !c.readiness.smartdns_install
  )
    throw new DpiError('invalid_response');
  return c;
}
export async function getSmartDnsConfigStatus(
  csrf: string,
): Promise<ConfigView> {
  const c = (await call(csrf, 'smartdnsconfigstatus')) as ConfigView;
  status(c?.status);
  return c;
}
export async function saveSmartDnsDraft(
  csrf: string,
  profile: Profile,
): Promise<string> {
  const c = (await call(csrf, 'smartdnsdraft', {
    profile: JSON.stringify(profile),
  })) as { profile_hash: string };
  if (!HASH.test(c?.profile_hash ?? '')) throw new DpiError('invalid_response');
  return c.profile_hash;
}
export async function validateSmartDnsDraft(
  csrf: string,
  id: string,
  hash: string,
) {
  return status(
    await call(csrf, 'smartdnsvalidate', {
      request_id: id,
      profile_hash: hash,
    }),
  );
}
export async function getSmartDnsPreview(
  csrf: string,
  id: string,
): Promise<DnsPreview> {
  const p = (await call(csrf, 'smartdnspreview', {
    preview_id: id,
  })) as DnsPreview;
  if (
    !p ||
    p.schema_version !== 1 ||
    !ID.test(p.id) ||
    !HASH.test(p.profile_hash) ||
    !HASH.test(p.baseline_hash) ||
    typeof p.config !== 'string' ||
    !Array.isArray(p.groups) ||
    !Array.isArray(p.overlaps) ||
    !['dns_only', 'configuration_only'].includes(p.scope) ||
    p.service_success_tested !== false
  )
    throw new DpiError('invalid_response');
  return p;
}
export async function applySmartDnsPreview(
  csrf: string,
  id: string,
  p: DnsPreview,
) {
  return status(
    await call(csrf, 'smartdnsapply', {
      request_id: id,
      preview_id: p.id,
      profile_hash: p.profile_hash,
      baseline_hash: p.baseline_hash,
    }),
  );
}
export async function confirmSmartDns(csrf: string, id: string) {
  return status(await call(csrf, 'smartdnsconfirm', { request_id: id }));
}
export async function rollbackSmartDns(csrf: string, id: string) {
  return status(await call(csrf, 'smartdnsrollback', { request_id: id }));
}

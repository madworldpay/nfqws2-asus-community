/** Pure editor state. No browser APIs, request side effects, or implicit resolver. */
export type DomainRule = { name: string; include_subdomains: boolean };
export type DnsUpstream = {
  id: string;
  label: string;
  protocol: 'udp' | 'tcp' | 'dot' | 'doh';
  address: string;
  port: number;
  tls_name: string;
  url: string;
  bootstrap: string[];
  default: boolean;
  domains: DomainRule[];
};
export type StaticRecord = DomainRule & {
  addresses: string[];
  checked_at: string | null;
};
export type Profile = {
  schema_version: 1;
  upstreams: DnsUpstream[];
  records: StaticRecord[];
};
export type DnsPreview = {
  schema_version: 1;
  id: string;
  profile_hash: string;
  baseline_hash: string;
  config: string;
  groups: { domain: string; include_subdomains: boolean; servers: string[] }[];
  overlaps: { record: string; dns_domain: string }[];
  checks: {
    stage: string;
    server_id?: string | null;
    ok: boolean;
    code?: string;
  }[];
  expires_uptime: number;
  scope: 'dns_only' | 'configuration_only';
  service_success_tested: false;
};
export type EditorState = {
  profile: Profile;
  revision: number;
  preview: DnsPreview | null;
};
export const emptyProfile = (): Profile => ({
  schema_version: 1,
  upstreams: [],
  records: [],
});
export const newUpstream = (id: string): DnsUpstream => ({
  id,
  label: '',
  protocol: 'dot',
  address: '',
  port: 853,
  tls_name: '',
  url: '',
  bootstrap: [],
  default: false,
  domains: [],
});
export const editProfile = (
  state: EditorState,
  profile: Profile,
): EditorState => ({ profile, revision: state.revision + 1, preview: null });
export const acceptPreview = (
  state: EditorState,
  revision: number,
  preview: DnsPreview,
): EditorState => (state.revision === revision ? { ...state, preview } : state);
export const withDomain = (
  profile: Profile,
  index: number,
  domain: DomainRule,
): Profile => ({
  ...profile,
  upstreams: profile.upstreams.map((s, i) =>
    i === index ? { ...s, domains: [...s.domains, domain] } : s,
  ),
});
export const remainingSeconds = (
  server: number | null,
  received: number,
  now: number,
): number | null =>
  server === null
    ? null
    : Math.max(0, Math.ceil(server - Math.max(0, now - received) / 1000));

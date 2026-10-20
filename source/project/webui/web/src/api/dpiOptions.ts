import type { DpiMetadata } from './dpiClient.ts';

export type DpiOptions = {
  profile?: string;
  language?: string;
  interface?: string | null;
  proxy?: string | null;
  fingerprint?: string | null;
  config?: Record<string, unknown>;
  targets?: Record<string, unknown[] | null>;
  burst?: Record<string, unknown>;
  limits?: { total_seconds?: number; group_seconds?: number };
};
export function parseDpiOptions(text: string): DpiOptions {
  const value: unknown = JSON.parse(text);
  if (!value || typeof value !== 'object' || Array.isArray(value))
    throw new Error('invalid_options');
  const result = { ...value } as Record<string, unknown>;
  const fail = (field: string): never => {
    throw new Error(`invalid_options:${field}`);
  };
  for (const key of ['profile', 'language'])
    if (key in result && typeof result[key] !== 'string') fail(key);
  for (const key of ['interface', 'proxy', 'fingerprint'])
    if (
      key in result &&
      result[key] !== null &&
      typeof result[key] !== 'string'
    )
      fail(key);
  for (const key of ['config', 'targets', 'burst', 'limits']) {
    if (!(key in result)) continue;
    // PHP represents an empty associative container as []; treat it as {}.
    if (Array.isArray(result[key]) && result[key].length === 0)
      result[key] = {};
    if (
      !result[key] ||
      typeof result[key] !== 'object' ||
      Array.isArray(result[key])
    )
      fail(key);
  }
  for (const [key, item] of Object.entries(result.targets ?? {}))
    if (item !== null && !Array.isArray(item)) fail(`targets.${key}`);
  for (const [key, item] of Object.entries(result.limits ?? {}))
    if (typeof item !== 'number' || !Number.isFinite(item))
      fail(`limits.${key}`);
  const burst = (result.burst ?? {}) as Record<string, unknown>;
  for (const key of ['connections', 'timeout', 'gap'])
    if (
      key in burst &&
      (typeof burst[key] !== 'number' || !Number.isFinite(burst[key]))
    )
      fail(`burst.${key}`);
  for (const key of ['profiles', 'tls', 'alpn', 'variant'])
    if (key in burst && typeof burst[key] !== 'string') fail(`burst.${key}`);
  if ('trace' in burst && typeof burst.trace !== 'boolean') fail('burst.trace');
  return result as DpiOptions;
}
export function effectiveDpiSettings(
  options: DpiOptions,
  metadata: DpiMetadata,
) {
  const profile = typeof options.profile === 'string' ? options.profile : 'ru';
  const list = (text: string) =>
    text.split(/\r?\n/).filter((x) => x.trim() && !x.trim().startsWith('#'));
  const names: Record<string, string> = {
    domains: 'domains.txt',
    tcp: 'tcp16.json',
    sni: 'whitelist_sni.txt',
    burst_domains: 'burst-domains.txt',
    quic_unsupported: 'quic_unsupported.txt',
  };
  const coverage: Record<string, number> = {};
  for (const [key, file] of Object.entries(names)) {
    const stock: unknown[] =
      key === 'tcp'
        ? JSON.parse(metadata.files[file])
        : list(metadata.files[file]);
    const selected = options.targets?.[key];
    coverage[key] = (
      Array.isArray(selected) && selected.length ? selected : stock
    ).length;
  }
  const config = { ...metadata.config, ...options.config };
  coverage.dns = Array.isArray(config.DNS_AVAILABILITY_SERVERS)
    ? config.DNS_AVAILABILITY_SERVERS.length
    : 0;
  return {
    profile,
    coverage,
    concurrency: config.MAX_CONCURRENT,
    timeout: config.TIMEOUT,
    ipVersion: config.IP_VERSION,
    limits: {
      total_seconds:
        typeof options.limits?.total_seconds === 'number' &&
        Number.isFinite(options.limits.total_seconds)
          ? options.limits.total_seconds
          : 600,
      group_seconds:
        typeof options.limits?.group_seconds === 'number' &&
        Number.isFinite(options.limits.group_seconds)
          ? options.limits.group_seconds
          : 180,
    },
  };
}

import catalog from './smartDnsPresets.json' with { type: 'json' };
import type { DnsUpstream } from './smartDnsProfile';

export type DnsPreset = Pick<
  DnsUpstream,
  'label' | 'protocol' | 'address' | 'port' | 'tls_name' | 'url' | 'bootstrap'
> & { id: string };
export const DNS_PRESETS = catalog.presets as DnsPreset[];
export const findDnsPreset = (server: DnsUpstream) =>
  DNS_PRESETS.find(
    (p) =>
      p.protocol === server.protocol &&
      p.address === server.address &&
      p.port === server.port &&
      p.tls_name === server.tls_name &&
      p.url === server.url &&
      p.bootstrap.join('|') === server.bootstrap.join('|'),
  );
export const applyDnsPreset = (
  server: DnsUpstream,
  id: string,
): DnsUpstream => {
  const preset = DNS_PRESETS.find((p) => p.id === id);
  if (!preset) return server;
  const old = findDnsPreset(server);
  return {
    ...server,
    protocol: preset.protocol,
    address: preset.address,
    port: preset.port,
    tls_name: preset.tls_name,
    url: preset.url,
    bootstrap: [...preset.bootstrap],
    label:
      !server.label || server.label === old?.label
        ? preset.label
        : server.label,
  };
};

export const selectedDnsPreset = (server: DnsUpstream, manual: boolean) =>
  manual ? 'custom' : findDnsPreset(server)?.id || 'custom';

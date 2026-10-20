import { DpiError, request } from '@/api/dpiClient';

export type RouterWan = {
  schema_version: 1;
  state: 'available' | 'partial' | 'unavailable';
  addresses: { interface: string; address: string }[];
};

function ipv4(value: string): number | undefined {
  if (!/^(?:0|[1-9]\d{0,2})(?:\.(?:0|[1-9]\d{0,2})){3}$/.test(value)) return;
  const parts = value.split('.').map(Number);
  if (parts.some((part) => part > 255)) return;
  return parts.reduce((result, part) => result * 256 + part, 0);
}

export function addWanClient(current: string, address: string): string {
  const target = ipv4(address);
  if (target === undefined) return current;
  for (const entry of current.trim().split(/\s+/)) {
    const parts = entry.split('/');
    if (parts.length > 2) continue;
    const network = ipv4(parts[0]);
    const prefix =
      parts[1] === undefined
        ? 32
        : /^\d{1,2}$/.test(parts[1])
          ? Number(parts[1])
          : -1;
    if (network === undefined || prefix < 0 || prefix > 32) continue;
    const size = 2 ** (32 - prefix);
    if (Math.floor(network / size) === Math.floor(target / size))
      return current;
  }
  return [current.trim(), `${address}/32`].filter(Boolean).join(' ');
}

export async function getRouterWan(csrf: string): Promise<RouterWan> {
  const { value } = await request(csrf, 'wanaddresses', {}, 16384);
  const data = value as RouterWan;
  if (
    !data ||
    data.schema_version !== 1 ||
    !['available', 'partial', 'unavailable'].includes(data.state) ||
    !Array.isArray(data.addresses) ||
    data.addresses.length > 16 ||
    data.addresses.some(
      (row) =>
        !row ||
        typeof row.interface !== 'string' ||
        !/^[a-zA-Z0-9_.-]{1,32}$/.test(row.interface) ||
        typeof row.address !== 'string' ||
        ipv4(row.address) === undefined,
    )
  )
    throw new DpiError('invalid_response');
  return data;
}

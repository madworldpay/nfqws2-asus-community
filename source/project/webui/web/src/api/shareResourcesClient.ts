import {
  ShareError,
  shareRequest,
  type ShareSelection,
} from '@/api/shareClient';
import type { DnsUpstream, Profile, StaticRecord } from '@/api/smartDnsProfile';
import { sha256 } from '@/api/supportDigest';

export type ResourceMeta = {
  id: string;
  kind: 'lists' | 'lua' | 'blobs';
  name: string;
  byte_length: number;
  sha256: string | null;
  state: 'available' | 'unavailable' | 'too_large';
};
export type ResourceCopy = Omit<ResourceMeta, 'sha256' | 'state'> & {
  sha256: string;
  encoding: 'utf8' | 'base64';
  data_base64: string;
  text?: string;
};
export type ResourceInventory = {
  files: ResourceMeta[];
  skipped: number;
  scan_truncated: boolean;
};
export type DependencyAudit = {
  config_sha256: string;
  audit: {
    scope: string;
    references: {
      id: string;
      name: string;
      resource_id: string | null;
      state: string;
      selected: boolean;
      sources: string[];
    }[];
    missing: DependencyAudit['audit']['references'];
    unresolved: { source: string; kind: string; name?: string }[];
    complete: boolean;
  };
};
export type DnsSource = {
  id: 'active' | 'draft' | 'legacy';
  origin: 'active' | 'draft' | 'legacy';
  sha256: string;
  profile: Profile;
  complete: boolean;
  warnings: { line: number; code: string }[];
  scope: 'upstreams_and_domain_rules';
};
export type DnsSources = {
  sources: DnsSource[];
  warnings: { source: string; code: string }[];
};
export type DnsSelection = {
  source_id: DnsSource['id'];
  source_sha256: string;
  upstreams: DnsUpstream[];
  records: { index: number; value: StaticRecord }[];
};
const record = (v: unknown): v is Record<string, unknown> =>
  typeof v === 'object' && v !== null && !Array.isArray(v);
const id = (v: unknown): v is string =>
  typeof v === 'string' && /^[a-f0-9]{32}$/.test(v);
const hash = (v: unknown): v is string =>
  typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const safeName = (v: unknown): v is string =>
  typeof v === 'string' &&
  v.length > 0 &&
  new TextEncoder().encode(v).length <= 128 &&
  v !== '.' &&
  v !== '..' &&
  !v.includes('/') &&
  !v.includes('\\') &&
  !Array.from(v).some((c) => c.charCodeAt(0) < 32 || c.charCodeAt(0) === 127);
const invalid = (): never => {
  throw new ShareError('invalid_response');
};
function metadata(v: unknown): v is ResourceMeta {
  return (
    record(v) &&
    id(v.id) &&
    ['lists', 'lua', 'blobs'].includes(String(v.kind)) &&
    safeName(v.name) &&
    Number.isSafeInteger(v.byte_length) &&
    Number(v.byte_length) >= 0 &&
    (v.sha256 === null || hash(v.sha256)) &&
    ['available', 'unavailable', 'too_large'].includes(String(v.state)) &&
    (v.state !== 'available' || hash(v.sha256))
  );
}
export async function getShareInventory(
  csrf: string,
): Promise<ResourceInventory> {
  const v = await shareRequest(csrf, 'shareinventory');
  if (
    !record(v) ||
    !Array.isArray(v.files) ||
    v.files.length > 128 ||
    !v.files.every(metadata) ||
    new Set(v.files.map((f) => f.id)).size !== v.files.length ||
    !Number.isSafeInteger(v.skipped) ||
    Number(v.skipped) < 0 ||
    typeof v.scan_truncated !== 'boolean'
  )
    return invalid();
  return v as ResourceInventory;
}
export function resourceBytes(
  copy: Pick<
    ResourceCopy,
    'encoding' | 'kind' | 'data_base64' | 'sha256' | 'byte_length' | 'text'
  >,
): Uint8Array<ArrayBuffer> {
  let raw: string;
  try {
    raw = atob(copy.data_base64);
  } catch {
    return invalid();
  }
  if (
    btoa(raw) !== copy.data_base64 ||
    raw.length !== copy.byte_length ||
    raw.length > 262144
  )
    return invalid();
  const original = Uint8Array.from(raw, (c) => c.charCodeAt(0));
  if (sha256(original) !== copy.sha256) return invalid();
  if (copy.encoding === 'utf8') {
    if (copy.kind === 'blobs') return invalid();
    const text = new TextDecoder('utf-8', { fatal: true }).decode(original);
    if (text.includes('\0')) return invalid();
    const result = new TextEncoder().encode(copy.text ?? text);
    if (result.length > 262144 || (copy.text ?? text).includes('\0'))
      return invalid();
    return result;
  }
  return original;
}
export async function readShareResource(
  csrf: string,
  meta: ResourceMeta,
): Promise<ResourceCopy> {
  if (!id(meta.id) || !hash(meta.sha256))
    throw new ShareError('invalid_request');
  const v = await shareRequest(csrf, 'shareresourceread', {
    id: meta.id,
    source_sha256: meta.sha256,
  });
  if (
    !record(v) ||
    v.id !== meta.id ||
    v.kind !== meta.kind ||
    v.name !== meta.name ||
    v.sha256 !== meta.sha256 ||
    v.byte_length !== meta.byte_length ||
    !['utf8', 'base64'].includes(String(v.encoding)) ||
    typeof v.data_base64 !== 'string' ||
    (v.text !== undefined && typeof v.text !== 'string')
  )
    return invalid();
  const copy = v as ResourceCopy;
  const original = resourceBytes({ ...copy, text: undefined });
  if (
    copy.encoding === 'utf8' &&
    copy.text !== new TextDecoder('utf-8', { fatal: true }).decode(original)
  )
    return invalid();
  return copy;
}
export async function analyzeShare(
  csrf: string,
  strategy: ShareSelection['strategy'],
  resourceIds: string[],
): Promise<DependencyAudit> {
  const v = await shareRequest(csrf, 'shareanalyze', {
    selection: JSON.stringify({
      ...(strategy ? { strategy } : {}),
      resource_ids: resourceIds,
    }),
  });
  if (
    !record(v) ||
    !hash(v.config_sha256) ||
    !record(v.audit) ||
    !Array.isArray(v.audit.references) ||
    v.audit.references.length > 128 ||
    !Array.isArray(v.audit.missing) ||
    !Array.isArray(v.audit.unresolved) ||
    typeof v.audit.complete !== 'boolean'
  )
    return invalid();
  return v as DependencyAudit;
}
export async function getShareDnsSources(csrf: string): Promise<DnsSources> {
  const v = await shareRequest(csrf, 'sharednssources');
  if (
    !record(v) ||
    !Array.isArray(v.sources) ||
    v.sources.length > 3 ||
    !Array.isArray(v.warnings)
  )
    return invalid();
  const seen = new Set<string>();
  for (const s of v.sources) {
    if (
      !record(s) ||
      !['active', 'draft', 'legacy'].includes(String(s.id)) ||
      s.id !== s.origin ||
      seen.has(String(s.id)) ||
      !hash(s.sha256) ||
      typeof s.complete !== 'boolean' ||
      !Array.isArray(s.warnings) ||
      !record(s.profile) ||
      s.profile.schema_version !== 1 ||
      !Array.isArray(s.profile.upstreams) ||
      s.profile.upstreams.length > 32 ||
      !Array.isArray(s.profile.records) ||
      s.profile.records.length > 64
    )
      return invalid();
    seen.add(String(s.id));
  }
  return v as DnsSources;
}
export function downloadContribution(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  try {
    link.href = url;
    link.download = filename;
    document.body.append(link);
    link.click();
  } finally {
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}
function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc ^= byte;
    for (let i = 0; i < 8; i++) crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0);
  }
  return (crc ^ 0xffffffff) >>> 0;
}
/** ZIP STORE: bounded selected copies only; no compression or execution. */
export function resourceZip(copies: ResourceCopy[]): Blob {
  if (!copies.length || copies.length > 128)
    throw new ShareError('invalid_request');
  const chunks: Uint8Array<ArrayBuffer>[] = [];
  const entries: Uint8Array<ArrayBuffer>[] = [];
  let offset = 0;
  let total = 0;
  const names = new Set();
  for (const copy of copies) {
    if (!safeName(copy.name) || !['lists', 'lua', 'blobs'].includes(copy.kind))
      throw new ShareError('invalid_request');
    const path = copy.kind + '/' + copy.name;
    if (names.has(path)) throw new ShareError('invalid_request');
    names.add(path);
    const name = new TextEncoder().encode(path);
    const data = resourceBytes(copy);
    total += data.length;
    if (total > 8388608) throw new ShareError('output_limit');
    const crc = crc32(data);
    const local = new Uint8Array(30 + name.length);
    const l = new DataView(local.buffer);
    l.setUint32(0, 0x04034b50, true);
    l.setUint16(4, 20, true);
    l.setUint16(6, 0x800, true);
    l.setUint16(12, 33, true);
    l.setUint32(14, crc, true);
    l.setUint32(18, data.length, true);
    l.setUint32(22, data.length, true);
    l.setUint16(26, name.length, true);
    local.set(name, 30);
    const central = new Uint8Array(46 + name.length);
    const c = new DataView(central.buffer);
    c.setUint32(0, 0x02014b50, true);
    c.setUint16(4, 20, true);
    c.setUint16(6, 20, true);
    c.setUint16(8, 0x800, true);
    c.setUint16(14, 33, true);
    c.setUint32(16, crc, true);
    c.setUint32(20, data.length, true);
    c.setUint32(24, data.length, true);
    c.setUint16(28, name.length, true);
    c.setUint32(42, offset, true);
    central.set(name, 46);
    chunks.push(local, data);
    entries.push(central);
    offset += local.length + data.length;
  }
  const centralSize = entries.reduce((n, b) => n + b.length, 0);
  const end = new Uint8Array(22);
  const e = new DataView(end.buffer);
  e.setUint32(0, 0x06054b50, true);
  e.setUint16(8, copies.length, true);
  e.setUint16(10, copies.length, true);
  e.setUint32(12, centralSize, true);
  e.setUint32(16, offset, true);
  return new Blob([...chunks, ...entries, end], { type: 'application/zip' });
}

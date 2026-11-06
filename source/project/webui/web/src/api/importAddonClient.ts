import { ShareError, shareRequest } from '@/api/shareClient';

export type ImportAddonSelection = Readonly<{ id: string; sha256: string }>;
export type ImportAddon = Readonly<{
  id: string;
  title: string;
  description: string;
  attribution: string;
  updated_at: string;
  revision: number;
  min_build: number;
  size: number;
  sha256: string;
}>;
export type ImportAddonCatalog = Readonly<{
  schema_version: 1;
  revision: number;
  build: number;
  addons: ImportAddon[];
}>;
export type ImportAddonPreview = Readonly<{
  id: string;
  title: string;
  kind: 'scope_domains_v1';
  domains: string[];
  action: 'scope_extended' | 'already_covered';
  note: string;
}>;
const ID = /^[a-z0-9][a-z0-9-]{0,63}$/;
const HASH = /^[a-f0-9]{64}$/;
const object = (v: unknown): v is Record<string, unknown> =>
  typeof v === 'object' && v !== null && !Array.isArray(v);
const exact = (v: Record<string, unknown>, keys: string[]) =>
  Object.keys(v).length === keys.length && keys.every((k) => k in v);
const integer = (v: unknown, min: number, max: number): v is number =>
  typeof v === 'number' && Number.isInteger(v) && v >= min && v <= max;
const text = (v: unknown, max: number, min = 0): v is string =>
  typeof v === 'string' && [...v].length >= min && [...v].length <= max;
const domain = (v: unknown): v is string => {
  if (
    typeof v !== 'string' ||
    v.length > 253 ||
    !/^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:[a-z]{2,63}|xn--[a-z0-9](?:[a-z0-9-]{0,57}[a-z0-9])?)$/.test(
      v,
    )
  )
    return false;
  return (
    ![
      'localhost',
      'local',
      'lan',
      'home',
      'internal',
      'invalid',
      'test',
      'example',
      'onion',
    ].includes(v.slice(v.lastIndexOf('.') + 1)) &&
    v !== 'home.arpa' &&
    !v.endsWith('.home.arpa')
  );
};

export async function loadImportAddonCatalog(
  csrf: string,
): Promise<ImportAddonCatalog> {
  const value = await shareRequest(
    csrf,
    'importaddoncatalog',
    {},
    262144,
    25000,
  );
  if (
    !object(value) ||
    !exact(value, ['schema_version', 'revision', 'build', 'addons']) ||
    value.schema_version !== 1 ||
    !integer(value.revision, 1, 2147483647) ||
    !integer(value.build, 0, 999999999) ||
    !Array.isArray(value.addons) ||
    value.addons.length > 64
  )
    throw new ShareError('catalog_invalid');
  const ids = new Set<string>();
  for (const addon of value.addons) {
    if (
      !object(addon) ||
      !exact(addon, [
        'id',
        'title',
        'description',
        'attribution',
        'updated_at',
        'revision',
        'min_build',
        'size',
        'sha256',
      ]) ||
      !text(addon.id, 64, 1) ||
      !ID.test(addon.id) ||
      ids.has(addon.id) ||
      !text(addon.title, 120, 1) ||
      !addon.title.trim() ||
      !text(addon.description, 600, 1) ||
      !text(addon.attribution, 240) ||
      !text(addon.updated_at, 20) ||
      !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(addon.updated_at) ||
      !integer(addon.revision, 1, 2147483647) ||
      !integer(addon.min_build, 92, 999999999) ||
      !integer(addon.size, 1, 65536) ||
      !text(addon.sha256, 64) ||
      !HASH.test(addon.sha256)
    )
      throw new ShareError('catalog_invalid');
    ids.add(addon.id);
  }
  return value as unknown as ImportAddonCatalog;
}

export function validImportAddonPreview(
  value: unknown,
): value is ImportAddonPreview[] {
  if (!Array.isArray(value) || value.length > 8) return false;
  const ids = new Set<string>();
  for (const addon of value) {
    if (
      !object(addon) ||
      !exact(addon, ['id', 'title', 'kind', 'domains', 'action', 'note']) ||
      !text(addon.id, 64, 1) ||
      !ID.test(addon.id) ||
      ids.has(addon.id) ||
      !text(addon.title, 120, 1) ||
      !addon.title.trim() ||
      addon.kind !== 'scope_domains_v1' ||
      !Array.isArray(addon.domains) ||
      addon.domains.length > 64 ||
      addon.domains.some((entry) => !domain(entry)) ||
      new Set(addon.domains).size !== addon.domains.length ||
      !['scope_extended', 'already_covered'].includes(String(addon.action)) ||
      !text(addon.note, 4096)
    )
      return false;
    ids.add(addon.id);
  }
  return true;
}

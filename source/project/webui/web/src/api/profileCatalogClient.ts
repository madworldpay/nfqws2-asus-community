import { ShareError, shareRequest } from '@/api/shareClient';

export type CatalogProfile = Readonly<{
  id: string;
  title: string;
  category: 'provider' | 'global';
  provider: string;
  region: string;
  description: string;
  attribution: string;
  updated_at: string;
  revision: number;
  min_build: number;
  size: number;
  sha256: string;
}>;
export type ProfileCatalog = Readonly<{
  schema_version: 1;
  revision: number;
  build: number;
  profiles: CatalogProfile[];
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
  typeof v === 'string' && v.length >= min && [...v].length <= max;

export async function loadProfileCatalog(
  csrf: string,
): Promise<ProfileCatalog> {
  const value = await shareRequest(csrf, 'importcatalog', {}, 262144, 25000);
  if (
    !object(value) ||
    !exact(value, ['schema_version', 'revision', 'build', 'profiles']) ||
    value.schema_version !== 1 ||
    !integer(value.revision, 1, 2147483647) ||
    !integer(value.build, 0, 999999999) ||
    !Array.isArray(value.profiles) ||
    value.profiles.length > 128
  )
    throw new ShareError('catalog_invalid');
  const ids = new Set<string>();
  for (const p of value.profiles) {
    if (
      !object(p) ||
      !exact(p, [
        'id',
        'title',
        'category',
        'provider',
        'region',
        'description',
        'attribution',
        'updated_at',
        'revision',
        'min_build',
        'size',
        'sha256',
      ]) ||
      !text(p.id, 64, 1) ||
      !ID.test(p.id) ||
      ids.has(p.id) ||
      !text(p.title, 120, 1) ||
      !p.title.trim() ||
      (p.category !== 'provider' && p.category !== 'global') ||
      !text(p.provider, 120) ||
      !text(p.region, 120) ||
      !text(p.description, 600, 1) ||
      !text(p.attribution, 240) ||
      !text(p.updated_at, 20) ||
      !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(p.updated_at) ||
      !integer(p.revision, 1, 2147483647) ||
      !integer(p.min_build, 1, 999999999) ||
      !integer(p.size, 1, 4194304) ||
      !text(p.sha256, 64) ||
      !HASH.test(p.sha256)
    )
      throw new ShareError('catalog_invalid');
    ids.add(p.id);
  }
  return value as unknown as ProfileCatalog;
}

export async function loadCatalogDocument(
  csrf: string,
  id: string,
  sha256: string,
): Promise<string> {
  if (!ID.test(id) || !HASH.test(sha256))
    throw new ShareError('catalog_invalid');
  const value = await shareRequest(
    csrf,
    'importcatalogload',
    { id, sha256 },
    8388672,
    25000,
  );
  if (
    !object(value) ||
    !exact(value, ['document']) ||
    typeof value.document !== 'string' ||
    !value.document.length ||
    new TextEncoder().encode(value.document).length > 4194304
  )
    throw new ShareError('catalog_invalid');
  return value.document;
}

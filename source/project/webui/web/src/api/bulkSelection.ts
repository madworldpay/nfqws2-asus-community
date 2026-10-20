import {
  PORT_IMPORT_KEYS,
  SHARED_IMPORT_KEYS,
  type ImportDocument,
  type ImportSelection,
} from '@/api/importClient';
import { STRATEGY_KEYS } from '@/api/shareClient';
import type {
  DnsSelection,
  DnsSource,
  ResourceCopy,
  ResourceMeta,
} from '@/api/shareResourcesClient';

export const selectAllDns = (
  sources: DnsSource[],
  current: DnsSelection[],
): DnsSelection[] =>
  sources.map((source) => {
    const old = current.find(
      (s) => s.source_id === source.id && s.source_sha256 === source.sha256,
    );
    return {
      source_id: source.id,
      source_sha256: source.sha256,
      upstreams: source.profile.upstreams.map(
        (u) => old?.upstreams.find((v) => v.id === u.id) ?? structuredClone(u),
      ),
      records: source.profile.records.map(
        (value, index) =>
          old?.records.find((r) => r.index === index) ?? {
            index,
            value: structuredClone(value),
          },
      ),
    };
  });
export const selectImportFiles = (
  doc: ImportDocument,
  current: ImportSelection,
  kind: ResourceMeta['kind'],
  checked: boolean,
): ImportSelection => {
  if (kind === 'lua') return current;
  const ids = new Set(
    doc.resources.filter((f) => f.kind === kind).map((f) => f.id),
  );
  return {
    ...current,
    files: checked
      ? [
          ...current.files,
          ...[...ids]
            .filter((id) => !current.files.some((f) => f.id === id))
            .map((id) => ({ id })),
        ]
      : current.files.filter((f) => !ids.has(f.id)),
  };
};
export const selectAllImport = (
  doc: ImportDocument,
  current: ImportSelection,
): ImportSelection => {
  const picks = (
    keys: readonly string[],
    source: Record<string, string>,
    old: { key: string; value: string }[],
  ) =>
    keys
      .filter((key) => typeof source[key] === 'string')
      .map(
        (key) => old.find((v) => v.key === key) ?? { key, value: source[key] },
      );
  return {
    ...current,
    blocks: picks(STRATEGY_KEYS, doc.values, current.blocks),
    shared: picks(SHARED_IMPORT_KEYS, doc.values, current.shared),
    ports: picks(PORT_IMPORT_KEYS, doc.ports, current.ports),
    files: doc.resources
      .filter((f) => f.kind !== 'lua')
      .map((f) => current.files.find((v) => v.id === f.id) ?? { id: f.id }),
    dns: selectAllDns(doc.dns_sources, current.dns),
  };
};
export async function readBulkResources(
  metas: ResourceMeta[],
  previous: Record<string, ResourceCopy>,
  read: (meta: ResourceMeta) => Promise<ResourceCopy>,
  kind?: ResourceMeta['kind'],
): Promise<{ selected: string[]; copies: Record<string, ResourceCopy> }> {
  const selected: string[] = [],
    copies = { ...previous };
  for (const meta of metas)
    if (
      meta.kind !== 'lua' &&
      (!kind || meta.kind === kind) &&
      meta.state === 'available'
    ) {
      if (!copies[meta.id] || copies[meta.id].sha256 !== meta.sha256)
        copies[meta.id] = await read(meta);
      selected.push(meta.id);
    }
  return { selected, copies };
}

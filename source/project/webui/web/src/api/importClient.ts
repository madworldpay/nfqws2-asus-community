import { ShareError, shareRequest, STRATEGY_KEYS } from '@/api/shareClient';
import {
  resourceBytes,
  type DnsSelection,
  type DnsSource,
  type ResourceCopy,
} from '@/api/shareResourcesClient';
import type { Profile } from '@/api/smartDnsProfile';
import { newSupportSubmissionId } from '@/api/supportReport';

export const SHARED_IMPORT_KEYS = [
  'NFQWS_BASE_ARGS',
  'NFQWS_EXTRA_ARGS',
  'NFQWS_ARGS_IPSET',
  'MODE_LIST',
  'MODE_ALL',
  'MODE_AUTO',
] as const;
export const PORT_IMPORT_KEYS = ['TCP_PORTS', 'UDP_PORTS'] as const;
export type ImportDocument = {
  values: Record<string, string>;
  ports: Record<string, string>;
  resources: (ResourceCopy & { aliases: string[] })[];
  dns_sources: DnsSource[];
  context: Record<string, unknown> | null;
  source: Record<string, unknown> | null;
  ignored: string[];
  input_sha256: string;
};
export type ImportSelection = {
  blocks: { key: string; value: string }[];
  shared: { key: string; value: string }[];
  ports: { key: string; value: string }[];
  files: { id: string; text?: string }[];
  dns: DnsSelection[];
  allow_shared_impact: boolean;
  allow_incomplete: boolean;
  trusted_lua: boolean;
};
export type ImportPlan = {
  ready: boolean;
  problems: {
    code: string;
    key?: string;
    name?: string;
    alias?: string;
    field?: string;
    id?: string;
  }[];
  warnings: { source?: string; kind: string; name?: string }[];
  required: { files: string[]; shared: string[] };
  affected_blocks: string[];
  config: string;
  changes: { key: string; before: string | null; after: string }[];
  files: (ResourceCopy & {
    path: string;
    reuse: boolean;
    replace: boolean;
    target_name: string;
  })[];
  draft: Profile | null;
  old_draft: Profile | null;
  digest: string;
  proof: string | null;
};
export type ImportStatus = {
  state:
    | 'idle'
    | 'prepared'
    | 'committing'
    | 'committed'
    | 'undoing'
    | 'undone'
    | 'rolled_back'
    | 'restore_required';
  id: string | null;
  can_undo: boolean;
  config_saved: boolean;
  dns_draft_saved: boolean;
  undo_proof?: string | null;
};
export const emptyImportSelection = (): ImportSelection => ({
  blocks: [],
  shared: [],
  ports: [],
  files: [],
  dns: [],
  allow_shared_impact: false,
  allow_incomplete: false,
  trusted_lua: false,
});
const obj = (v: unknown): v is Record<string, unknown> =>
  typeof v === 'object' && v !== null && !Array.isArray(v);
const hash = (v: unknown): v is string =>
  typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const id = (v: unknown): v is string =>
  typeof v === 'string' && /^[a-f0-9]{32}$/.test(v);
const invalid = (): never => {
  throw new ShareError('invalid_response');
};
const map = (v: unknown, keys: readonly string[]): Record<string, string> => {
  if (Array.isArray(v) && v.length === 0) return {};
  if (
    !obj(v) ||
    Object.entries(v).some(
      ([k, x]) => !keys.includes(k) || typeof x !== 'string',
    )
  )
    return invalid();
  return v as Record<string, string>;
};
export async function readImportFiles(files: File[]): Promise<string[]> {
  if (
    !files.length ||
    files.length > 5 ||
    files.reduce((n, f) => n + f.size, 0) > 4194304
  )
    throw new ShareError('import_limit');
  return Promise.all(
    files.map(async (f) => {
      const bytes = await f.arrayBuffer();
      if (bytes.byteLength !== f.size || !f.size)
        throw new ShareError('invalid_import');
      return new TextDecoder('utf-8', { fatal: true }).decode(bytes);
    }),
  );
}
export async function inspectImport(
  csrf: string,
  documents: string[],
): Promise<ImportDocument> {
  const v = await shareRequest(
    csrf,
    'importinspect',
    { documents: JSON.stringify(documents) },
    4194304,
    30000,
  );
  if (
    !obj(v) ||
    !Array.isArray(v.resources) ||
    v.resources.length > 128 ||
    !Array.isArray(v.dns_sources) ||
    v.dns_sources.length > 3 ||
    !Array.isArray(v.ignored) ||
    !hash(v.input_sha256) ||
    !(v.context === null || obj(v.context)) ||
    !(v.source === null || obj(v.source))
  )
    return invalid();
  const values = map(v.values, [...STRATEGY_KEYS, ...SHARED_IMPORT_KEYS]);
  const ports = map(v.ports, PORT_IMPORT_KEYS);
  let bytes = 0;
  const seen = new Set<string>();
  for (const row of v.resources) {
    if (
      !obj(row) ||
      !id(row.id) ||
      seen.has(row.id) ||
      !['lists', 'lua', 'blobs'].includes(String(row.kind)) ||
      typeof row.name !== 'string' ||
      row.name === '.' ||
      row.name === '..' ||
      row.name.includes('/') ||
      row.name.includes('\\') ||
      Array.from(row.name).some(
        (c) => c.charCodeAt(0) < 32 || c.charCodeAt(0) === 127,
      ) ||
      !Array.isArray(row.aliases)
    )
      return invalid();
    seen.add(row.id);
    bytes += resourceBytes(row as ImportDocument['resources'][number]).length;
  }
  if (bytes > 524288) return invalid();
  for (const s of v.dns_sources)
    if (
      !obj(s) ||
      !['active', 'draft', 'legacy'].includes(String(s.id)) ||
      s.id !== s.origin ||
      !hash(s.sha256) ||
      !obj(s.profile) ||
      s.profile.schema_version !== 1 ||
      !Array.isArray(s.profile.upstreams) ||
      !Array.isArray(s.profile.records) ||
      typeof s.complete !== 'boolean' ||
      !Array.isArray(s.warnings)
    )
      return invalid();
  return { ...v, values, ports } as ImportDocument;
}
export const selectImportDependencies = (
  selection: ImportSelection,
  doc: ImportDocument,
  required: ImportPlan['required'],
): ImportSelection => ({
  ...selection,
  files: [
    ...selection.files,
    ...required.files
      .filter(
        (id) =>
          !selection.files.some((f) => f.id === id) &&
          doc.resources.some((f) => f.id === id && f.kind !== 'lua'),
      )
      .map((id) => ({ id })),
  ],
  shared: [
    ...selection.shared,
    ...required.shared
      .filter(
        (key) =>
          !selection.shared.some((s) => s.key === key) &&
          typeof doc.values[key] === 'string',
      )
      .map((key) => ({ key, value: doc.values[key] })),
  ],
});
export async function prepareImport(
  csrf: string,
  documents: string[],
  selection: ImportSelection,
): Promise<ImportPlan> {
  const v = await shareRequest(
    csrf,
    'importprepare',
    {
      documents: JSON.stringify(documents),
      selection: JSON.stringify(selection),
    },
    4194304,
    30000,
  );
  if (
    !obj(v) ||
    typeof v.ready !== 'boolean' ||
    !Array.isArray(v.problems) ||
    !Array.isArray(v.warnings) ||
    !obj(v.required) ||
    !Array.isArray(v.required.files) ||
    !Array.isArray(v.required.shared) ||
    !Array.isArray(v.affected_blocks) ||
    typeof v.config !== 'string' ||
    !Array.isArray(v.changes) ||
    !Array.isArray(v.files) ||
    v.files.length > 128 ||
    !hash(v.digest) ||
    (v.ready ? typeof v.proof !== 'string' : v.proof !== null)
  )
    return invalid();
  for (const f of v.files) {
    if (
      !obj(f) ||
      typeof f.path !== 'string' ||
      !/^\/opt\/etc\/nfqws2\/(lists|lua|blobs)\/[A-Za-z0-9_.-]{1,128}$/.test(
        f.path,
      ) ||
      typeof f.reuse !== 'boolean' ||
      typeof f.replace !== 'boolean'
    )
      return invalid();
    resourceBytes(f as ImportPlan['files'][number]);
  }
  return v as ImportPlan;
}
const status = (v: unknown): ImportStatus => {
  if (
    !obj(v) ||
    ![
      'idle',
      'prepared',
      'committing',
      'committed',
      'undoing',
      'undone',
      'rolled_back',
      'restore_required',
    ].includes(String(v.state)) ||
    !(v.id === null || id(v.id)) ||
    typeof v.can_undo !== 'boolean' ||
    typeof v.config_saved !== 'boolean' ||
    typeof v.dns_draft_saved !== 'boolean' ||
    !(
      v.undo_proof === undefined ||
      v.undo_proof === null ||
      typeof v.undo_proof === 'string'
    )
  )
    return invalid();
  return v as ImportStatus;
};
export async function importStatus(csrf: string): Promise<ImportStatus> {
  return status(await shareRequest(csrf, 'importstatus'));
}
export async function applyImport(
  csrf: string,
  documents: string[],
  selection: ImportSelection,
  proof: string,
  request_id: string,
): Promise<ImportStatus> {
  return status(
    await shareRequest(
      csrf,
      'importapply',
      {
        documents: JSON.stringify(documents),
        selection: JSON.stringify(selection),
        proof,
        request_id,
      },
      32768,
      45000,
    ),
  );
}
export async function undoImport(
  csrf: string,
  id: string,
  proof: string,
): Promise<ImportStatus> {
  return status(
    await shareRequest(csrf, 'importundo', { id, proof }, 32768, 45000),
  );
}
export function newImportRequestId(): string {
  return newSupportSubmissionId().replace(/-/g, '');
}

export { ShareError as ImportError };
export function importOutcomeUnknown(error: unknown): boolean {
  return !(
    error instanceof ShareError &&
    [
      'source_changed',
      'stale_preview',
      'busy',
      'request_conflict',
      'invalid_request',
      'invalid_import',
      'invalid_proof',
      'forbidden',
      'unauthorized',
      'import_not_ready',
    ].includes(error.code)
  );
}

import type { DpiStatus } from '@/api/dpiClient';
import { sha256 } from '@/api/supportDigest';
import {
  newSupportSubmissionId,
  type SupportMailResult,
  type SupportReportFile,
} from '@/api/supportReport';

export const STRATEGY_KEYS = [
  'NFQWS_ARGS',
  'NFQWS_ARGS_QUIC',
  'NFQWS_ARGS_UDP',
  'NFQWS_ARGS_CUSTOM',
] as const;
export type StrategyKey = (typeof STRATEGY_KEYS)[number];
export type StrategyBlock = { key: StrategyKey; value: string };
export type StrategyDraft = { blocks: StrategyBlock[]; config: string };
export type StrategyContext = {
  purpose: string;
  operator: string;
  comment: string;
  region: string;
  share_location: boolean;
};
export type ShareSelection = {
  version?: 3 | 4;
  resources?: {
    files: { id: string; source_sha256: string; text?: string }[];
    missing_reason: string;
  };
  dns?: import('./shareResourcesClient').DnsSelection[];
  context?: Omit<StrategyContext, 'region'> & { region?: string };
  analysis_config_sha256?: string;
  report?: { raw: string; filename: string; proof: string };
  dpi?: { kind: 'saved' | 'legacy'; id: string };
  strategy?:
    | {
        mode: 'blocks';
        draft: { blocks: StrategyBlock[] };
        context: Omit<StrategyContext, 'region'> & { region?: string };
      }
    | {
        mode: 'config';
        config: string;
        context: Omit<StrategyContext, 'region'> & { region?: string };
      };
  link_installation?: boolean;
};
export type ShareSource = Readonly<{
  model: string;
  firmware: Readonly<{
    firmver: string | null;
    buildno: string | null;
    extendno: string | null;
  }>;
  kernel: string | null;
  versions: Readonly<{ core: string; web: string }>;
  installation_id?: string;
}>;
export type ShareWire = Readonly<{
  type: 'report' | 'dpi' | 'strategy' | 'resources' | 'dns';
  filename: string;
  byte_length: number;
  sha256: string;
  data_base64: string;
}>;
export type PreparedShare = Readonly<{
  version?: 3 | 4;
  wire: readonly ShareWire[];
  files: readonly (SupportReportFile & {
    type: ShareWire['type'];
    text: string;
  })[];
  proof: string;
  source?: ShareSource;
}>;
export type SavedReport = {
  id: string;
  filename: string;
  bytes: number;
  sha256: string;
};
export type SavedReports = {
  reports: SavedReport[];
  code: string;
  skipped: number;
  scan_truncated: boolean;
};
export type ShareState = {
  mail: {
    configured: boolean;
    sharing_v3: boolean;
    sharing_v4?: boolean;
    code: string;
  };
  dpi: DpiStatus;
  saved: SavedReports;
};
export type ShareLocation =
  | { available: false }
  | {
      available: true;
      country: string;
      region: string;
      city: string;
      database_age_days: number;
    };
export class ShareError extends Error {
  code: string;
  constructor(code: string) {
    super(code);
    this.code = code;
  }
}
const UUID =
  /^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/;
const ID = /^[a-f0-9]{32}$/;
const NAME =
  /^NFQWS2_[A-Za-z0-9_-]+_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}Z\.json$/;
const object = (v: unknown): v is Record<string, unknown> =>
  typeof v === 'object' && v !== null && !Array.isArray(v);
function exact(
  v: unknown,
  keys: string[],
  required = keys,
): v is Record<string, unknown> {
  return (
    object(v) &&
    Object.keys(v).every((k) => keys.includes(k)) &&
    required.every((k) => k in v)
  );
}
async function read(response: Response, max: number): Promise<unknown> {
  if (
    !/^application\/json(?:;|$)/i.test(
      response.headers.get('Content-Type') ?? '',
    ) ||
    Number(response.headers.get('Content-Length') ?? 0) > max
  )
    throw new ShareError('invalid_response');
  const reader = response.body?.getReader();
  if (!reader) throw new ShareError('invalid_response');
  const chunks: Uint8Array<ArrayBuffer>[] = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > max) throw new ShareError('invalid_response');
      chunks.push(new Uint8Array(value));
    }
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
  return JSON.parse(
    new TextDecoder('utf-8', { fatal: true }).decode(
      await new Blob(chunks).arrayBuffer(),
    ),
  );
}
export async function shareRequest(
  csrf: string,
  cmd: string,
  params: Record<string, string> = {},
  max = 2097152,
  timeout = 15000,
): Promise<unknown> {
  const response = await fetch('/index.php', {
    method: 'POST',
    credentials: 'same-origin',
    redirect: 'error',
    body: new URLSearchParams({ cmd, csrf_token: csrf, ...params }),
    signal: AbortSignal.timeout(timeout),
  });
  const value = await read(response, max);
  if (!response.ok)
    throw new ShareError(
      response.status === 401
        ? 'unauthorized'
        : response.status === 403
          ? 'forbidden'
          : object(value) && typeof value.error === 'string'
            ? value.error
            : 'unavailable',
    );
  return value;
}
function source(value: unknown): ShareSource {
  if (
    !exact(
      value,
      ['model', 'firmware', 'kernel', 'versions', 'installation_id'],
      ['model', 'firmware', 'kernel', 'versions'],
    ) ||
    typeof value.model !== 'string' ||
    value.model.length > 64 ||
    !exact(value.firmware, ['firmver', 'buildno', 'extendno']) ||
    !Object.values(value.firmware).every(
      (v) => v === null || (typeof v === 'string' && v.length <= 64),
    ) ||
    !exact(value.versions, ['core', 'web']) ||
    !Object.values(value.versions).every(
      (v) => typeof v === 'string' && /^[A-Za-z0-9.+_-]{1,64}$/.test(v),
    ) ||
    !(
      value.kernel === null ||
      (typeof value.kernel === 'string' && value.kernel.length <= 64)
    ) ||
    (value.installation_id !== undefined &&
      !(
        typeof value.installation_id === 'string' &&
        ID.test(value.installation_id)
      ))
  )
    throw new ShareError('invalid_response');
  return Object.freeze({
    ...value,
    firmware: Object.freeze({ ...value.firmware }),
    versions: Object.freeze({ ...value.versions }),
  }) as ShareSource;
}
export async function prepareShare(
  selection: ShareSelection,
  csrf: string,
): Promise<PreparedShare> {
  const version = selection.version ?? 3;
  // The original v3 request has no version field; v4 explicitly opts in.
  const requestSelection = { ...selection };
  if (version === 3) delete requestSelection.version;
  const value = await shareRequest(
    csrf,
    'shareprepare',
    {
      selection: JSON.stringify(requestSelection),
    },
    version === 4 ? 4194304 : 2097152,
  );
  if (
    !exact(
      value,
      ['version', 'files', 'source', 'proof'],
      ['files', 'proof'],
    ) ||
    (version === 4
      ? value.version !== 4
      : value.version !== undefined && value.version !== 3) ||
    !Array.isArray(value.files) ||
    value.files.length < 1 ||
    value.files.length > (version === 4 ? 5 : 3) ||
    typeof value.proof !== 'string' ||
    !new RegExp(
      `^v${version}\\.[1-9][0-9]{0,9}\\.[a-f0-9]{32}\\.[a-f0-9]{64}$`,
    ).test(value.proof)
  )
    throw new ShareError('invalid_response');
  const files = [];
  const wire: ShareWire[] = [];
  let last = -1;
  for (const f of value.files) {
    if (!exact(f, ['type', 'filename', 'byte_length', 'sha256', 'data_base64']))
      throw new ShareError('invalid_response');
    const type = f.type as ShareWire['type'];
    const at = (
      version === 4
        ? ['report', 'dpi', 'strategy', 'resources', 'dns']
        : ['report', 'dpi', 'strategy']
    ).indexOf(type);
    const max = [1048576, 262144, 65536, 786432, 131072][at];
    if (
      at <= last ||
      at < 0 ||
      typeof f.filename !== 'string' ||
      !NAME.test(f.filename) ||
      f.filename.length > 128 ||
      !Number.isInteger(f.byte_length) ||
      Number(f.byte_length) < 1 ||
      Number(f.byte_length) > max ||
      typeof f.sha256 !== 'string' ||
      !/^[a-f0-9]{64}$/.test(f.sha256) ||
      typeof f.data_base64 !== 'string' ||
      f.data_base64.length > 4 * Math.ceil(max / 3)
    )
      throw new ShareError('invalid_response');
    const decoded = atob(f.data_base64);
    if (btoa(decoded) !== f.data_base64 || decoded.length !== f.byte_length)
      throw new ShareError('invalid_response');
    const bytes = Uint8Array.from(decoded, (c) => c.charCodeAt(0));
    if (sha256(bytes) !== f.sha256) throw new ShareError('invalid_response');
    const text = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
    const data = JSON.parse(text);
    if (
      !object(data) ||
      (type === 'report' &&
        (data.schema_version !== 1 ||
          typeof data.complete !== 'boolean' ||
          typeof data.model !== 'string' ||
          typeof data.captured_at !== 'string' ||
          f.filename !==
            `NFQWS2_${data.model}_${data.captured_at.slice(0, -1).replace('T', '_').replace(/:/g, '-')}Z.json`)) ||
      (type === 'dpi' &&
        (!f.filename.startsWith('NFQWS2_DPI_') ||
          !(
            (data.type === 'nfqws2_dpi_saved' && data.schema_version === 1) ||
            (data.type === 'nfqws2_dpi' &&
              [1, 2].includes(Number(data.schema_version)))
          ) ||
          !Array.isArray(data.groups) ||
          !data.groups.length)) ||
      (type === 'strategy' &&
        (!f.filename.startsWith('NFQWS2_STRATEGY_') ||
          data.type !== 'nfqws2_strategy' ||
          data.schema_version !== (version === 4 ? 2 : 1) ||
          !['blocks', 'config'].includes(String(data.mode)))) ||
      (type === 'resources' &&
        (!f.filename.startsWith('NFQWS2_RESOURCES_') ||
          data.type !== 'nfqws2_resources' ||
          data.schema_version !== 1 ||
          !Array.isArray(data.files) ||
          !object(data.audit))) ||
      (type === 'dns' &&
        (!f.filename.startsWith('NFQWS2_DNS_') ||
          data.type !== 'nfqws2_dns' ||
          data.schema_version !== 1 ||
          !Array.isArray(data.sources)))
    )
      throw new ShareError('invalid_response');
    files.push(
      Object.freeze({
        type,
        filename: f.filename,
        blob: new Blob([bytes], { type: 'application/json' }),
        text,
        complete:
          type === 'report'
            ? data.complete === true
            : type === 'dpi'
              ? data.state === 'completed'
              : type === 'resources'
                ? (data.audit as { complete?: boolean }).complete === true
                : type === 'dns'
                  ? (data.sources as { complete: boolean }[]).every(
                      (s) => s.complete,
                    )
                  : true,
      }),
    );
    wire.push(Object.freeze({ ...f }) as ShareWire);
    last = at;
  }
  const origin = value.source !== undefined ? source(value.source) : undefined;
  if (origin?.installation_id && selection.link_installation !== true)
    throw new ShareError('invalid_response');
  return Object.freeze({
    version,
    wire: Object.freeze(wire),
    files: Object.freeze(files),
    proof: value.proof,
    ...(origin ? { source: origin } : {}),
  });
}
const pending = new WeakMap<PreparedShare, Promise<SupportMailResult>>();
const terminal = new WeakMap<PreparedShare, SupportMailResult>();
export function sendShare(
  snapshot: PreparedShare,
  csrf: string,
  submissionId: string,
): Promise<SupportMailResult> {
  const old = terminal.get(snapshot);
  if (old) return Promise.resolve(old);
  const active = pending.get(snapshot);
  if (active) return active;
  const perform = async (): Promise<SupportMailResult> => {
    if (!UUID.test(submissionId)) throw new ShareError('invalid_request');
    const envelope = JSON.stringify({
      version: snapshot.version ?? 3,
      submission_id: submissionId,
      files: snapshot.wire,
      ...(snapshot.source ? { source: snapshot.source } : {}),
    });
    if (
      new Blob([envelope]).size >
      ((snapshot.version ?? 3) === 4 ? 4194304 : 2097152)
    )
      throw new ShareError('output_limit');
    const unknown: SupportMailResult = {
      state: 'unknown',
      submissionId,
      code: 'delivery_unknown',
    };
    try {
      const response = await fetch('/index.php', {
        method: 'POST',
        credentials: 'same-origin',
        redirect: 'error',
        signal: AbortSignal.timeout(20000),
        body: new URLSearchParams({
          cmd: 'sharesend',
          csrf_token: csrf,
          consent: 'send',
          submission_id: submissionId,
          proof: snapshot.proof,
          envelope,
        }),
      });
      if ([400, 401, 403].includes(response.status))
        throw new ShareError(
          response.status === 401
            ? 'unauthorized'
            : response.status === 403
              ? 'forbidden'
              : 'invalid_request',
        );
      const v = await read(response, 4096);
      const statuses: Record<string, number> = {
        accepted: 200,
        failed_safe: 503,
        unknown: 503,
        busy: 409,
        limited: 429,
        invalid: 422,
      };
      if (
        !exact(v, ['state', 'submission_id', 'code']) ||
        v.submission_id !== submissionId ||
        typeof v.state !== 'string' ||
        typeof v.code !== 'string' ||
        ![
          'smtp_accepted',
          'transport_failed',
          'delivery_unknown',
          'busy',
          'rate_limited',
          'invalid_request',
          'id_conflict',
          'invalid_share',
          'not_configured',
          'https_unavailable',
          'invalid_config',
        ].includes(v.code) ||
        (statuses[v.state] !== response.status &&
          !(
            v.state === 'invalid' &&
            v.code === 'id_conflict' &&
            response.status === 409
          ))
      )
        return unknown;
      return {
        state: v.state as SupportMailResult['state'],
        submissionId,
        code: v.code,
      };
    } catch (error) {
      if (error instanceof ShareError) throw error;
      return unknown;
    }
  };
  const promise = perform().then((v) => {
    if (v.state === 'accepted' || v.state === 'unknown')
      terminal.set(snapshot, v);
    return v;
  });
  pending.set(snapshot, promise);
  void promise.then(
    () => pending.delete(snapshot),
    () => pending.delete(snapshot),
  );
  return promise;
}
function reports(value: unknown): SavedReports {
  if (
    !object(value) ||
    !Array.isArray(value.reports) ||
    value.reports.length > 20 ||
    typeof value.code !== 'string' ||
    typeof value.skipped !== 'number' ||
    typeof value.scan_truncated !== 'boolean'
  )
    throw new ShareError('invalid_response');
  for (const r of value.reports)
    if (
      !object(r) ||
      typeof r.id !== 'string' ||
      !ID.test(r.id) ||
      typeof r.filename !== 'string' ||
      !/^dpi_detector_results-\d{8}-\d{6}\.txt$/.test(r.filename) ||
      typeof r.bytes !== 'number' ||
      !Number.isInteger(r.bytes) ||
      r.bytes < 1 ||
      r.bytes > 1048576 ||
      typeof r.sha256 !== 'string' ||
      !/^[a-f0-9]{64}$/.test(r.sha256)
    )
      throw new ShareError('invalid_response');
  return value as SavedReports;
}
export async function getShareState(csrf: string): Promise<ShareState> {
  const v = await shareRequest(csrf, 'sharestates');
  if (
    !object(v) ||
    !object(v.mail) ||
    typeof v.mail.configured !== 'boolean' ||
    typeof v.mail.sharing_v3 !== 'boolean' ||
    typeof v.mail.code !== 'string' ||
    !object(v.dpi) ||
    !object(v.dpi.installed) ||
    typeof v.dpi.installed.installed !== 'boolean' ||
    !Array.isArray(v.dpi.history)
  )
    throw new ShareError('invalid_response');
  reports(v.saved);
  return v as ShareState;
}
export async function refreshSaved(csrf: string): Promise<SavedReports> {
  return reports(await shareRequest(csrf, 'sharesavedrefresh'));
}
export async function readSaved(
  csrf: string,
  id: string,
): Promise<{ raw: string; sha256: string; filename: string }> {
  if (!ID.test(id)) throw new ShareError('invalid_request');
  const v = await shareRequest(csrf, 'sharesavedread', { id }, 8388608);
  if (
    !exact(v, ['raw', 'sha256', 'filename']) ||
    typeof v.raw !== 'string' ||
    new Blob([v.raw]).size > 1048576 ||
    typeof v.sha256 !== 'string' ||
    sha256(new TextEncoder().encode(v.raw)) !== v.sha256 ||
    typeof v.filename !== 'string' ||
    !/^dpi_detector_results-\d{8}-\d{6}\.txt$/.test(v.filename)
  )
    throw new ShareError('invalid_response');
  return v as { raw: string; sha256: string; filename: string };
}
export async function deleteSaved(csrf: string, id: string): Promise<void> {
  if (!ID.test(id)) throw new ShareError('invalid_request');
  const v = await shareRequest(csrf, 'sharesaveddelete', { id });
  if (!exact(v, ['deleted']) || v.deleted !== true)
    throw new ShareError('invalid_response');
}
export async function getStrategyDraft(csrf: string): Promise<StrategyDraft> {
  const v = await shareRequest(csrf, 'sharestrategydraft');
  if (
    !exact(v, ['blocks', 'config']) ||
    !Array.isArray(v.blocks) ||
    v.blocks.length > 4 ||
    typeof v.config !== 'string' ||
    new Blob([v.config]).size > 262144
  )
    throw new ShareError('invalid_response');
  const seen = new Set();
  for (const b of v.blocks) {
    if (
      !exact(b, ['key', 'value']) ||
      !STRATEGY_KEYS.includes(b.key as StrategyKey) ||
      seen.has(b.key) ||
      typeof b.value !== 'string' ||
      new Blob([b.value]).size > 65536
    )
      throw new ShareError('invalid_response');
    seen.add(b.key);
  }
  return v as StrategyDraft;
}
export async function getShareLocation(csrf: string): Promise<ShareLocation> {
  const v = await shareRequest(csrf, 'sharelocation', {}, 4096, 6000);
  if (!object(v) || typeof v.available !== 'boolean')
    throw new ShareError('invalid_response');
  if (!v.available) return { available: false };
  if (
    !exact(v, [
      'available',
      'country',
      'region',
      'city',
      'database_age_days',
    ]) ||
    typeof v.country !== 'string' ||
    !/^[A-Z]{2}$/.test(v.country) ||
    !['region', 'city'].every(
      (k) =>
        typeof v[k] === 'string' &&
        v[k].length <= 120 &&
        !Array.from(v[k]).some(
          (c) =>
            c.charCodeAt(0) < 32 ||
            (c.charCodeAt(0) >= 127 && c.charCodeAt(0) <= 159),
        ),
    ) ||
    !Number.isInteger(v.database_age_days) ||
    Number(v.database_age_days) < 0 ||
    Number(v.database_age_days) > 62
  )
    throw new ShareError('invalid_response');
  return v as ShareLocation;
}
export function autoLocation(
  current: string,
  edited: boolean,
  location: ShareLocation,
): string {
  return edited || !location.available
    ? current
    : [
        ...new Set(
          [location.country, location.region, location.city].filter(Boolean),
        ),
      ]
        .join(', ')
        .slice(0, 120);
}
export function strategyContext(
  context: StrategyContext,
): Omit<StrategyContext, 'region'> & { region?: string } {
  const { region, ...rest } = context;
  return context.share_location ? { ...rest, region } : rest;
}

export async function saveShare(
  snapshot: PreparedShare,
): Promise<'native' | 'browser'> {
  const blob = new Blob(
    [
      JSON.stringify(
        {
          version: snapshot.version ?? 3,
          submission_id: newSupportSubmissionId(),
          source: snapshot.source,
          files: snapshot.wire,
        },
        null,
        2,
      ) + '\n',
    ],
    { type: 'application/json' },
  );
  if (blob.size > ((snapshot.version ?? 3) === 4 ? 4194304 : 2097152))
    throw new ShareError('output_limit');
  const filename = `NFQWS2_SHARE_${new Date().toISOString().slice(0, 19).replace('T', '_').replace(/:/g, '-')}Z.json`;
  const picker = window as Window & {
    showSaveFilePicker?: (o: unknown) => Promise<{
      createWritable: () => Promise<{
        write: (b: Blob) => Promise<void>;
        close: () => Promise<void>;
        abort: () => Promise<void>;
      }>;
    }>;
  };
  if (window.isSecureContext && picker.showSaveFilePicker) {
    const handle = await picker.showSaveFilePicker({
      suggestedName: filename,
      types: [
        {
          description: 'NFQWS2 (JSON)',
          accept: { 'application/json': ['.json'] },
        },
      ],
    });
    const writable = await handle.createWritable();
    try {
      await writable.write(blob);
      await writable.close();
    } catch (e) {
      await writable.abort().catch(() => {});
      throw e;
    }
    return 'native';
  }
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  try {
    anchor.href = url;
    anchor.download = filename;
    document.body.append(anchor);
    anchor.click();
  } finally {
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return 'browser';
}

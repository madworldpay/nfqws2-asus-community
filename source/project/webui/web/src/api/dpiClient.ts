export type DpiState =
  | 'queued'
  | 'running'
  | 'completed'
  | 'partial'
  | 'cancelled'
  | 'timed_out'
  | 'failed'
  | 'interrupted';
export type DpiJob = {
  id: string;
  kind: 'install' | 'run';
  state: DpiState;
  started_at: number;
  finished_at: number | null;
  code: string | null;
  tests: number[];
  completed_tests: number[];
  current_group: number | null;
  native_available?: boolean;
};
export type DpiStatus = {
  available: { available: boolean; code: string };
  installed: { installed: boolean; version: string | null };
  version: string;
  default_tests: number[];
  active: DpiJob | null;
  history: DpiJob[];
};
export type DpiFile = {
  kind: 'analysis';
  blob: Blob;
  filename: string;
  jobId: string;
  startedAt: string;
  complete: boolean;
};
export class DpiError extends Error {
  code: string;
  field?: string;
  constructor(code: string, field?: string) {
    super(code);
    this.code = code;
    this.field = field;
  }
}
const JOB = /^[a-f0-9]{32}$/;
const UUID =
  /^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/;
export async function request(
  csrf: string,
  cmd: string,
  params: Record<string, string> = {},
  max = 16384,
): Promise<{ value: unknown; text: string; response: Response }> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch('/index.php', {
      method: 'POST',
      credentials: 'same-origin',
      body: new URLSearchParams({ cmd, csrf_token: csrf, ...params }),
      signal: controller.signal,
    });
    if (
      !/^application\/json(?:;|$)/i.test(
        response.headers.get('Content-Type') ?? '',
      )
    )
      throw new DpiError('invalid_response');
    if (Number(response.headers.get('Content-Length') ?? 0) > max)
      throw new DpiError('invalid_response');
    const reader = response.body?.getReader();
    if (!reader) throw new DpiError('invalid_response');
    let size = 0;
    const chunks: Uint8Array<ArrayBuffer>[] = [];
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        size += value.byteLength;
        if (size > max) throw new DpiError('invalid_response');
        chunks.push(new Uint8Array(value));
      }
    } finally {
      await reader.cancel().catch(() => {});
      reader.releaseLock();
    }
    const text = new TextDecoder('utf-8', { fatal: true }).decode(
      await new Blob(chunks).arrayBuffer(),
    );
    const value: unknown = JSON.parse(text);
    if (!response.ok) {
      const error =
        typeof value === 'object' && value !== null && 'error' in value
          ? String(value.error)
          : 'request_failed';
      throw new DpiError(
        response.status === 401
          ? 'unauthorized'
          : response.status === 403
            ? 'forbidden'
            : /^[a-z_]{1,40}$/.test(error)
              ? error
              : 'request_failed',
        typeof value === 'object' &&
          value !== null &&
          'field' in value &&
          typeof value.field === 'string' &&
          /^[a-zA-Z0-9_.]{1,100}$/.test(value.field)
          ? value.field
          : undefined,
      );
    }
    return { value, text, response };
  } catch (e) {
    if (e instanceof DpiError) throw e;
    throw new DpiError(
      controller.signal.aborted ? 'timeout' : 'request_failed',
    );
  } finally {
    clearTimeout(timer);
  }
}
function id(id: string) {
  if (!JOB.test(id)) throw new DpiError('invalid_request');
  return id;
}
function req(id: string) {
  if (!UUID.test(id)) throw new DpiError('invalid_request');
  return id;
}
function job(value: unknown): DpiJob {
  const j = value as DpiJob;
  if (
    !j ||
    !JOB.test(j.id) ||
    ![
      'queued',
      'running',
      'completed',
      'partial',
      'cancelled',
      'timed_out',
      'failed',
      'interrupted',
    ].includes(j.state) ||
    !Array.isArray(j.tests) ||
    !Array.isArray(j.completed_tests)
  )
    throw new DpiError('invalid_response');
  return j;
}
export async function getDpiStatus(csrf: string): Promise<DpiStatus> {
  const { value } = await request(csrf, 'dpistatus');
  const s = value as DpiStatus;
  if (
    typeof s?.available?.available !== 'boolean' ||
    typeof s.installed?.installed !== 'boolean' ||
    !Array.isArray(s.history) ||
    s.history.length > 3
  )
    throw new DpiError('invalid_response');
  if (s.active !== null) job(s.active);
  s.history.forEach(job);
  return s;
}
export async function installDpi(
  csrf: string,
  requestId: string,
): Promise<DpiJob> {
  return job(
    (
      await request(csrf, 'dpiinstall', {
        request_id: req(requestId),
        consent: 'install',
      })
    ).value,
  );
}
export async function startDpi(
  csrf: string,
  requestId: string,
  groups: number[],
  heavyConsent: number[],
  options: Record<string, unknown> = {},
): Promise<DpiJob> {
  if (
    !groups.length ||
    groups.some(
      (g, i) =>
        !Number.isInteger(g) || g < 0 || g > 6 || (i > 0 && g <= groups[i - 1]),
    ) ||
    heavyConsent.join('') !== groups.filter((g) => g === 5 || g === 6).join('')
  )
    throw new DpiError('invalid_request');
  return job(
    (
      await request(csrf, 'dpistart', {
        request_id: req(requestId),
        tests: groups.join(''),
        heavy_consent: heavyConsent.join(''),
        options: JSON.stringify(options),
      })
    ).value,
  );
}
export async function stopDpi(
  csrf: string,
  jobId: string,
): Promise<{ id: string; state: 'stopping' }> {
  const { value } = await request(csrf, 'dpistop', { job_id: id(jobId) });
  const v = value as { id: string; state: 'stopping' };
  if (v.id !== jobId || v.state !== 'stopping')
    throw new DpiError('invalid_response');
  return v;
}
export async function downloadDpiResult(
  csrf: string,
  jobId: string,
): Promise<DpiFile> {
  const { value, text, response } = await request(
    csrf,
    'dpiresult',
    { job_id: id(jobId) },
    262144,
  );
  const v = value as {
    type: string;
    schema_version: number;
    origin: string;
    started_at: string;
    state: DpiState;
    groups: unknown[];
  };
  if (
    v?.type !== 'nfqws2_dpi' ||
    ![1, 2].includes(v.schema_version) ||
    v.origin !== 'router' ||
    !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(v.started_at) ||
    !Array.isArray(v.groups) ||
    !v.groups.length ||
    ['queued', 'running'].includes(v.state)
  )
    throw new DpiError('invalid_response');
  const filename = `NFQWS2_DPI_${v.started_at.slice(0, -1).replace('T', '_').replace(/:/g, '-')}Z.json`;
  if (
    response.headers.get('Content-Disposition') !==
    `attachment; filename="${filename}"`
  )
    throw new DpiError('invalid_response');
  return Object.freeze({
    kind: 'analysis' as const,
    blob: new Blob([text], { type: 'application/json' }),
    filename,
    jobId,
    startedAt: v.started_at,
    complete: v.state === 'completed',
  });
}
export async function deleteDpiResult(
  csrf: string,
  jobId: string,
): Promise<{ deleted: true }> {
  const { value } = await request(csrf, 'dpidelete', { job_id: id(jobId) });
  if ((value as { deleted: unknown })?.deleted !== true)
    throw new DpiError('invalid_response');
  return { deleted: true };
}

export type DpiNativeFile = Omit<DpiFile, 'kind'> & { kind: 'native' };
export type DpiMetadata = {
  config: Record<string, unknown>;
  config_keys: string[];
  fingerprints: string[];
  profiles: Record<string, string[] | null>;
  files: Record<string, string>;
  interfaces: string[];
};
export async function getDpiMetadata(csrf: string): Promise<DpiMetadata> {
  const { value } = await request(csrf, 'dpimetadata', {}, 131072);
  const m = value as DpiMetadata;
  if (
    !m ||
    !Array.isArray(m.fingerprints) ||
    !m.config ||
    !m.files ||
    !Array.isArray(m.interfaces)
  )
    throw new DpiError('invalid_response');
  return m;
}
export async function dpiPreferences(
  csrf: string,
  action: 'read' | 'save' | 'reset',
  options: Record<string, unknown> = {},
): Promise<Record<string, unknown>> {
  const { value } = await request(
    csrf,
    'dpipreferences',
    { action, options: JSON.stringify(options) },
    131072,
  );
  if (!value || typeof value !== 'object' || Array.isArray(value))
    throw new DpiError('invalid_response');
  return value as Record<string, unknown>;
}
export async function downloadDpiNativeResult(
  csrf: string,
  jobId: string,
): Promise<DpiNativeFile> {
  const { value, text, response } = await request(
    csrf,
    'dpinative',
    { job_id: id(jobId) },
    1048576,
  );
  const v = value as {
    type: string;
    schema_version: number;
    origin: string;
    started_at: string;
    state: DpiState;
    groups: unknown[];
  };
  if (
    v?.type !== 'nfqws2_dpi_native' ||
    v.schema_version !== 1 ||
    v.origin !== 'router' ||
    !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(v.started_at) ||
    !Array.isArray(v.groups) ||
    ['queued', 'running'].includes(v.state)
  )
    throw new DpiError('invalid_response');
  const filename = `NFQWS2_DPI_NATIVE_${v.started_at.slice(0, -1).replace('T', '_').replace(/:/g, '-')}Z.json`;
  if (
    response.headers.get('Content-Disposition') !==
    `attachment; filename="${filename}"`
  )
    throw new DpiError('invalid_response');
  return Object.freeze({
    kind: 'native',
    blob: new Blob([text], { type: 'application/json' }),
    filename,
    jobId,
    startedAt: v.started_at,
    complete: v.state === 'completed',
  });
}

/** Preserve the original export of old jobs; mail uses its safe projection. */
export async function downloadDpiOriginal(
  csrf: string,
  jobId: string,
  nativeAvailable: boolean,
): Promise<DpiFile | DpiNativeFile> {
  return nativeAvailable
    ? downloadDpiNativeResult(csrf, jobId)
    : downloadDpiResult(csrf, jobId);
}

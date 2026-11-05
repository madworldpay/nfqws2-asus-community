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
  keepalive = false,
): Promise<{ value: unknown; text: string; response: Response }> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch('/index.php', {
      method: 'POST',
      credentials: 'same-origin',
      keepalive,
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

export type DpiTerminalState =
  | 'running'
  | 'exited'
  | 'stopped'
  | 'expired'
  | 'output_limit'
  | 'failed';
export type DpiTerminalResponse = {
  terminal_id: string;
  state: DpiTerminalState;
  offset: number;
  data: string;
  exit_code: number | null;
};
export type DpiTerminalInfo = {
  available: boolean;
  installed: boolean;
  code: string | null;
};
const TERMINAL_OUTPUT_LIMIT = 2097152;
function terminalSize(cols: number, rows: number) {
  if (
    !Number.isInteger(cols) ||
    cols < 80 ||
    cols > 240 ||
    !Number.isInteger(rows) ||
    rows < 10 ||
    rows > 80
  )
    throw new DpiError('invalid_request');
  return { cols: String(cols), rows: String(rows) };
}
function terminalBytes(data: string): Uint8Array {
  if (
    typeof data !== 'string' ||
    data.length > 43692 ||
    !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(
      data,
    )
  )
    throw new DpiError('invalid_response');
  const raw = atob(data);
  if (raw.length > 32768 || btoa(raw) !== data)
    throw new DpiError('invalid_response');
  return Uint8Array.from(raw, (char) => char.charCodeAt(0));
}
function terminalResponse(
  value: unknown,
  expectedId?: string,
): DpiTerminalResponse {
  const v = value as DpiTerminalResponse;
  if (
    !v ||
    !JOB.test(v.terminal_id) ||
    (expectedId && v.terminal_id !== expectedId) ||
    ![
      'running',
      'exited',
      'stopped',
      'expired',
      'output_limit',
      'failed',
    ].includes(v.state) ||
    !Number.isInteger(v.offset) ||
    v.offset < 0 ||
    v.offset > TERMINAL_OUTPUT_LIMIT ||
    (v.exit_code !== null &&
      (!Number.isInteger(v.exit_code) ||
        v.exit_code < -255 ||
        v.exit_code > 255))
  )
    throw new DpiError('invalid_response');
  terminalBytes(v.data);
  return v;
}
export async function getDpiTerminalInfo(
  csrf: string,
): Promise<DpiTerminalInfo> {
  const { value } = await request(csrf, 'dpiterminalinfo');
  const v = value as DpiTerminalInfo;
  if (
    !v ||
    typeof v.available !== 'boolean' ||
    typeof v.installed !== 'boolean' ||
    (v.code !== null &&
      (typeof v.code !== 'string' || !/^[a-z_]{1,40}$/.test(v.code)))
  )
    throw new DpiError('invalid_response');
  return v;
}
export async function startDpiTerminal(
  csrf: string,
  cols: number,
  rows: number,
  language: 'ru' | 'en',
  requestId: string,
): Promise<DpiTerminalResponse> {
  if (!['ru', 'en'].includes(language)) throw new DpiError('invalid_request');
  return terminalResponse(
    (
      await request(
        csrf,
        'dpiterminalstart',
        { ...terminalSize(cols, rows), language, request_id: id(requestId) },
        49152,
      )
    ).value,
  );
}
export async function removeDpiDetector(csrf: string, deleteReports: boolean) {
  if (typeof deleteReports !== 'boolean') throw new DpiError('invalid_request');
  const { value } = await request(
    csrf,
    'dpiterminalremove',
    {
      consent: 'remove',
      delete_reports: deleteReports ? '1' : '0',
    },
    1024,
  );
  const result = value as { removed: boolean; reports_removed: boolean };
  if (result?.removed !== true || result.reports_removed !== deleteReports)
    throw new DpiError('invalid_response');
  return result;
}
export async function pollDpiTerminal(
  csrf: string,
  terminalId: string,
  offset: number,
): Promise<DpiTerminalResponse> {
  if (!Number.isInteger(offset) || offset < 0 || offset > TERMINAL_OUTPUT_LIMIT)
    throw new DpiError('invalid_request');
  return terminalResponse(
    (
      await request(
        csrf,
        'dpiterminalpoll',
        { terminal_id: id(terminalId), offset: String(offset) },
        49152,
      )
    ).value,
    terminalId,
  );
}
export async function inputDpiTerminal(
  csrf: string,
  terminalId: string,
  data: string,
): Promise<DpiTerminalResponse> {
  const bytes = new TextEncoder().encode(data);
  if (!bytes.length || bytes.length > 1024)
    throw new DpiError('invalid_request');
  return terminalResponse(
    (
      await request(
        csrf,
        'dpiterminalinput',
        {
          terminal_id: id(terminalId),
          data: btoa(String.fromCharCode(...bytes)),
        },
        49152,
      )
    ).value,
    terminalId,
  );
}
export async function resizeDpiTerminal(
  csrf: string,
  terminalId: string,
  cols: number,
  rows: number,
): Promise<DpiTerminalResponse> {
  return terminalResponse(
    (
      await request(
        csrf,
        'dpiterminalresize',
        { terminal_id: id(terminalId), ...terminalSize(cols, rows) },
        49152,
      )
    ).value,
    terminalId,
  );
}
export async function stopDpiTerminal(
  csrf: string,
  terminalId: string,
): Promise<DpiTerminalResponse> {
  return terminalResponse(
    (
      await request(
        csrf,
        'dpiterminalstop',
        { terminal_id: id(terminalId) },
        49152,
        true,
      )
    ).value,
    terminalId,
  );
}

/** Owns one native process. All output/input requests share a single loop. */
export class DpiTerminalSession {
  private terminalId: string | null = null;
  // One nonce belongs to this dialog attempt, including retries after a lost
  // response. Another dialog must never attach to this process before cleanup.
  private requestId = Array.from(
    crypto.getRandomValues(new Uint8Array(16)),
    (byte) => byte.toString(16).padStart(2, '0'),
  ).join('');
  private offset = 0;
  private closed = false;
  private inputQueue: string[] = [];
  private size: { cols: number; rows: number } | null = null;
  private running: Promise<void> | null = null;
  private stopping: Promise<void> | null = null;
  private wake: (() => void) | null = null;
  private csrf: string;
  private language: 'ru' | 'en';
  private callbacks: {
    output: (data: Uint8Array) => void;
    state: (state: DpiTerminalState) => void;
    error: (error: DpiError) => void;
  };
  constructor(
    csrf: string,
    language: 'ru' | 'en',
    callbacks: DpiTerminalSession['callbacks'],
  ) {
    this.csrf = csrf;
    this.language = language;
    this.callbacks = callbacks;
  }
  start(cols: number, rows: number): Promise<void> {
    if (!this.running && !this.closed) this.running = this.run(cols, rows);
    return this.running ?? Promise.resolve();
  }
  input(data: string) {
    if (this.closed || !this.terminalId) return;
    const bytes = new TextEncoder().encode(data).length;
    const queued = this.inputQueue.reduce(
      (sum, item) => sum + new TextEncoder().encode(item).length,
      0,
    );
    if (!bytes || bytes > 1024 || queued + bytes > 8192) {
      this.callbacks.error(new DpiError('input_limit'));
      return;
    }
    this.inputQueue.push(data);
    this.wake?.();
  }
  resize(cols: number, rows: number) {
    terminalSize(cols, rows);
    if (this.closed) return;
    this.size = { cols, rows };
    this.wake?.();
  }
  async close(): Promise<void> {
    this.closed = true;
    this.inputQueue = [];
    this.wake?.();
    // A keepalive stop must leave immediately on pagehide, even if a poll is
    // awaiting a response. The output loop itself still never overlaps polls.
    const stopping = this.stopOwned();
    await this.running;
    await stopping;
    await this.stopOwned();
  }
  private stopOwned(): Promise<void> {
    if (!this.stopping && this.terminalId) {
      this.stopping = stopDpiTerminal(this.csrf, this.terminalId).then(
        () => {},
        () => {},
      );
    }
    return this.stopping ?? Promise.resolve();
  }
  private consume(value: DpiTerminalResponse) {
    const bytes = terminalBytes(value.data);
    if (value.offset !== this.offset + bytes.length)
      throw new DpiError('invalid_response');
    this.offset = value.offset;
    if (bytes.length) this.callbacks.output(bytes);
    this.callbacks.state(value.state);
    return bytes.length;
  }
  private wait() {
    return new Promise<void>((resolve) => {
      const finish = () => {
        clearTimeout(timer);
        this.wake = null;
        resolve();
      };
      const timer = setTimeout(finish, 150);
      this.wake = finish;
    });
  }
  private async run(cols: number, rows: number) {
    try {
      let started: DpiTerminalResponse;
      try {
        started = await startDpiTerminal(
          this.csrf,
          cols,
          rows,
          this.language,
          this.requestId,
        );
      } catch (error) {
        if (
          !(error instanceof DpiError) ||
          !['timeout', 'request_failed'].includes(error.code)
        )
          throw error;
        // The server returns the existing session for the same browser owner.
        // Recover a lost reply even after close so its process can be stopped.
        started = await startDpiTerminal(
          this.csrf,
          cols,
          rows,
          this.language,
          this.requestId,
        );
      }
      this.terminalId = started.terminal_id;
      if (this.closed) return;
      this.consume(started);
      if (
        started.state !== 'running' &&
        terminalBytes(started.data).length < 32768
      )
        return;
      while (!this.closed) {
        if (this.size) {
          const size = this.size;
          this.size = null;
          await resizeDpiTerminal(
            this.csrf,
            this.terminalId,
            size.cols,
            size.rows,
          );
        } else if (this.inputQueue.length) {
          await inputDpiTerminal(
            this.csrf,
            this.terminalId,
            this.inputQueue.shift()!,
          );
        } else {
          const value = await pollDpiTerminal(
            this.csrf,
            this.terminalId,
            this.offset,
          );
          if (this.closed) break;
          const length = this.consume(value);
          if (value.state !== 'running' && length < 32768) break;
          if (!this.inputQueue.length && !this.size) await this.wait();
        }
      }
    } catch (error) {
      if (!this.closed) {
        this.callbacks.error(
          error instanceof DpiError ? error : new DpiError('request_failed'),
        );
        this.callbacks.state('failed');
      }
      this.closed = true;
    } finally {
      if (this.closed) await this.stopOwned();
    }
  }
}

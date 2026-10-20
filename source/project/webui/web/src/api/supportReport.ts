export type SupportReportFile = {
  blob: Blob;
  filename: string;
  complete: boolean;
  proof?: string;
};
export type ReportErrorCode =
  | 'unauthorized'
  | 'busy'
  | 'forbidden'
  | 'unavailable'
  | 'invalid'
  | 'timeout'
  | 'save_failed';
export class SupportReportError extends Error {
  code: ReportErrorCode;
  constructor(code: ReportErrorCode) {
    super(code);
    this.name = 'SupportReportError';
    this.code = code;
  }
}

const MAX_BYTES = 1048576;
const NAME =
  /^NFQWS2_[A-Za-z0-9_-]{1,80}_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}Z\.json$/;

export async function downloadSupportReport(
  csrfToken: string,
  onUnauthorized: () => void = () => {},
): Promise<SupportReportFile> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);
  try {
    const response = await fetch('/index.php', {
      method: 'POST',
      credentials: 'same-origin',
      body: new URLSearchParams({
        cmd: 'supportreport',
        csrf_token: csrfToken,
      }),
      signal: controller.signal,
    });
    if (!response.ok) {
      if (response.status === 401) {
        onUnauthorized();
        throw new SupportReportError('unauthorized');
      }
      throw new SupportReportError(
        response.status === 409
          ? 'busy'
          : response.status === 403
            ? 'forbidden'
            : 'unavailable',
      );
    }
    if (
      !/^application\/json(?:;|$)/i.test(
        response.headers.get('Content-Type') ?? '',
      )
    )
      throw new SupportReportError('invalid');
    const match = /^attachment;\s*filename="([^"]+)"$/i.exec(
      response.headers.get('Content-Disposition') ?? '',
    );
    if (
      !match ||
      !NAME.test(match[1]) ||
      Number(response.headers.get('Content-Length') ?? 0) > MAX_BYTES
    )
      throw new SupportReportError('invalid');
    const reader = response.body?.getReader();
    if (!reader) throw new SupportReportError('invalid');
    const chunks: Uint8Array<ArrayBuffer>[] = [];
    let bytes = 0;
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        bytes += value.byteLength;
        if (bytes > MAX_BYTES) throw new SupportReportError('invalid');
        chunks.push(new Uint8Array(value));
      }
    } finally {
      await reader.cancel().catch(() => {});
      reader.releaseLock();
    }
    const blob = new Blob(chunks, { type: 'application/json' });
    const report = JSON.parse(await blob.text());
    if (
      report?.schema_version !== 1 ||
      typeof report.complete !== 'boolean' ||
      !report.sections ||
      typeof report.sections !== 'object' ||
      !Array.isArray(report.failures) ||
      typeof report.model !== 'string' ||
      !/^[A-Za-z0-9_-]{1,80}$/.test(report.model) ||
      typeof report.captured_at !== 'string' ||
      !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(report.captured_at)
    )
      throw new SupportReportError('invalid');
    const expectedName = `NFQWS2_${report.model}_${report.captured_at.slice(0, -1).replace('T', '_').replaceAll(':', '-')}Z.json`;
    if (match[1] !== expectedName) throw new SupportReportError('invalid');
    const proof = response.headers.get('X-NFQWS2-Report-Proof') ?? '';
    return {
      blob,
      filename: match[1],
      complete: report.complete,
      ...(/^v1\.[1-9][0-9]{0,9}\.[a-f0-9]{32}\.[a-f0-9]{64}$/.test(proof)
        ? { proof }
        : {}),
    };
  } catch (error) {
    if (controller.signal.aborted) throw new SupportReportError('timeout');
    if (error instanceof SupportReportError) throw error;
    throw new SupportReportError('invalid');
  } finally {
    clearTimeout(timeout);
  }
}

export type SupportMailAvailability = {
  dpi_attachments?: boolean;
  configured: boolean;
  code: 'ready' | 'not_configured' | 'https_unavailable' | 'invalid_config';
};
export type SupportMailResult = {
  state:
    | 'accepted'
    | 'failed_safe'
    | 'unknown'
    | 'busy'
    | 'limited'
    | 'invalid';
  submissionId: string;
  code: string;
};
export type SupportReportPreview = {
  text: string;
  model: string;
  capturedAt: string;
  bytes: number;
  sections: {
    name:
      | 'platform'
      | 'package'
      | 'engine'
      | 'ark'
      | 'process'
      | 'resources'
      | 'errors'
      | 'settings'
      | 'network'
      | 'rules'
      | 'nfqueue'
      | 'dns';
    state: 'available' | 'partial' | 'unavailable';
  }[];
};

export async function inspectSupportReport(
  file: SupportReportFile,
): Promise<SupportReportPreview> {
  if (!NAME.test(file.filename) || file.blob.size > MAX_BYTES)
    throw new SupportReportError('invalid');
  const text = new TextDecoder('utf-8', { fatal: true }).decode(
    await file.blob.arrayBuffer(),
  );
  const report = JSON.parse(text);
  const names = [
    'platform',
    'package',
    'engine',
    'ark',
    'process',
    'resources',
    'errors',
    'settings',
    'network',
    'rules',
    'nfqueue',
    'dns',
  ];
  if (
    report?.schema_version !== 1 ||
    typeof report.model !== 'string' ||
    !/^[A-Za-z0-9_-]{1,80}$/.test(report.model) ||
    typeof report.captured_at !== 'string' ||
    !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(report.captured_at) ||
    !report.sections ||
    typeof report.sections !== 'object' ||
    Array.isArray(report.sections)
  )
    throw new SupportReportError('invalid');
  const expected = `NFQWS2_${report.model}_${report.captured_at.slice(0, -1).replace('T', '_').replaceAll(':', '-')}Z.json`;
  if (file.filename !== expected) throw new SupportReportError('invalid');
  const sections = Object.entries(report.sections).map(([name, section]) => {
    const state = (section as { state?: unknown })?.state;
    if (
      !names.includes(name) ||
      !['available', 'partial', 'unavailable'].includes(String(state))
    )
      throw new SupportReportError('invalid');
    return {
      name: name as SupportReportPreview['sections'][number]['name'],
      state: state as SupportReportPreview['sections'][number]['state'],
    };
  });
  return {
    text,
    model: report.model,
    capturedAt: report.captured_at,
    bytes: file.blob.size,
    sections,
  };
}

async function smallJson(response: Response): Promise<Record<string, unknown>> {
  const reader = response.body?.getReader();
  if (!reader) throw new SupportReportError('invalid');
  const chunks: Uint8Array<ArrayBuffer>[] = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 4096) throw new SupportReportError('invalid');
      chunks.push(new Uint8Array(value));
    }
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
  return JSON.parse(await new Blob(chunks).text());
}

export async function getSupportMailAvailability(
  csrfToken: string,
  onUnauthorized: () => void = () => {},
): Promise<SupportMailAvailability> {
  const response = await fetch('/index.php', {
    method: 'POST',
    credentials: 'same-origin',
    body: new URLSearchParams({
      cmd: 'supportmailstatus',
      csrf_token: csrfToken,
    }),
    signal: AbortSignal.timeout(5000),
  });
  if (response.status === 401) {
    onUnauthorized();
    throw new SupportReportError('unauthorized');
  }
  if (!response.ok)
    throw new SupportReportError(
      response.status === 403 ? 'forbidden' : 'unavailable',
    );
  const value = await smallJson(response);
  const codes = [
    'ready',
    'not_configured',
    'https_unavailable',
    'invalid_config',
  ];
  if (
    typeof value.configured !== 'boolean' ||
    typeof value.code !== 'string' ||
    !codes.includes(value.code) ||
    value.configured !== (value.code === 'ready')
  )
    throw new SupportReportError('invalid');
  return {
    configured: value.configured,
    code: value.code as SupportMailAvailability['code'],
    dpi_attachments: value.dpi_attachments === true,
  };
}

export function newSupportSubmissionId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join(
    '',
  );
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

const sendingReports = new WeakMap<Blob, Promise<SupportMailResult>>();
const terminalReports = new WeakMap<Blob, SupportMailResult>();
export function sendSupportReport(
  file: SupportReportFile,
  csrfToken: string,
  submissionId: string,
  onUnauthorized: () => void = () => {},
): Promise<SupportMailResult> {
  const terminal = terminalReports.get(file.blob);
  if (terminal) return Promise.resolve(terminal);
  const pending = sendingReports.get(file.blob);
  if (pending) return pending;
  const perform = async (): Promise<SupportMailResult> => {
    if (
      !file.proof ||
      !/^v1\.[1-9][0-9]{0,9}\.[a-f0-9]{32}\.[a-f0-9]{64}$/.test(file.proof) ||
      !/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/.test(
        submissionId,
      )
    )
      throw new SupportReportError('invalid');
    const preview = await inspectSupportReport(file);
    const unknown: SupportMailResult = {
      state: 'unknown',
      submissionId,
      code: 'delivery_unknown',
    };
    try {
      const response = await fetch('/index.php', {
        method: 'POST',
        credentials: 'same-origin',
        signal: AbortSignal.timeout(20000),
        body: new URLSearchParams({
          cmd: 'supportsend',
          csrf_token: csrfToken,
          consent: 'send',
          filename: file.filename,
          report: preview.text,
          report_proof: file.proof,
          submission_id: submissionId,
        }),
      });
      if (response.status === 401) {
        onUnauthorized();
        throw new SupportReportError('unauthorized');
      }
      if (response.status === 403 || response.status === 400)
        throw new SupportReportError(
          response.status === 403 ? 'forbidden' : 'invalid',
        );
      const value = await smallJson(response);
      const statuses: Record<string, number> = {
        accepted: 200,
        failed_safe: 503,
        unknown: 503,
        busy: 409,
        limited: 429,
        invalid: 422,
      };
      const codes = [
        'smtp_accepted',
        'transport_failed',
        'delivery_unknown',
        'busy',
        'rate_limited',
        'invalid_request',
        'id_conflict',
        'invalid_report',
        'not_configured',
        'https_unavailable',
        'invalid_config',
      ];
      if (
        typeof value.state !== 'string' ||
        typeof value.code !== 'string' ||
        !codes.includes(value.code) ||
        value.submission_id !== submissionId ||
        (statuses[value.state] !== response.status &&
          !(
            value.state === 'invalid' &&
            value.code === 'id_conflict' &&
            response.status === 409
          ))
      )
        return unknown;
      return {
        state: value.state as SupportMailResult['state'],
        submissionId,
        code: value.code,
      };
    } catch (error) {
      if (
        error instanceof SupportReportError &&
        ['unauthorized', 'forbidden'].includes(error.code)
      )
        throw error;
      return unknown;
    }
  };
  const promise = perform().then((result) => {
    if (result.state === 'accepted' || result.state === 'unknown')
      terminalReports.set(file.blob, result);
    return result;
  });
  sendingReports.set(file.blob, promise);
  void promise.then(
    () => sendingReports.delete(file.blob),
    () => sendingReports.delete(file.blob),
  );
  return promise;
}

type WritableReportFile = {
  write: (blob: Blob) => Promise<void>;
  close: () => Promise<void>;
  abort: () => Promise<void>;
};
type PickerWindow = Window & {
  showSaveFilePicker?: (options: {
    suggestedName: string;
    types: { description: string; accept: Record<string, string[]> }[];
  }) => Promise<{ createWritable: () => Promise<WritableReportFile> }>;
};
export const canChooseReportLocation = () =>
  window.isSecureContext &&
  typeof (window as PickerWindow).showSaveFilePicker === 'function';

// Called directly by the Save button, while browser user activation is live.
export async function saveSupportReport(
  file: SupportReportFile,
): Promise<'native' | 'browser'> {
  if (!NAME.test(file.filename) || file.blob.size > MAX_BYTES)
    throw new SupportReportError('invalid');
  if (canChooseReportLocation()) {
    const handle = await (window as PickerWindow).showSaveFilePicker!({
      suggestedName: file.filename,
      types: [
        {
          description: 'NFQWS2 diagnostics (JSON)',
          accept: { 'application/json': ['.json'] },
        },
      ],
    });
    const writable = await handle.createWritable();
    try {
      await writable.write(file.blob);
      await writable.close();
    } catch (error) {
      await writable.abort().catch(() => {});
      throw error;
    }
    return 'native';
  }
  const url = URL.createObjectURL(file.blob);
  const anchor = document.createElement('a');
  try {
    anchor.href = url;
    anchor.download = file.filename;
    document.body.append(anchor);
    anchor.click();
  } finally {
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return 'browser';
}

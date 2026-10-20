import { sha256 } from '@/api/supportDigest';
import {
  inspectSupportReport,
  SupportReportError,
  type SupportMailResult,
  type SupportReportFile,
} from '@/api/supportReport';

export type BundleWireFile = Readonly<{
  type: 'report' | 'dpi';
  filename: string;
  byte_length: number;
  sha256: string;
  data_base64: string;
}>;
export type SupportBundleFile = Readonly<{
  files: readonly Readonly<{
    blob: Blob;
    filename: string;
    complete: boolean;
  }>[];
  wire: readonly BundleWireFile[];
  proof: string;
}>;
async function read(response: Response, max: number): Promise<unknown> {
  if (
    !/^application\/json(?:;|$)/i.test(
      response.headers.get('Content-Type') ?? '',
    )
  )
    throw new SupportReportError('invalid');
  const reader = response.body?.getReader();
  if (!reader) throw new SupportReportError('invalid');
  let size = 0;
  const chunks: Uint8Array<ArrayBuffer>[] = [];
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > max) throw new SupportReportError('invalid');
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
export async function prepareSupportBundle(
  report: SupportReportFile,
  jobId: string,
  csrf: string,
): Promise<SupportBundleFile> {
  if (!report.proof || !/^[a-f0-9]{32}$/.test(jobId))
    throw new SupportReportError('invalid');
  const preview = await inspectSupportReport(report);
  const response = await fetch('/index.php', {
    method: 'POST',
    credentials: 'same-origin',
    signal: AbortSignal.timeout(20000),
    body: new URLSearchParams({
      cmd: 'supportbundleprepare',
      csrf_token: csrf,
      report: preview.text,
      filename: report.filename,
      report_proof: report.proof,
      job_id: jobId,
    }),
  });
  if (!response.ok)
    throw new SupportReportError(
      response.status === 401
        ? 'unauthorized'
        : response.status === 403
          ? 'forbidden'
          : 'invalid',
    );
  const value = (await read(response, 2097152)) as {
    files: BundleWireFile[];
    proof: string;
  };
  if (
    !Array.isArray(value.files) ||
    value.files.length !== 2 ||
    !/^v2\.[1-9][0-9]{0,9}\.[a-f0-9]{32}\.[a-f0-9]{64}$/.test(value.proof)
  )
    throw new SupportReportError('invalid');
  const files = [];
  const wire = [];
  for (let i = 0; i < 2; i++) {
    const f = value.files[i],
      max = i ? 262144 : 1048576;
    if (
      f.type !== (i ? 'dpi' : 'report') ||
      typeof f.data_base64 !== 'string' ||
      f.data_base64.length > 4 * Math.ceil(max / 3) ||
      !Number.isInteger(f.byte_length) ||
      f.byte_length < 1 ||
      f.byte_length > max ||
      !/^NFQWS2_[A-Za-z0-9_-]{1,64}_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}Z\.json$/.test(
        f.filename,
      )
    )
      throw new SupportReportError('invalid');
    const decoded = atob(f.data_base64);
    if (btoa(decoded) !== f.data_base64 || decoded.length !== f.byte_length)
      throw new SupportReportError('invalid');
    const bytes = Uint8Array.from(decoded, (c) => c.charCodeAt(0));
    if (sha256(bytes) !== f.sha256) throw new SupportReportError('invalid');
    const text = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
    const data = JSON.parse(text);
    if (i === 0 && (text !== preview.text || f.filename !== report.filename))
      throw new SupportReportError('invalid');
    if (
      i === 1 &&
      (data.type !== 'nfqws2_dpi' ||
        ![1, 2].includes(data.schema_version) ||
        data.origin !== 'router' ||
        !Array.isArray(data.groups) ||
        data.groups.length === 0 ||
        f.filename !==
          `NFQWS2_DPI_${String(data.started_at).slice(0, -1).replace('T', '_').replace(/:/g, '-')}Z.json`)
    )
      throw new SupportReportError('invalid');
    files.push(
      Object.freeze({
        blob: new Blob([bytes], { type: 'application/json' }),
        filename: f.filename,
        complete: i === 0 ? report.complete : data.state === 'completed',
      }),
    );
    wire.push(Object.freeze({ ...f }));
  }
  return Object.freeze({
    files: Object.freeze(files),
    wire: Object.freeze(wire),
    proof: value.proof,
  });
}
const pending = new WeakMap<SupportBundleFile, Promise<SupportMailResult>>();
const terminal = new WeakMap<SupportBundleFile, SupportMailResult>();
export function sendSupportBundle(
  bundle: SupportBundleFile,
  csrf: string,
  submissionId: string,
): Promise<SupportMailResult> {
  const old = terminal.get(bundle);
  if (old) return Promise.resolve(old);
  const active = pending.get(bundle);
  if (active) return active;
  const perform = async (): Promise<SupportMailResult> => {
    if (
      !/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/.test(
        submissionId,
      )
    )
      throw new SupportReportError('invalid');
    const envelope = JSON.stringify({
      version: 2,
      submission_id: submissionId,
      files: bundle.wire,
    });
    if (new Blob([envelope]).size > 2097152)
      throw new SupportReportError('invalid');
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
          cmd: 'supportbundlesend',
          csrf_token: csrf,
          consent: 'send',
          envelope,
          proof: bundle.proof,
          submission_id: submissionId,
        }),
      });
      if ([400, 401, 403].includes(response.status))
        throw new SupportReportError(
          response.status === 401
            ? 'unauthorized'
            : response.status === 403
              ? 'forbidden'
              : 'invalid',
        );
      const v = (await read(response, 4096)) as {
        state: SupportMailResult['state'];
        code: string;
        submission_id: string;
      };
      const statuses: Record<string, number> = {
        accepted: 200,
        failed_safe: 503,
        unknown: 503,
        busy: 409,
        limited: 429,
        invalid: 422,
      };
      if (
        v.submission_id !== submissionId ||
        ![
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
        ].includes(v.code) ||
        (statuses[v.state] !== response.status &&
          !(
            v.state === 'invalid' &&
            v.code === 'id_conflict' &&
            response.status === 409
          ))
      )
        return unknown;
      return { state: v.state, code: v.code, submissionId };
    } catch (e) {
      if (e instanceof SupportReportError) throw e;
      return unknown;
    }
  };
  const promise = perform().then((r) => {
    if (r.state === 'accepted' || r.state === 'unknown')
      terminal.set(bundle, r);
    return r;
  });
  pending.set(bundle, promise);
  void promise.then(
    () => pending.delete(bundle),
    () => pending.delete(bundle),
  );
  return promise;
}

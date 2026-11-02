import { DpiError } from '@/api/dpiClient';

export type IpHealthEntry = {
  id: string;
  ip: string;
  port: 443;
  host: string;
  until: number;
  first_seen: number;
  incident: 1 | 2;
  last_check: number | null;
  check_state: 'due' | 'checking' | 'silent' | 'replied' | 'unknown';
};
export type IpHealthStatus = {
  schema_version: 1;
  revision: string;
  enabled: boolean;
  runtime: {
    state: 'active' | 'starting' | 'stopped' | 'unavailable';
    code: string | null;
    updated_at: number | null;
    dns: 'router_udp' | 'unavailable';
  };
  entries: IpHealthEntry[];
};
const REVISION = /^[a-f0-9]{64}$/;
const ID = /^[a-f0-9]{32}$/;
const timestamp = (value: unknown) =>
  typeof value === 'number' &&
  Number.isSafeInteger(value) &&
  value >= 0 &&
  value <= 8640000000000;
const optionalTime = (value: unknown) => value === null || timestamp(value);
function status(value: unknown): IpHealthStatus {
  const v = value as IpHealthStatus;
  if (
    !v ||
    v.schema_version !== 1 ||
    typeof v.revision !== 'string' ||
    !REVISION.test(v.revision) ||
    typeof v.enabled !== 'boolean' ||
    !v.runtime ||
    !['active', 'starting', 'stopped', 'unavailable'].includes(
      v.runtime.state,
    ) ||
    !(
      v.runtime.code === null ||
      (typeof v.runtime.code === 'string' && v.runtime.code.length <= 80)
    ) ||
    !optionalTime(v.runtime.updated_at) ||
    !['router_udp', 'unavailable'].includes(v.runtime.dns) ||
    !Array.isArray(v.entries) ||
    v.entries.length > 512 ||
    v.entries.some(
      (e) =>
        !e ||
        typeof e.id !== 'string' ||
        !ID.test(e.id) ||
        typeof e.ip !== 'string' ||
        !/^[0-9a-fA-F:.]{2,45}$/.test(e.ip) ||
        e.port !== 443 ||
        typeof e.host !== 'string' ||
        e.host.length > 253 ||
        Array.from(e.host).some(
          (character) =>
            character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127,
        ) ||
        !timestamp(e.until) ||
        !timestamp(e.first_seen) ||
        ![1, 2].includes(e.incident) ||
        !optionalTime(e.last_check) ||
        !['due', 'checking', 'silent', 'replied', 'unknown'].includes(
          e.check_state,
        ),
    ) ||
    new Set(v.entries.map((e) => e.id)).size !== v.entries.length
  )
    throw new DpiError('invalid_response');
  return v;
}
// IP Health distinguishes an expired session even when PHP exits before JSON.
async function request(
  csrf: string,
  cmd: string,
  params: Record<string, string> = {},
) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch('/index.php', {
      method: 'POST',
      credentials: 'same-origin',
      redirect: 'error',
      cache: 'no-store',
      body: new URLSearchParams({ cmd, csrf_token: csrf, ...params }),
      signal: controller.signal,
    });
    if (response.status === 401) throw new DpiError('unauthorized');
    if (response.status === 403) throw new DpiError('forbidden');
    if (
      !/^application\/json(?:;|$)/i.test(
        response.headers.get('Content-Type') ?? '',
      )
    )
      throw new DpiError('invalid_response');
    const reader = response.body?.getReader();
    if (!reader) throw new DpiError('invalid_response');
    const chunks: Uint8Array<ArrayBuffer>[] = [];
    let size = 0;
    try {
      while (true) {
        const result = await reader.read();
        if (result.done) break;
        size += result.value.byteLength;
        if (size > 524288) throw new DpiError('invalid_response');
        chunks.push(new Uint8Array(result.value));
      }
    } finally {
      await reader.cancel().catch(() => {});
      reader.releaseLock();
    }
    let value: unknown;
    try {
      value = JSON.parse(
        new TextDecoder('utf-8', { fatal: true }).decode(
          await new Blob(chunks).arrayBuffer(),
        ),
      );
    } catch {
      throw new DpiError('invalid_response');
    }
    if (!response.ok) {
      const code =
        typeof value === 'object' && value !== null && 'error' in value
          ? value.error
          : null;
      throw new DpiError(
        typeof code === 'string' && /^[a-z_]{1,40}$/.test(code)
          ? code
          : 'request_failed',
      );
    }
    return value;
  } catch (error) {
    if (error instanceof DpiError) throw error;
    throw new DpiError(
      controller.signal.aborted ? 'timeout' : 'request_failed',
    );
  } finally {
    clearTimeout(timer);
  }
}
export async function getIpHealthStatus(csrf: string): Promise<IpHealthStatus> {
  return status(await request(csrf, 'iphealthstatus'));
}
async function mutate(
  csrf: string,
  cmd: string,
  revision: string,
  params: Record<string, string> = {},
) {
  if (!REVISION.test(revision)) throw new DpiError('invalid_request');
  return status(await request(csrf, cmd, { ...params, revision }));
}
export function configureIpHealth(
  csrf: string,
  enabled: boolean,
  revision: string,
) {
  return mutate(csrf, 'iphealthconfigure', revision, {
    enabled: enabled ? '1' : '0',
  });
}
export function removeIpHealth(csrf: string, id: string, revision: string) {
  if (!ID.test(id)) throw new DpiError('invalid_request');
  return mutate(csrf, 'iphealthremove', revision, { id });
}
export function clearIpHealth(csrf: string, revision: string) {
  return mutate(csrf, 'iphealthclear', revision);
}
export function recheckIpHealth(csrf: string, id: string, revision: string) {
  if (id !== 'all' && !ID.test(id)) throw new DpiError('invalid_request');
  return mutate(csrf, 'iphealthrecheck', revision, { id });
}

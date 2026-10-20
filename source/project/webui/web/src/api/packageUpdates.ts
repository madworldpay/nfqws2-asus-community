export type PackageCandidate = {
  revision: string;
  package_version: string;
  core_version: string;
  web_version: string;
  build: number;
  notes: string;
  package: {
    family: 'aarch64-3.10' | 'armv7';
    filename: string;
    size: number;
    sha256: string;
  };
};
export type PackageCheck = {
  state: 'unconfigured' | 'checking' | 'current' | 'available' | 'failed';
  code: string | null;
  candidate: PackageCandidate | null;
  installed_version: string | null;
};
export type PackageOperation = {
  id: string;
  revision: string;
  state:
    | 'preparing'
    | 'prepared'
    | 'applying'
    | 'succeeded'
    | 'failed'
    | 'interrupted';
  phase?: string;
  package_version: string;
  installed_version?: string;
  core_state?: 'running' | 'waiting_for_wan' | 'stopped';
  settings_verified?: boolean;
  code: string | null;
  service_intent: 'running' | 'waiting_for_wan' | 'stopped' | null;
};
export type PackageOverview = {
  check: PackageCheck;
  operation: PackageOperation | null;
};
export class PackageUpdateError extends Error {
  code: string;
  constructor(code: string) {
    super(code);
    this.code = code;
  }
}
const VERSION = /^[0-9]+\.[0-9]+\.[0-9]+-asus[1-9][0-9]*\+b[1-9][0-9]*$/;
const HEX32 = /^[a-f0-9]{32}$/;
const HEX64 = /^[a-f0-9]{64}$/;
const record = (v: unknown): v is Record<string, unknown> =>
  v !== null && typeof v === 'object' && !Array.isArray(v);
const keys = (v: Record<string, unknown>, expected: string[]) =>
  Object.keys(v).sort().join(',') === [...expected].sort().join(',');
const code = (v: unknown) =>
  v === null || (typeof v === 'string' && /^[a-z_]{1,64}$/.test(v));
const coreState = (v: unknown) =>
  v === 'running' || v === 'waiting_for_wan' || v === 'stopped';
const invalid = (): never => {
  throw new PackageUpdateError('invalid_response');
};

function candidate(value: unknown): PackageCandidate {
  if (
    !record(value) ||
    !keys(value, [
      'revision',
      'package_version',
      'core_version',
      'web_version',
      'build',
      'notes',
      'package',
    ])
  )
    return invalid();
  const p = value.package;
  if (
    typeof value.revision !== 'string' ||
    !HEX64.test(value.revision) ||
    typeof value.package_version !== 'string' ||
    !VERSION.test(value.package_version) ||
    typeof value.core_version !== 'string' ||
    !/^[0-9]+\.[0-9]+\.[0-9]+-asus[1-9][0-9]*$/.test(value.core_version) ||
    typeof value.web_version !== 'string' ||
    !/^[0-9]+\.[0-9]+\.[0-9]+$/.test(value.web_version) ||
    !Number.isSafeInteger(value.build) ||
    (value.build as number) < 1 ||
    typeof value.notes !== 'string' ||
    value.notes.length > 2000 ||
    !record(p) ||
    !keys(p, ['family', 'filename', 'size', 'sha256'])
  )
    return invalid();
  if (
    (p.family !== 'aarch64-3.10' && p.family !== 'armv7') ||
    p.filename !== `nfqws2-asus_${value.package_version}_${p.family}.ipk` ||
    !Number.isSafeInteger(p.size) ||
    (p.size as number) < 1 ||
    (p.size as number) > 33554432 ||
    typeof p.sha256 !== 'string' ||
    !HEX64.test(p.sha256)
  )
    return invalid();
  return value as PackageCandidate;
}
function check(value: unknown): PackageCheck {
  if (
    !record(value) ||
    !keys(value, ['state', 'code', 'candidate', 'installed_version']) ||
    !['unconfigured', 'checking', 'current', 'available', 'failed'].includes(
      String(value.state),
    ) ||
    !code(value.code) ||
    (value.installed_version !== null &&
      (typeof value.installed_version !== 'string' ||
        !VERSION.test(value.installed_version)))
  )
    return invalid();
  if (value.state === 'available') candidate(value.candidate);
  else if (value.candidate !== null) return invalid();
  return value as PackageCheck;
}
function operation(value: unknown): PackageOperation {
  const required = [
    'id',
    'revision',
    'state',
    'package_version',
    'code',
    'service_intent',
  ];
  const optional = [
    'phase',
    'installed_version',
    'core_state',
    'settings_verified',
  ];
  if (
    !record(value) ||
    required.some((key) => !(key in value)) ||
    Object.keys(value).some(
      (key) => !required.includes(key) && !optional.includes(key),
    ) ||
    typeof value.id !== 'string' ||
    !HEX32.test(value.id) ||
    typeof value.revision !== 'string' ||
    !HEX64.test(value.revision) ||
    ![
      'preparing',
      'prepared',
      'applying',
      'succeeded',
      'failed',
      'interrupted',
    ].includes(String(value.state)) ||
    typeof value.package_version !== 'string' ||
    !VERSION.test(value.package_version) ||
    !code(value.code) ||
    (value.service_intent !== null && !coreState(value.service_intent))
  )
    return invalid();
  if (
    value.phase !== undefined &&
    ![
      'queued',
      'validating',
      'stopping',
      'installing',
      'verifying',
      'finished',
    ].includes(String(value.phase))
  )
    return invalid();
  if (
    value.installed_version !== undefined &&
    (typeof value.installed_version !== 'string' ||
      !VERSION.test(value.installed_version))
  )
    return invalid();
  if (value.core_state !== undefined && !coreState(value.core_state))
    return invalid();
  if (
    value.settings_verified !== undefined &&
    typeof value.settings_verified !== 'boolean'
  )
    return invalid();
  return value as PackageOperation;
}
async function request(
  csrf: string,
  cmd: string,
  params: Record<string, string>,
): Promise<unknown> {
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
    if (
      !/^application\/json(?:;|$)/i.test(
        response.headers.get('Content-Type') ?? '',
      )
    )
      return invalid();
    const reader = response.body?.getReader();
    if (!reader) return invalid();
    let total = 0;
    const chunks: Uint8Array[] = [];
    try {
      while (true) {
        const result = await reader.read();
        if (result.done) break;
        total += result.value.length;
        if (total > 32768) return invalid();
        chunks.push(result.value);
      }
    } finally {
      await reader.cancel().catch(() => {});
      reader.releaseLock();
    }
    const bytes = new Uint8Array(total);
    let at = 0;
    for (const chunk of chunks) {
      bytes.set(chunk, at);
      at += chunk.length;
    }
    let value: unknown;
    try {
      value = JSON.parse(new TextDecoder().decode(bytes));
    } catch {
      return invalid();
    }
    if (!response.ok)
      throw new PackageUpdateError(
        record(value) && typeof value.error === 'string' && code(value.error)
          ? value.error
          : 'update_failed',
      );
    return value;
  } catch (error) {
    if (error instanceof PackageUpdateError) throw error;
    throw new PackageUpdateError('request_failed');
  } finally {
    clearTimeout(timer);
  }
}
export function packageUpdateRequestId(): string {
  const bytes = new Uint8Array(16);
  globalThis.crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}
export async function checkPackageUpdate(
  csrf: string,
  force = false,
): Promise<PackageCheck> {
  return check(
    await request(csrf, 'packageupdatecheck', { force: force ? '1' : '0' }),
  );
}
export async function preparePackageUpdate(
  csrf: string,
  revision: string,
  requestId: string,
): Promise<PackageOperation> {
  return operation(
    await request(csrf, 'packageupdateprepare', {
      revision,
      request_id: requestId,
    }),
  );
}
export async function applyPackageUpdate(
  csrf: string,
  id: string,
  revision: string,
  requestId: string,
): Promise<PackageOperation> {
  return operation(
    await request(csrf, 'packageupdateapply', {
      operation_id: id,
      revision,
      request_id: requestId,
      consent: 'install',
    }),
  );
}
export async function getPackageUpdateOverview(
  csrf: string,
  id = '',
): Promise<PackageOverview> {
  const value = await request(csrf, 'packageupdatestatus', {
    operation_id: id,
  });
  if (!record(value) || !keys(value, ['check', 'operation'])) return invalid();
  return {
    check: check(value.check),
    operation: value.operation === null ? null : operation(value.operation),
  };
}
export async function getPackageUpdate(
  csrf: string,
  id: string,
): Promise<PackageOperation> {
  const value = await getPackageUpdateOverview(csrf, id);
  return value.operation ?? invalid();
}
export function packageUpdateBadges(
  checkResult: PackageCheck | undefined,
  installed: string | undefined,
  web: string,
  build: string | undefined,
) {
  const c = checkResult?.state === 'available' ? checkResult.candidate : null;
  if (!c) return { core: false, web: false, build: false };
  const newerWeb = c.web_version.split('.').map(Number);
  const oldWeb = web.split('.').map(Number);
  let webNew = false;
  for (let i = 0; i < 3; i++) {
    if (newerWeb[i] !== oldWeb[i]) {
      webNew = newerWeb[i] > oldWeb[i];
      break;
    }
  }
  return {
    core: !!installed && c.core_version !== installed.replace(/\+b[0-9]+$/, ''),
    web: webNew,
    build: c.build > Number(build ?? 0),
  };
}

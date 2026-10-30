import { ShareError } from '@/api/shareClient';

export type TechnicalState = {
  state: 'idle' | 'connecting' | 'connected' | 'stopped' | 'expired' | 'failed';
  session_id: string | null;
  expires_at: number | null;
  code: string | null;
};
export async function technicalRequest(
  csrf: string,
  cmd: 'technicalstart' | 'technicalstatus' | 'technicalstop',
  invitation?: string,
): Promise<TechnicalState> {
  const params: Record<string, string> = {};
  if (cmd === 'technicalstart') {
    params.invitation = invitation?.trim() ?? '';
    params.consent = 'temporary_root_access';
    if (!params.invitation || params.invitation.length > 16384)
      throw new ShareError('invalid_invitation');
  }
  const controller = new AbortController();
  const timer = globalThis.setTimeout(() => controller.abort(), 15000);
  let v: unknown;
  try {
    const response = await fetch('/index.php', {
      method: 'POST',
      credentials: 'same-origin',
      redirect: 'error',
      signal: controller.signal,
      body: new URLSearchParams({ cmd, csrf_token: csrf, ...params }),
    });
    if (
      !/^application\/json(?:;|$)/i.test(
        response.headers.get('Content-Type') ?? '',
      )
    )
      throw new ShareError('invalid_response');
    const reader = response.body?.getReader();
    if (!reader) throw new ShareError('invalid_response');
    let raw = '';
    let size = 0;
    const decoder = new TextDecoder('utf-8', { fatal: true });
    try {
      while (true) {
        const chunk = await reader.read();
        if (chunk.done) break;
        size += chunk.value.byteLength;
        if (size > 4096) throw new ShareError('invalid_response');
        raw += decoder.decode(chunk.value, { stream: true });
      }
      raw += decoder.decode();
    } finally {
      await reader.cancel().catch(() => {});
      reader.releaseLock();
    }
    v = JSON.parse(raw);
    if (!response.ok) {
      const code = (v as { error?: unknown })?.error;
      throw new ShareError(
        typeof code === 'string' && /^[a-z_]{1,64}$/.test(code)
          ? code
          : 'connection_failed',
      );
    }
  } finally {
    globalThis.clearTimeout(timer);
  }
  if (
    v === null ||
    typeof v !== 'object' ||
    Array.isArray(v) ||
    Object.keys(v).sort().join(',') !== 'code,expires_at,session_id,state'
  )
    throw new ShareError('invalid_response');
  const s = v as Record<string, unknown>;
  if (
    ![
      'idle',
      'connecting',
      'connected',
      'stopped',
      'expired',
      'failed',
    ].includes(String(s.state)) ||
    !(
      s.session_id === null ||
      (typeof s.session_id === 'string' && /^[a-f0-9]{32}$/.test(s.session_id))
    ) ||
    !(
      s.expires_at === null ||
      (Number.isSafeInteger(s.expires_at) && (s.expires_at as number) > 0)
    ) ||
    !(
      s.code === null ||
      (typeof s.code === 'string' && /^[a-z_]{1,64}$/.test(s.code))
    )
  )
    throw new ShareError('invalid_response');
  return s as TechnicalState;
}

import { DpiError, request } from '@/api/dpiClient';

export type SmartDnsStatus = {
  version: string;
  installed: { installed: boolean; version: string | null };
  available: { available: boolean; code: string };
  external_detected: boolean;
  job: {
    id: string;
    state: 'queued' | 'running' | 'completed' | 'failed' | 'interrupted';
    code: string | null;
  } | null;
};

export async function getSmartDnsStatus(csrf: string): Promise<SmartDnsStatus> {
  const { value } = await request(csrf, 'smartdnsstatus', {}, 4096);
  const v = value as SmartDnsStatus;
  if (
    !v ||
    typeof v.version !== 'string' ||
    typeof v.installed?.installed !== 'boolean' ||
    typeof v.available?.available !== 'boolean' ||
    typeof v.external_detected !== 'boolean' ||
    (v.job !== null &&
      (!/^[a-f0-9]{32}$/.test(v.job?.id ?? '') ||
        !['queued', 'running', 'completed', 'failed', 'interrupted'].includes(
          v.job?.state,
        )))
  )
    throw new DpiError('invalid_response');
  return v;
}

export async function installSmartDns(csrf: string, id: string) {
  await request(csrf, 'smartdnsinstall', {
    request_id: id,
    consent: 'install',
  });
}

import { request } from '@/api/dpiClient';

import { validateMtproto, type MtprotoAddresses } from '@/utils/mtprotoInstall';

export async function getMtprotoAddresses(
  csrf: string,
): Promise<MtprotoAddresses> {
  const { value } = await request(csrf, 'mtprotoaddresses', {}, 1024);
  const data = value as MtprotoAddresses;
  if (
    !data ||
    Object.keys(data).sort().join(',') !== 'docker,router' ||
    [data.router, data.docker].some(
      (host) =>
        host !== null &&
        (typeof host !== 'string' ||
          validateMtproto({
            server: host,
            port: '1443',
            secret: 'dd' + '0'.repeat(32),
          }).server),
    )
  )
    throw new Error('invalid_response');
  return data;
}

export type RouterInstallJob = {
  id: string;
  state: 'queued' | 'running' | 'failed' | 'completed';
  port: number;
  code: string | null;
};

export async function routerInstallJob(
  csrf: string,
  start?: { request_id: string; port: string; secret: string },
): Promise<RouterInstallJob | null> {
  const { value } = await request(
    csrf,
    start ? 'mtprotoinstall' : 'mtprotoinstallstatus',
    start ?? {},
    1024,
  );
  const job = (value as { job?: RouterInstallJob })?.job;
  if (job === null && !start) return null;
  if (
    !job ||
    !/^[a-f0-9]{32}$/.test(job.id) ||
    (start && job.id !== start.request_id) ||
    !['queued', 'running', 'failed', 'completed'].includes(job.state) ||
    !Number.isInteger(job.port) ||
    job.port < 1024 ||
    job.port > 65535 ||
    (job.code !== null && typeof job.code !== 'string')
  )
    throw new Error('invalid_response');
  return job;
}

export async function routerInstallConnection(csrf: string, id: string) {
  const { value } = await request(
    csrf,
    'mtprotoinstalllink',
    { request_id: id },
    512,
  );
  const data = value as { port: number; secret: string };
  if (
    !data ||
    !Number.isInteger(data.port) ||
    data.port < 1024 ||
    data.port > 65535 ||
    typeof data.secret !== 'string' ||
    !/^dd[a-f0-9]{32}$/.test(data.secret)
  )
    throw new Error('invalid_response');
  return { port: String(data.port), secret: data.secret };
}

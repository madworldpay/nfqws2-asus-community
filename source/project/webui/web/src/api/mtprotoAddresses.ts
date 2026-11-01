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

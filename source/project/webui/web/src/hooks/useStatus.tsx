import { useMemo } from 'react';
import { useConfig } from '@/config/useConfig';
import { useQuery } from '@tanstack/react-query';

import { API } from '@/api/client';

import { isAuthUnconfigured } from '@/utils/authError';
import { parsePackageVersion, type Version } from '@/utils/packageVersion';

export const useVersionCheck = (url: string, enabled = true) => {
  return useQuery({
    queryKey: ['version', url],
    enabled,
    queryFn: async () => {
      const res = await fetch(url);
      if (!res.ok) {
        return { tag_name: 'v0.0.0', html_url: '' };
      }
      return res.json();
    },
    select: (data: { tag_name?: string; html_url?: string }) => {
      return {
        url: data.html_url,
        version: parsePackageVersion(data.tag_name).version,
      };
    },
  });
};

type UseStatusResult = {
  platform: 'asus-entware' | 'openwrt';
  authUnavailable?: boolean;
  status: boolean;
  nfqws2: boolean;
  service: boolean;
  arkLoaded?: boolean | null;
  version?: Version;
  packageVersion?: string;
  buildNumber?: string;
  anonym: boolean;
  authenticated: boolean;
  csrfToken?: string;
  username?: string;
  webVersion?: Version;
  latest?: Version;
  webLatest?: Version;
  url?: string;
  webUrl?: string;
  isPending: boolean;
};

export const useStatus = (): UseStatusResult => {
  const { data: status, isPending, isError, error } = API.status();

  const { updateUrl, webUpdateUrl } = useConfig(status?.nfqws2 ?? false);

  const { data: latest } = useVersionCheck(
    updateUrl,
    false, // ASUS packages have no public update feed yet.
  );

  const { data: latestWeb } = useVersionCheck(webUpdateUrl, false);

  return useMemo(() => {
    if (!isError && !isPending && status?.status === 0) {
      const current = parsePackageVersion(status.version);
      const currentWeb = parsePackageVersion(process.env.APP_VERSION).version;

      return {
        platform: status.platform === 'openwrt' ? 'openwrt' : 'asus-entware',
        status: true,
        nfqws2: status.nfqws2,
        service: status.service,
        arkLoaded:
          typeof status.ark_loaded === 'boolean' ? status.ark_loaded : null,
        ...current,
        anonym: status.anonym,
        authenticated: status.authenticated ?? !status.anonym,
        csrfToken: status.csrf_token,
        username: status.username,
        webVersion: currentWeb,
        latest: latest?.version,
        webLatest: latestWeb?.version,
        url: latest?.url,
        webUrl: latestWeb?.url,
        isPending,
      };
    }

    return {
      platform: 'asus-entware',
      authUnavailable: isError && isAuthUnconfigured(error),
      status: isError || isPending,
      nfqws2: true,
      service: false,
      anonym: true,
      authenticated: false,
      isPending,
    };
  }, [error, isError, isPending, latest, latestWeb, status]);
};

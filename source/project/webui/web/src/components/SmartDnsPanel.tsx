import { useCallback, useEffect, useState } from 'react';
import { Alert, Box, Button, Link, Stack, Typography } from '@mui/material';

import {
  getSmartDnsStatus,
  installSmartDns,
  type SmartDnsStatus,
} from '@/api/smartDnsClient';
import type { Checkup } from '@/api/smartDnsConfigClient';
import { newSupportSubmissionId } from '@/api/supportReport';

import { InlineHelp } from '@/components/InlineHelp';
import { RouterCheckup } from '@/components/RouterCheckup';
import { SmartDnsConfigurator } from '@/components/SmartDnsConfigurator';

import { useStatus } from '@/hooks/useStatus';
import { useTranslation } from '@/hooks/useTranslation';

export const SmartDnsPanel = () => {
  const { csrfToken } = useStatus();
  const { t } = useTranslation();
  const [data, setData] = useState<SmartDnsStatus>();
  const [error, setError] = useState('');
  const [checkup, setCheckup] = useState<Checkup>();
  const [submitting, setSubmitting] = useState(false);
  const active =
    data?.job?.state === 'queued' || data?.job?.state === 'running';
  const load = useCallback(async () => {
    if (!csrfToken) return;
    try {
      setData(await getSmartDnsStatus(csrfToken));
      setError('');
    } catch {
      setError(t('smartdns.request_error'));
    }
  }, [csrfToken, t]);
  useEffect(() => {
    void load();
  }, [load]);
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => void load(), 1500);
    return () => clearInterval(timer);
  }, [active, load]);
  const install = async () => {
    if (!csrfToken || submitting) return;
    setSubmitting(true);
    try {
      await installSmartDns(
        csrfToken,
        newSupportSubmissionId().replace(/-/g, ''),
      );
      await load();
    } catch {
      setError(t('smartdns.request_error'));
      // A lost HTTP reply does not cancel the detached installation.
      await load();
    } finally {
      setSubmitting(false);
    }
  };
  return (
    <Box sx={{ position: 'absolute', inset: 0, overflowY: 'auto', p: 2 }}>
      <Stack spacing={2} sx={{ maxWidth: 1000, mx: 'auto' }}>
        <Stack
          direction="row"
          alignItems="center"
          justifyContent="space-between"
        >
          <Typography component="h1" variant="h6">
            SmartDNS{' '}
            <InlineHelp title={t('smartdns.guide')}>
              <Stack spacing={2}>
                <Typography>{t('smartdns.intro')}</Typography>
                <Typography>{t('smartdns.scope')}</Typography>
                <Typography>{t('smartdns.resources')}</Typography>
              </Stack>
            </InlineHelp>
          </Typography>
          <Button onClick={() => void load()}>{t('smartdns.refresh')}</Button>
        </Stack>
        <Typography variant="body2">{t('smartdns.short_intro')}</Typography>
        {csrfToken && (
          <RouterCheckup
            csrf={csrfToken}
            onResult={setCheckup}
            scope="smartdns"
          />
        )}
        {data && (
          <Typography variant="caption" color="text.secondary">
            {t('smartdns.engine_version')}: {data.version}
          </Typography>
        )}
        {data?.installed.installed && (
          <>
            {csrfToken && (
              <SmartDnsConfigurator
                csrf={csrfToken}
                external={
                  data.external_detected ||
                  checkup?.items.some(
                    (x) =>
                      x.id === 'dns_runtime' &&
                      x.facts.external_smartdns === true,
                  ) === true
                }
              />
            )}
          </>
        )}
        {active && <Alert severity="info">{t('smartdns.installing')}</Alert>}
        {data?.job && ['failed', 'interrupted'].includes(data.job.state) && (
          <Alert severity="warning">{t('smartdns.failed')}</Alert>
        )}
        {error && <Alert severity="warning">{error}</Alert>}
        {data && !data.installed.installed && !active && (
          <>
            {!data.available.available && (
              <Alert severity="info">{t('smartdns.unavailable')}</Alert>
            )}
            <Button
              variant="contained"
              disabled={submitting || !data.available.available}
              onClick={() => void install()}
            >
              {t('smartdns.install')}
            </Button>
          </>
        )}
        <Link
          href="https://github.com/madworldpay/nfqws2-asus-community/blob/main/SMARTDNS.md"
          target="_blank"
          rel="noreferrer"
        >
          {t('smartdns.guide')}
        </Link>
        <Link
          href="https://github.com/pymumu/smartdns"
          target="_blank"
          rel="noreferrer"
        >
          SmartDNS · pymumu
        </Link>
      </Stack>
    </Box>
  );
};

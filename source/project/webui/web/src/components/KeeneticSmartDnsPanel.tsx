import { useState } from 'react';
import { Alert, Box, Button, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';

import { getSmartDnsStatus, installSmartDns } from '@/api/smartDnsClient';
import {
  saveSmartDnsDraft,
  smartDnsConfigQuery,
  switchKeeneticSmartDns,
} from '@/api/smartDnsConfigClient';
import { emptyProfile, type Profile } from '@/api/smartDnsProfile';
import { newSupportSubmissionId } from '@/api/supportReport';

import { SmartDnsProfileForm } from '@/components/SmartDnsProfileForm';

import { useStatus } from '@/hooks/useStatus';
import { useTranslation } from '@/hooks/useTranslation';

export const KeeneticSmartDnsPanel = () => {
  const { csrfToken } = useStatus();
  const { t } = useTranslation();
  const csrf = csrfToken ?? '';
  const view = useQuery({
    ...smartDnsConfigQuery(csrf),
    enabled: !!csrf,
    refetchInterval: 30000,
  });
  const engine = useQuery({
    queryKey: ['keenetic-smartdns-engine', csrf],
    queryFn: () => getSmartDnsStatus(csrf),
    enabled: !!csrf,
    retry: false,
    refetchInterval: (q) =>
      ['queued', 'running'].includes(q.state.data?.job?.state ?? '')
        ? 1500
        : false,
  });
  const [edit, setEdit] = useState<Profile | null>(null);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);
  const state = view.isError
    ? 'unknown'
    : (view.data?.keenetic_runtime ?? 'unknown');
  const draft = edit ?? view.data?.draft ?? emptyProfile();
  const pending = ['running', 'queued'].includes(engine.data?.job?.state ?? '');
  const busy = working || pending || !csrf;
  const refresh = () => Promise.all([view.refetch(), engine.refetch()]);
  async function perform(action: 'save' | 'start' | 'stop' | 'install') {
    if (busy) return;
    setWorking(true);
    setError('');
    setSaved(false);
    try {
      if (action === 'install')
        await installSmartDns(csrf, newSupportSubmissionId().replace(/-/g, ''));
      if (action === 'stop') await switchKeeneticSmartDns(csrf, null);
      if (action === 'start' && view.data?.draft_hash)
        await switchKeeneticSmartDns(csrf, view.data.draft_hash);
      if (action === 'save') {
        await saveSmartDnsDraft(csrf, draft);
        await view.refetch();
        setEdit(null);
        setSaved(true);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'request_failed');
    } finally {
      await refresh();
      setWorking(false);
    }
  }
  return (
    <Box sx={{ position: 'absolute', inset: 0, overflowY: 'auto', p: 2 }}>
      <Stack spacing={2} sx={{ maxWidth: 1000, mx: 'auto' }}>
        <Typography component="h1" variant="h6">
          SmartDNS · {t(`smartdns.connection_state.${state}`)}
        </Typography>
        <Typography variant="body2">
          {t('smartdns.keenetic.endpoint')}
        </Typography>
        {(view.isError || engine.isError) && (
          <Alert severity="warning">{t('smartdns.request_error')}</Alert>
        )}
        {error && (
          <Alert severity="error">
            {t('smartdns.keenetic.action_error')} ({error})
          </Alert>
        )}
        {engine.data?.job?.state === 'failed' && (
          <Alert severity="error">
            {t('smartdns.failed')} ({engine.data.job.code})
          </Alert>
        )}
        {pending && <Alert severity="info">{t('smartdns.installing')}</Alert>}
        {state === 'external' && (
          <Alert severity="info">{t('smartdns.keenetic.external')}</Alert>
        )}
        <Stack direction="row" gap={1} flexWrap="wrap">
          <Button onClick={() => void refresh()} disabled={!csrf || working}>
            {t('smartdns.refresh')}
          </Button>
          {engine.data && !engine.data.installed.installed && (
            <Button
              variant="outlined"
              onClick={() => void perform('install')}
              disabled={
                busy || state !== 'stopped' || !engine.data.available.available
              }
            >
              {t('smartdns.install')}
            </Button>
          )}
          {engine.data?.installed.installed && state !== 'running' && (
            <Button
              variant="contained"
              onClick={() => void perform('start')}
              disabled={
                busy || state !== 'stopped' || !!edit || !view.data?.draft_hash
              }
            >
              {t('smartdns.keenetic.start')}
            </Button>
          )}
          {state === 'running' && (
            <Button
              variant="outlined"
              disabled={busy}
              onClick={() => void perform('stop')}
            >
              {t('smartdns.keenetic.stop')}
            </Button>
          )}
        </Stack>
        {engine.data &&
          !engine.data.installed.installed &&
          !engine.data.available.available && (
            <Alert severity="info">
              {t('smartdns.unavailable')} ({engine.data.available.code})
            </Alert>
          )}
        {view.data && (
          <>
            <SmartDnsProfileForm
              value={draft}
              disabled={busy || view.isError}
              onChange={(p) => {
                setEdit(p);
                setSaved(false);
                setError('');
              }}
            />
            <Stack direction="row" spacing={2} alignItems="center">
              <Button
                variant="contained"
                disabled={busy || !edit || view.isError}
                onClick={() => void perform('save')}
              >
                {t('smartdns.keenetic.save')}
              </Button>
              {saved && (
                <Typography role="status">
                  {t('smartdns.keenetic.saved')}
                </Typography>
              )}
            </Stack>
          </>
        )}
      </Stack>
    </Box>
  );
};

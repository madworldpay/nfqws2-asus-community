import { useEffect, useRef, useState } from 'react';
import { Alert, Button, Link, Stack } from '@mui/material';

import { DpiError } from '@/api/dpiClient';
import {
  routerInstallConnection,
  routerInstallJob,
  type RouterInstallJob,
} from '@/api/mtprotoAddresses';
import { newSupportSubmissionId } from '@/api/supportReport';

import { useTranslation } from '@/hooks/useTranslation';

import { mtprotoLink, type MtprotoValues } from '@/utils/mtprotoInstall';

function reason(code?: string | null) {
  if (code === 'already_installed') return 'router_exists';
  if (code === 'telegram_unreachable') return 'router_no_telegram';
  if (code === 'forbidden' || code === 'unauthorized') return 'router_login';
  if (code === 'busy' || code === 'recovery_required') return 'router_busy';
  if (code === 'interrupted') return 'router_interrupted';
  if (code === 'link_unavailable') return 'router_no_link';
  return 'router_failed';
}

export function MtprotoRouterInstall({
  csrf,
  values,
}: {
  csrf?: string;
  values: MtprotoValues;
}) {
  const { t } = useTranslation();
  const [job, setJob] = useState<RouterInstallJob | null>(null);
  const [checked, setChecked] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [connection, setConnection] =
    useState<Pick<MtprotoValues, 'port' | 'secret'>>();
  const pending = useRef(false);
  const attempt = useRef<{
    request_id: string;
    port: string;
    secret: string;
  } | null>(null);
  const active = job?.state === 'queued' || job?.state === 'running';
  useEffect(() => {
    if (!csrf) return;
    let current = true;
    let timer: ReturnType<typeof setTimeout>;
    const check = async () => {
      try {
        const result = await routerInstallJob(csrf);
        if (!current) return;
        setChecked(true);
        setError('');
        setJob(result);
        const sent = attempt.current;
        if (
          sent &&
          result?.state === 'completed' &&
          sent.request_id === result.id
        )
          setConnection({ port: String(result.port), secret: sent.secret });
        if (result?.state === 'queued' || result?.state === 'running')
          timer = setTimeout(check, 1500);
      } catch (e) {
        if (current) {
          setChecked(false);
          setError(e instanceof DpiError ? e.code : 'status_unavailable');
        }
      }
    };
    void check();
    return () => {
      current = false;
      clearTimeout(timer);
    };
  }, [csrf, refresh]);

  const start = async () => {
    if (!csrf || pending.current || !checked || active) return;
    pending.current = true;
    setBusy(true);
    setError('');
    setConnection(undefined);
    try {
      let sent = attempt.current;
      if (
        !sent ||
        sent.port !== values.port ||
        sent.secret !== values.secret ||
        job?.state === 'failed'
      ) {
        sent = {
          request_id: newSupportSubmissionId().replace(/-/g, ''),
          port: values.port,
          secret: values.secret,
        };
        attempt.current = sent;
      }
      setJob(await routerInstallJob(csrf, sent));
      setRefresh((n) => n + 1);
    } catch (e) {
      setChecked(false);
      setError(e instanceof DpiError ? e.code : 'status_unavailable');
    } finally {
      pending.current = false;
      setBusy(false);
    }
  };
  const getLink = async () => {
    if (!csrf || !job || pending.current) return;
    pending.current = true;
    setBusy(true);
    setError('');
    try {
      setConnection(await routerInstallConnection(csrf, job.id));
    } catch (e) {
      setError(e instanceof DpiError ? e.code : 'link_unavailable');
    } finally {
      pending.current = false;
      setBusy(false);
    }
  };
  return (
    <Stack spacing={1} alignItems="flex-start">
      {!csrf ? (
        <Alert severity="info">{t('mtproto.router_login')}</Alert>
      ) : (
        <>
          {job?.state !== 'completed' && (
            <Button
              variant="contained"
              disabled={busy || active || !checked}
              onClick={() => void start()}
            >
              {t('mtproto.router_install')}
            </Button>
          )}
          {active && (
            <Alert severity="info" role="status">
              {t('mtproto.router_working', { port: job.port })}
            </Alert>
          )}
          {job?.state === 'failed' && !error && (
            <Alert severity="error">{t(`mtproto.${reason(job.code)}`)}</Alert>
          )}
          {job?.state === 'completed' && (
            <>
              <Alert severity="success" role="status">
                {t('mtproto.router_done', { port: job.port })}
              </Alert>
              {connection ? (
                <Link
                  href={mtprotoLink({ server: values.server, ...connection })}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {t('mtproto.open_telegram')}
                </Link>
              ) : (
                <Button disabled={busy} onClick={() => void getLink()}>
                  {t('mtproto.router_link')}
                </Button>
              )}
            </>
          )}
          {error && (
            <>
              <Alert severity="warning">
                {t(
                  error === 'status_unavailable'
                    ? 'mtproto.router_status_failed'
                    : `mtproto.${reason(error)}`,
                )}
              </Alert>
              <Button disabled={busy} onClick={() => setRefresh((n) => n + 1)}>
                {t('mtproto.router_check')}
              </Button>
            </>
          )}
        </>
      )}
    </Stack>
  );
}

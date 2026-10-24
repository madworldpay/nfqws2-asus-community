import { useCallback, useEffect, useState } from 'react';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';
import {
  Alert,
  AlertTitle,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableRow,
  Tooltip,
  Typography,
} from '@mui/material';

import { API } from '@/api/client';
import type { ArkActionResponse, ArkStatusResponse } from '@/api/schema';

import { useStatus } from '@/hooks/useStatus';
import { useTranslation } from '@/hooks/useTranslation';

import {
  classifyArkReadiness,
  normalizeArkDiagnostics,
  type ArkReadiness,
} from '@/utils/arkReadiness';
import {
  compareQueueSamples,
  type QueueComparison,
} from '@/utils/queueSamples';

export const ArkReadinessSummary = ({
  readiness,
  checking = false,
}: {
  readiness: ArkReadiness;
  checking?: boolean;
}) => {
  const { t } = useTranslation();
  const unloadedWithMissingFlags =
    readiness.result === 'flags_unknown' && readiness.runtime === 'unloaded';
  return (
    <Alert
      severity={
        checking
          ? 'info'
          : readiness.runtime === 'loaded'
            ? 'error'
            : readiness.result === 'absent' ||
                readiness.result === 'ready' ||
                unloadedWithMissingFlags
              ? 'success'
              : 'warning'
      }
    >
      <AlertTitle>
        {t(
          !checking && readiness.runtime === 'loaded'
            ? 'ark.runtime_loaded_title'
            : 'ark.check_title',
        )}
      </AlertTitle>
      {checking
        ? t('ark.checking')
        : unloadedWithMissingFlags
          ? t('ark.readiness.runtime_clear')
          : t(`ark.readiness.${readiness.result}`, {
              disabled: readiness.disabled,
              enabled: readiness.enabled,
              runtime: t(`ark.${readiness.runtime}`),
            })}
      {!checking && unloadedWithMissingFlags && (
        <Typography variant="caption" component="p" sx={{ mb: 0 }}>
          {t('ark.readiness.unavailable_flags_note', {
            disabled: readiness.disabled,
          })}
        </Typography>
      )}
    </Alert>
  );
};

export const ArkDiagnosticsTable = ({
  diagnostics: data,
}: {
  diagnostics: unknown;
}) => {
  const { t } = useTranslation();
  const diagnostics = normalizeArkDiagnostics(data);
  if (!diagnostics) return null;
  const positive: Record<string, boolean> = {
    ark_present:
      diagnostics.ark.present === 'absent' &&
      diagnostics.ark.loaded === 'unloaded',
    ark_runtime: diagnostics.ark.loaded === 'unloaded',
    queue:
      diagnostics.nfqueue.state === 'bound' &&
      diagnostics.nfqueue.queue_number !== null,
    queue_state: diagnostics.nfqueue.state === 'bound',
    sequence:
      diagnostics.nfqueue.sequence !== null && diagnostics.nfqueue.sequence > 0,
    process: diagnostics.process_running === true,
  };
  return (
    <Table size="small" aria-label={t('ark.diagnostics')}>
      <TableBody>
        {(
          [
            ['ark_present', t(`ark.${diagnostics.ark.present}`)],
            ['ark_runtime', t(`ark.${diagnostics.ark.loaded}`)],
            ['queue', diagnostics.nfqueue.queue_number ?? t('ark.unknown')],
            ['queue_state', t(`ark.${diagnostics.nfqueue.state}`)],
            ['sequence', diagnostics.nfqueue.sequence ?? t('ark.unknown')],
            [
              'process',
              t(
                diagnostics.process_running === null
                  ? 'ark.unknown'
                  : diagnostics.process_running
                    ? 'ark.running'
                    : 'ark.stopped',
              ),
            ],
          ] as const
        ).map(([label, value]) => (
          <TableRow key={label}>
            <TableCell>{t(`ark.${label}`)}</TableCell>
            <TableCell align="right">
              <Stack
                direction="row"
                spacing={0.75}
                alignItems="center"
                justifyContent="flex-end"
              >
                <span>{value}</span>
                {positive[label] && (
                  <CheckCircleOutlineIcon color="success" fontSize="small" />
                )}
              </Stack>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
};

export const ArkFlagsTable = ({ flags }: { flags: ArkReadiness['flags'] }) => {
  const { t } = useTranslation();
  const [showInternalHelp, setShowInternalHelp] = useState(false);
  return (
    <>
      <Table size="small" aria-label={t('ark.flags')}>
        <TableBody>
          {flags.map((flag) => (
            <TableRow key={flag.key}>
              <TableCell>{t(`ark.functions.${flag.key}`)}</TableCell>
              <TableCell align="right">
                <Stack
                  direction="row"
                  spacing={0.75}
                  alignItems="center"
                  justifyContent="flex-end"
                >
                  <span>{t(`ark.${flag.state}`)}</span>
                  {flag.key === 'ark_ids_enable' &&
                    flag.state === 'unknown' && (
                      <Tooltip title={t('ark.internal_flag_help_title')}>
                        <IconButton
                          size="small"
                          aria-label={t('ark.internal_flag_help_title')}
                          onClick={() => setShowInternalHelp(true)}
                        >
                          <HelpOutlineIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    )}
                  {flag.state === 'disabled' && (
                    <CheckCircleOutlineIcon color="success" fontSize="small" />
                  )}
                </Stack>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <Dialog
        open={showInternalHelp}
        onClose={() => setShowInternalHelp(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>{t('ark.internal_flag_help_title')}</DialogTitle>
        <DialogContent>
          <Typography>{t('ark.internal_flag_help')}</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowInternalHelp(false)}>
            {t('common.close')}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
};

export const ArkDialog = ({ onClose }: { onClose: VoidFunction }) => {
  const { t } = useTranslation();
  const { csrfToken } = useStatus();
  const [status, setStatus] = useState<ArkStatusResponse>();
  const [checkingArk, setCheckingArk] = useState(true);
  const [pending, setPending] = useState(false);
  const [queueResult, setQueueResult] = useState<QueueComparison>();
  const [checkingQueue, setCheckingQueue] = useState(false);
  const [error, setError] = useState<
    NonNullable<ArkActionResponse['error']> | ''
  >('');
  const [message, setMessage] = useState<
    NonNullable<ArkActionResponse['message']> | 'reboot_needed' | ''
  >('');
  const [confirm, setConfirm] = useState<'arkprepare' | 'arkrestore' | null>(
    null,
  );

  const load = useCallback(async () => {
    setStatus(undefined);
    setCheckingArk(true);
    setError('');
    try {
      const { data } = await API.arkStatus();
      setStatus(data);
      setError(data?.status === 0 ? '' : (data?.error ?? 'read_failed'));
    } catch {
      setError('read_failed');
    } finally {
      setCheckingArk(false);
      void API.invalidateStatus();
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  const checkQueue = async () => {
    if (pending) return;
    setPending(true);
    setCheckingQueue(true);
    setQueueResult(undefined);
    try {
      const { data: first } = await API.arkStatus();
      await new Promise((resolve) => window.setTimeout(resolve, 10000));
      const { data: second } = await API.arkStatus();
      setStatus(second);
      setQueueResult(
        compareQueueSamples(
          first?.status === 0 ? first.diagnostics?.nfqueue : undefined,
          second?.status === 0 ? second.diagnostics?.nfqueue : undefined,
        ),
      );
    } catch {
      setStatus(undefined);
      setQueueResult({ result: 'unavailable' });
    } finally {
      setCheckingQueue(false);
      setPending(false);
      void API.invalidateStatus();
    }
  };

  const run = async () => {
    if (!confirm || !csrfToken || !status?.revision || pending) return;
    setPending(true);
    setError('');
    setMessage('');
    try {
      const { data } = await API.arkAction(confirm, csrfToken, status.revision);
      if (data?.status === 0) {
        setMessage(
          data.reboot_required ? 'reboot_needed' : (data.message ?? 'prepared'),
        );
      } else {
        setError(data?.error ?? 'apply_failed');
      }
      setConfirm(null);
      // Refresh after every result, including a partial failure with a retained backup.
      const { data: refreshed } = await API.arkStatus();
      setStatus(refreshed);
      if (refreshed?.status !== 0) setError(refreshed?.error ?? 'read_failed');
    } catch {
      setStatus(undefined);
      setError('request_failed');
      setConfirm(null);
    } finally {
      setPending(false);
      void API.invalidateStatus();
    }
  };

  const canAct = status?.status === 0 && !!csrfToken && !pending;
  const activeBackup = status?.backup && !status.backup.restored;
  const readiness = classifyArkReadiness(status);
  const absent = readiness.result === 'absent';
  const showDetails = !absent && !checkingArk && status?.status === 0;
  const enabled = Array.isArray(status?.flags)
    ? status.flags.filter((flag) => flag?.enabled === true)
    : [];

  return (
    <Dialog open maxWidth="sm" fullWidth onClose={() => !pending && onClose()}>
      <DialogTitle>{t('ark.title')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2}>
          <ArkReadinessSummary
            readiness={readiness}
            checking={checkingArk || pending}
          />
          {showDetails && (
            <>
              <Typography variant="body2">{t('ark.about')}</Typography>
              <Alert severity="info">{t('ark.model_hint')}</Alert>
              {status?.model && status.model !== 'GT-BE19000AI' && (
                <Alert severity="warning">
                  {t('ark.other_model_warning', { model: status.model })}
                </Alert>
              )}
              <Typography variant="body2">{t('ark.explanation')}</Typography>
              <ArkDiagnosticsTable diagnostics={status?.diagnostics} />
              <Typography variant="body2">
                {t('ark.queue_test_hint')}
              </Typography>
              {checkingQueue && (
                <Alert severity="info">{t('ark.queue_testing')}</Alert>
              )}
              {queueResult && (
                <Alert
                  severity={
                    queueResult.result === 'increased' ? 'success' : 'warning'
                  }
                >
                  {queueResult.result === 'increased' ||
                  queueResult.result === 'unchanged'
                    ? t(`ark.queue_${queueResult.result}`, {
                        before: queueResult.before,
                        after: queueResult.after,
                        delta: queueResult.delta,
                      })
                    : t(`ark.queue_${queueResult.result}`)}
                </Alert>
              )}
              {!status && !error && <CircularProgress size={24} />}
              {status?.status === 0 && (
                <ArkFlagsTable flags={readiness.flags} />
              )}
            </>
          )}
          {status?.backup && (
            <Typography variant="body2">
              {t(
                status.backup.restored
                  ? 'ark.backup_restored'
                  : 'ark.backup_saved',
                {
                  date: new Date(status.backup.created).toLocaleString(),
                },
              )}
            </Typography>
          )}
          {confirm && (
            <Alert severity="warning">
              {confirm === 'arkprepare'
                ? t('ark.confirm_prepare', {
                    functions:
                      enabled
                        .map((flag) => t(`ark.functions.${flag.key}`))
                        .join(', ') || t('ark.none'),
                  })
                : t('ark.confirm_restore')}
            </Alert>
          )}
          {message && <Alert severity="success">{t(`ark.${message}`)}</Alert>}
          {error && <Alert severity="error">{t(`ark.errors.${error}`)}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ flexWrap: 'wrap' }}>
        {!absent && (
          <>
            {showDetails && (
              <Button
                disabled={pending || status?.status !== 0}
                onClick={() => void checkQueue()}
              >
                {t('ark.queue_test')}
              </Button>
            )}
            <Button
              disabled={pending || checkingArk}
              onClick={() => void load()}
            >
              {t('ark.refresh')}
            </Button>
          </>
        )}
        <Button
          onClick={() => (confirm ? setConfirm(null) : onClose())}
          disabled={pending}
        >
          {t(confirm ? 'common.cancel' : 'common.close')}
        </Button>
        {confirm ? (
          <Button
            variant="contained"
            color="warning"
            disabled={!canAct}
            onClick={() => void run()}
          >
            {pending ? <CircularProgress size={18} /> : t('ark.confirm')}
          </Button>
        ) : (
          <>
            {(!absent || activeBackup) && (
              <Button
                disabled={!canAct || !activeBackup}
                onClick={() => setConfirm('arkrestore')}
              >
                {t('ark.restore')}
              </Button>
            )}
            {showDetails && (
              <Button
                variant="contained"
                disabled={
                  !canAct ||
                  !!activeBackup ||
                  typeof status?.ark_loaded !== 'boolean'
                }
                onClick={() => setConfirm('arkprepare')}
              >
                {t('ark.prepare')}
              </Button>
            )}
          </>
        )}
      </DialogActions>
    </Dialog>
  );
};

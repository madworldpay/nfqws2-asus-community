import { useEffect, useRef, useState } from 'react';
import DownloadIcon from '@mui/icons-material/Download';
import {
  Alert,
  Box,
  Button,
  LinearProgress,
  Stack,
  Typography,
} from '@mui/material';

import { DpiError } from '@/api/dpiClient';
import {
  checkDpiSite,
  DPI_SITE_SERVICES,
  type DpiSiteContext,
  type DpiSiteService,
  type DpiSiteCheck as SiteObservation,
} from '@/api/dpiSiteCheckClient';

import { useTranslation } from '@/hooks/useTranslation';

import {
  downloadDpiSiteCheck,
  dpiSiteClockChanged,
  dpiSiteContextLabel,
  dpiSiteResponseLabel,
} from '@/utils/dpiSiteCheckDownload';

const Snapshot = ({
  value,
  label,
}: {
  value: DpiSiteContext;
  label: string;
}) => {
  const { t } = useTranslation();
  return (
    <Box sx={{ flex: 1, minWidth: 0 }}>
      <Typography variant="subtitle2">{label}</Typography>
      <Typography variant="body2">
        {t('dpi_site_check.nfqws')}:{' '}
        {t(
          value.nfqws === 'unknown'
            ? 'dpi_site_check.unknown'
            : value.nfqws === 'running'
              ? 'dpi_site_check.running_state'
              : 'dpi_site_check.stopped_state',
        )}
      </Typography>
      <Typography variant="body2">
        {t('dpi_site_check.mode')}:{' '}
        {value.mode === 'unknown' ? t('dpi_site_check.unknown') : value.mode}
      </Typography>
      <Typography variant="body2" sx={{ overflowWrap: 'anywhere' }}>
        {t('dpi_site_check.sha')}:{' '}
        {value.config_sha256 ?? t('dpi_site_check.unknown')}
      </Typography>
    </Box>
  );
};

function serverTime(seconds: number) {
  const date = new Date(seconds * 1000);
  return Number.isNaN(date.getTime()) ? String(seconds) : date.toISOString();
}

export const DpiSiteCheck = ({
  csrfToken,
  onRunning,
}: {
  csrfToken: string;
  onRunning: (running: boolean) => void;
}) => {
  const { t } = useTranslation();
  const [service, setService] = useState<DpiSiteService>('facebook');
  const [reports, setReports] = useState<SiteObservation[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');
  const pending = useRef(false);
  const generation = useRef(0);
  useEffect(
    () => () => {
      // The in-flight request is server-bounded. Its late reply cannot start the
      // remaining targets or overwrite results belonging to a reopened dialog.
      generation.current++;
      onRunning(false);
    },
    [onRunning],
  );

  const run = async () => {
    if (pending.current) return;
    pending.current = true;
    const ownGeneration = ++generation.current;
    setRunning(true);
    onRunning(true);
    setError('');
    setReports([]);
    try {
      for (const target of DPI_SITE_SERVICES[service]) {
        const report = await checkDpiSite(csrfToken, target);
        if (generation.current !== ownGeneration) return;
        setReports((current) => [...current, report]);
      }
    } catch (failure) {
      if (generation.current === ownGeneration)
        setError(failure instanceof DpiError ? failure.code : 'request_failed');
    } finally {
      if (generation.current === ownGeneration) {
        pending.current = false;
        setRunning(false);
        onRunning(false);
      }
    }
  };
  const sessionError = [
    'unauthorized',
    'forbidden',
    'auth_required',
    'csrf_failed',
    'origin_rejected',
  ].includes(error);
  const busy = ['busy', 'terminal_busy', 'dpi_busy', 'job_busy'].includes(
    error,
  );
  return (
    <Stack
      component="section"
      spacing={1.5}
      aria-label={t('dpi_site_check.title')}
      aria-busy={running}
      sx={{ flexShrink: 0, minWidth: 0 }}
    >
      <Typography variant="body2">{t('dpi_site_check.incomplete')}</Typography>
      <Typography variant="body2">{t('dpi_site_check.dns_scope')}</Typography>
      <Typography variant="caption">
        {t('dpi_site_check.snapshot_scope')}
      </Typography>
      <Typography variant="caption">
        {t('dpi_site_check.switch_hint')}
      </Typography>
      <Stack
        direction="row"
        gap={1}
        useFlexGap
        flexWrap="wrap"
        aria-label={t('dpi_site_check.service')}
      >
        {(Object.keys(DPI_SITE_SERVICES) as DpiSiteService[]).map((name) => (
          <Button
            key={name}
            variant={service === name ? 'contained' : 'outlined'}
            disabled={running}
            aria-pressed={service === name}
            onClick={() => {
              if (pending.current) return;
              setService(name);
              setReports([]);
              setError('');
            }}
          >
            {t(`dpi_site_check.service_${name}`)}
          </Button>
        ))}
      </Stack>
      <Stack direction="row" gap={1} useFlexGap flexWrap="wrap">
        <Button
          variant="contained"
          disabled={running}
          onClick={() => void run()}
        >
          {t(running ? 'dpi_site_check.running' : 'dpi_site_check.run')}
        </Button>
        <Button
          startIcon={<DownloadIcon />}
          disabled={running || !reports.length}
          onClick={() => {
            try {
              downloadDpiSiteCheck(service, reports, t);
            } catch {
              setError('download_failed');
            }
          }}
        >
          {t('dpi_site_check.download')}
        </Button>
      </Stack>
      {running && <LinearProgress aria-label={t('dpi_site_check.running')} />}
      {!!error && (
        <Alert severity={busy ? 'warning' : 'error'}>
          {t(
            sessionError
              ? 'dpi_terminal.session_error'
              : busy
                ? 'dpi_site_check.busy'
                : error === 'invalid_response'
                  ? 'dpi_site_check.invalid_response'
                  : error === 'download_failed'
                    ? 'dpi_site_check.download_failed'
                    : 'dpi_site_check.request_failed',
          )}
        </Alert>
      )}
      <Stack spacing={2} aria-live="polite">
        {reports.map((report) => {
          const r = report.response;
          const warning =
            r.outcome !== 'response' ||
            r.body_limited ||
            (r.http_status !== null && r.http_status >= 400);
          return (
            <Stack
              key={report.target}
              component="article"
              spacing={1}
              data-dpi-site-result={report.target}
              sx={{
                p: 1.5,
                border: 1,
                borderColor: 'divider',
                borderRadius: 1,
                minWidth: 0,
              }}
            >
              <Typography variant="subtitle2" sx={{ overflowWrap: 'anywhere' }}>
                {report.url}
              </Typography>
              <Alert severity={warning ? 'warning' : 'info'}>
                HTTP {r.http_status ?? '—'} — {dpiSiteResponseLabel(report, t)}
              </Alert>
              <Typography variant="body2">
                {t('dpi_site_check.bytes')}: {r.bytes_read};{' '}
                {t('dpi_site_check.body_limited')}:{' '}
                {t(r.body_limited ? 'dpi_site_check.yes' : 'dpi_site_check.no')}
              </Typography>
              <Typography variant="body2" sx={{ overflowWrap: 'anywhere' }}>
                {t('dpi_site_check.redirect')}: {r.redirect ?? '—'}
              </Typography>
              <Typography variant="body2">
                {t('dpi_site_check.elapsed')}: {r.elapsed_ms ?? '—'};{' '}
                {t('dpi_site_check.error_code')}: {r.error_code ?? '—'}
              </Typography>
              <Typography variant="caption" sx={{ overflowWrap: 'anywhere' }}>
                {t('dpi_site_check.time')}: {serverTime(report.started_at)} →{' '}
                {serverTime(report.finished_at)}
              </Typography>
              {dpiSiteClockChanged(report) && (
                <Alert severity="warning">
                  {t('dpi_site_check.clock_changed')}
                </Alert>
              )}
              <Typography variant="body2">
                {t('dpi_site_check.context')}:{' '}
                {dpiSiteContextLabel(report.context.changed, t)}
              </Typography>
              <Stack direction={{ xs: 'column', sm: 'row' }} gap={1.5}>
                <Snapshot
                  label={t('dpi_site_check.before')}
                  value={report.context.before}
                />
                <Snapshot
                  label={t('dpi_site_check.after')}
                  value={report.context.after}
                />
              </Stack>
            </Stack>
          );
        })}
      </Stack>
    </Stack>
  );
};

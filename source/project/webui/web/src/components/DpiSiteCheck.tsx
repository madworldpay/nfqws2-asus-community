import { useEffect, useRef, useState } from 'react';
import DownloadIcon from '@mui/icons-material/Download';
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  LinearProgress,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';

import { DpiError } from '@/api/dpiClient';
import {
  checkDpiSite,
  checkDpiTarget,
  DPI_SITE_SERVICES,
  type DpiSiteContext,
  type DpiSiteDnsScope,
  type DpiSiteService,
  type DpiSiteObservation as SiteObservation,
} from '@/api/dpiSiteCheckClient';

import { FrankShareButton } from '@/components/ShareDialog';

import { useTranslation } from '@/hooks/useTranslation';

import {
  buildDpiSiteCheckText,
  downloadDpiSiteCheck,
  dpiSiteClockChanged,
  dpiSiteContextLabel,
  dpiSiteDiagnosis,
  dpiSiteResponseLabel,
  dpiSiteTraceHops,
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
  initialTargets,
}: {
  csrfToken: string;
  onRunning: (running: boolean) => void;
  initialTargets?: string[];
}) => {
  const { t } = useTranslation();
  const [service, setService] = useState<DpiSiteService>(
    initialTargets?.length ? 'custom' : 'facebook',
  );
  const [customTarget, setCustomTarget] = useState(
    initialTargets?.join('\n') ?? '',
  );
  const [dnsScope, setDnsScope] = useState<DpiSiteDnsScope>('local_resolver');
  const [reports, setReports] = useState<SiteObservation[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');
  const [preview, setPreview] = useState(false);
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
      if (service === 'custom') {
        const targets = customTarget
          .split(/\r?\n/)
          .map((value) => value.trim())
          .filter(Boolean);
        if (
          !targets.length ||
          targets.length > 10 ||
          new Set(targets).size !== targets.length
        )
          throw new DpiError('invalid_request');
        for (const target of targets) {
          for (const operation of ['https', 'route'] as const) {
            const report = await checkDpiTarget(
              csrfToken,
              target,
              operation,
              dnsScope,
            );
            if (generation.current !== ownGeneration) return;
            setReports((current) => [...current, report]);
          }
        }
      } else {
        for (const target of DPI_SITE_SERVICES[service]) {
          const report = await checkDpiSite(csrfToken, target, dnsScope);
          if (generation.current !== ownGeneration) return;
          setReports((current) => [...current, report]);
        }
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
      <Typography variant="body2">
        {t(
          service === 'custom'
            ? 'dpi_site_check.custom_scope'
            : 'dpi_site_check.incomplete',
        )}
      </Typography>
      <Typography variant="body2">{t('dpi_site_check.dns_scope')}</Typography>
      <Stack
        direction="row"
        gap={1}
        useFlexGap
        flexWrap="wrap"
        aria-label={t('dpi_site_check.dns_choice')}
      >
        {(['local_resolver', 'system_resolver'] as const).map((scope) => (
          <Button
            key={scope}
            size="small"
            variant={dnsScope === scope ? 'contained' : 'outlined'}
            disabled={running}
            aria-pressed={dnsScope === scope}
            onClick={() => {
              if (pending.current) return;
              setDnsScope(scope);
              setReports([]);
              setError('');
            }}
          >
            {t(`dpi_site_check.dns_button_${scope}`)}
          </Button>
        ))}
      </Stack>
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
        {(
          [...Object.keys(DPI_SITE_SERVICES), 'custom'] as DpiSiteService[]
        ).map((name) => (
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
      {service === 'custom' && (
        <TextField
          label={t('dpi_site_check.custom_target')}
          placeholder="example.com / 1.1.1.1"
          value={customTarget}
          disabled={running}
          size="small"
          fullWidth
          multiline
          minRows={3}
          helperText={t('dpi_site_check.custom_hint')}
          slotProps={{ htmlInput: { maxLength: 4096 } }}
          onChange={(event) => {
            if (pending.current) return;
            setCustomTarget(event.target.value);
            setReports([]);
            setError('');
          }}
        />
      )}
      <Stack direction="row" gap={1} useFlexGap flexWrap="wrap">
        <Button
          variant="contained"
          disabled={running || (service === 'custom' && !customTarget.trim())}
          onClick={() => void run()}
        >
          {t(
            running
              ? 'dpi_site_check.running'
              : service === 'custom'
                ? 'dpi_site_check.run_custom'
                : 'dpi_site_check.run',
          )}
        </Button>
        <Button
          disabled={running || !reports.length}
          onClick={() => setPreview(true)}
        >
          {t('dpi_site_check.preview')}
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
        <FrankShareButton
          disabled={running || !reports.length}
          load={() => ({
            blob: new Blob([buildDpiSiteCheckText(service, reports, t)], {
              type: 'text/plain;charset=utf-8',
            }),
            filename: `NFQWS2_SERVICE_${service}_${reports[0]?.started_at ?? 'partial'}.txt`,
          })}
        />
      </Stack>
      <Dialog
        open={preview}
        onClose={() => setPreview(false)}
        fullWidth
        maxWidth="lg"
        aria-labelledby="dpi-site-preview-title"
      >
        <DialogTitle id="dpi-site-preview-title">
          {t('dpi_site_check.preview')}
        </DialogTitle>
        <DialogContent dividers>
          <Typography
            component="pre"
            variant="body2"
            data-dpi-site-preview
            sx={{ m: 0, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}
          >
            {buildDpiSiteCheckText(service, reports, t)}
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPreview(false)}>
            {t('dpi_site_check.preview_close')}
          </Button>
        </DialogActions>
      </Dialog>
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
                  : error === 'invalid_request' && service === 'custom'
                    ? 'dpi_site_check.custom_invalid'
                    : error === 'download_failed'
                      ? 'dpi_site_check.download_failed'
                      : 'dpi_site_check.request_failed',
          )}
        </Alert>
      )}
      <Stack spacing={2} aria-live="polite">
        {reports.map((report) => {
          const r = report.response;
          const route =
            report.schema_version === 2 && report.operation === 'route';
          const network = report.schema_version === 2 ? report.network : null;
          const warning = route
            ? report.schema_version === 2 && report.addresses.length === 0
            : r.outcome !== 'response' ||
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
                {route ? (
                  dpiSiteResponseLabel(report, t)
                ) : (
                  <>
                    HTTP {r.http_status ?? '—'} —{' '}
                    {dpiSiteResponseLabel(report, t)}
                  </>
                )}
              </Alert>
              <Typography variant="caption">
                {t(`dpi_site_check.dns_${report.dns_scope}`)}
              </Typography>
              {report.schema_version === 2 && (
                <Stack spacing={1}>
                  <Typography variant="body2" sx={{ overflowWrap: 'anywhere' }}>
                    {t('dpi_site_check.resolved')}:{' '}
                    {report.addresses.join(', ') || '—'}
                  </Typography>
                  {report.kind === 'domain' && (
                    <Typography
                      variant="body2"
                      sx={{ overflowWrap: 'anywhere' }}
                    >
                      {t('dpi_site_check.dns_answer')}:{' '}
                      {report.dns.answers.join(', ') || '—'}; RCODE{' '}
                      {report.dns.rcode ?? '—'}
                    </Typography>
                  )}
                  <Typography variant="body2">
                    {t(`dpi_site_check.diagnosis_${dpiSiteDiagnosis(report)}`)}
                  </Typography>
                  <Typography variant="caption">
                    {t('dpi_site_check.diagnosis_limit')}
                  </Typography>
                </Stack>
              )}
              {network && (
                <Stack spacing={1}>
                  <Typography variant="caption">
                    {t('dpi_site_check.network_hint')}
                  </Typography>
                  {(['ping', 'route', 'trace'] as const).map((kind) => (
                    <Box key={kind}>
                      <Typography variant="subtitle2">
                        {t(`dpi_site_check.network_${kind}`)} —{' '}
                        {t(`dpi_site_check.network_${network[kind].state}`)}
                      </Typography>
                      {kind === 'trace' &&
                        dpiSiteTraceHops(network.trace.output).length > 0 && (
                          <TableContainer>
                            <Table
                              size="small"
                              aria-label={t('dpi_site_check.hops')}
                              sx={{
                                '& th, & td': { px: 1, py: 0.75, fontSize: 12 },
                              }}
                            >
                              <TableHead>
                                <TableRow>
                                  {(
                                    [
                                      'hop',
                                      'hop_ip',
                                      'hop_ms',
                                      'hop_reply',
                                    ] as const
                                  ).map((key) => (
                                    <TableCell key={key}>
                                      {t(`dpi_site_check.${key}`)}
                                    </TableCell>
                                  ))}
                                </TableRow>
                              </TableHead>
                              <TableBody>
                                {dpiSiteTraceHops(network.trace.output).map(
                                  (hop) => (
                                    <TableRow key={hop.hop}>
                                      <TableCell>{hop.hop}</TableCell>
                                      <TableCell sx={{ whiteSpace: 'nowrap' }}>
                                        {hop.addresses.join(', ') || '—'}
                                      </TableCell>
                                      <TableCell>
                                        {hop.times_ms.join(', ') || '—'}
                                      </TableCell>
                                      <TableCell>
                                        {hop.unanswered
                                          ? t('dpi_site_check.hop_no_reply')
                                          : t('dpi_site_check.hop_replied')}
                                        {hop.note && ` ${hop.note}`}
                                      </TableCell>
                                    </TableRow>
                                  ),
                                )}
                              </TableBody>
                            </Table>
                          </TableContainer>
                        )}
                      <Typography
                        component="pre"
                        variant="body2"
                        sx={{
                          m: 0,
                          p: 1,
                          bgcolor: 'action.hover',
                          whiteSpace: 'pre-wrap',
                          overflowWrap: 'anywhere',
                          maxHeight: 240,
                          overflow: 'auto',
                        }}
                      >
                        {network[kind].output || '—'}
                      </Typography>
                    </Box>
                  ))}
                </Stack>
              )}
              {!route && (
                <Typography variant="body2">
                  {t('dpi_site_check.bytes')}: {r.bytes_read};{' '}
                  {t('dpi_site_check.body_limited')}:{' '}
                  {t(
                    r.body_limited ? 'dpi_site_check.yes' : 'dpi_site_check.no',
                  )}
                </Typography>
              )}
              {!route && (
                <Typography variant="body2" sx={{ overflowWrap: 'anywhere' }}>
                  {t('dpi_site_check.redirect')}: {r.redirect ?? '—'}
                </Typography>
              )}
              <Typography variant="body2">
                {t('dpi_site_check.elapsed')}: {r.elapsed_ms ?? '—'}
                {!route && (
                  <>
                    ; {t('dpi_site_check.error_code')}: {r.error_code ?? '—'}
                  </>
                )}
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

import { useCallback, useEffect, useRef, useState } from 'react';
import type { TranslationKey } from '@/context/TranslationProvider';
import AccessTimeOutlinedIcon from '@mui/icons-material/AccessTimeOutlined';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import DnsOutlinedIcon from '@mui/icons-material/DnsOutlined';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import RefreshIcon from '@mui/icons-material/Refresh';
import RepeatIcon from '@mui/icons-material/Repeat';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Paper,
  Stack,
  Switch,
  Typography,
} from '@mui/material';

import { DpiError } from '@/api/dpiClient';
import {
  clearIpHealth,
  configureIpHealth,
  getIpHealthStatus,
  recheckIpHealth,
  removeIpHealth,
  type IpHealthStatus,
} from '@/api/ipHealthClient';

import { useStatus } from '@/hooks/useStatus';
import { useTranslation } from '@/hooks/useTranslation';

const runtimeCodes = new Set([
  'core_stopped',
  'socket_unavailable',
  'multiwan_unsupported',
  'queue_in_use',
  'clock_unavailable',
  'starting',
  'unavailable',
]);
const knownErrors = new Set([
  'timeout',
  'invalid_response',
  'unauthorized',
  'forbidden',
]);

export const IpHealthPanel = () => {
  const { csrfToken } = useStatus();
  const { t, langcode } = useTranslation();
  const [data, setData] = useState<IpHealthStatus>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [stale, setStale] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const inFlight = useRef(false);
  const mounted = useRef(false);
  const sessionGeneration = useRef(0);

  const load = useCallback(
    async (manual = false) => {
      if (!csrfToken || inFlight.current) return;
      const epoch = sessionGeneration.current;
      const current = () =>
        mounted.current && sessionGeneration.current === epoch;
      inFlight.current = true;
      setBusy(true);
      try {
        const next = await getIpHealthStatus(csrfToken);
        if (current()) {
          setData(next);
          setStale(false);
          // Polling must not erase a lost-action or stale-revision explanation.
          setError((previous) =>
            manual || !['action_unknown', 'stale_revision'].includes(previous)
              ? ''
              : previous,
          );
        }
      } catch (e) {
        if (current()) {
          setError(
            e instanceof DpiError && knownErrors.has(e.code)
              ? e.code
              : 'request_failed',
          );
          setStale(true);
        }
      } finally {
        if (current()) {
          inFlight.current = false;
          setBusy(false);
        }
      }
    },
    [csrfToken],
  );

  useEffect(() => {
    mounted.current = true;
    sessionGeneration.current++;
    inFlight.current = false;
    setBusy(false);
    setData(undefined);
    setError('');
    setStale(false);
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;
    let generation = 0;
    const poll = async (current = generation) => {
      if (
        stopped ||
        current !== generation ||
        document.visibilityState !== 'visible'
      )
        return;
      await load();
      if (
        !stopped &&
        current === generation &&
        document.visibilityState === 'visible'
      )
        timer = setTimeout(() => void poll(current), 5000);
    };
    const visibility = () => {
      generation++;
      clearTimeout(timer);
      if (document.visibilityState === 'visible') void poll();
    };
    void poll();
    document.addEventListener('visibilitychange', visibility);
    return () => {
      stopped = true;
      mounted.current = false;
      sessionGeneration.current++;
      clearTimeout(timer);
      document.removeEventListener('visibilitychange', visibility);
    };
  }, [load]);

  const action = async (
    operation: (csrf: string, revision: string) => Promise<IpHealthStatus>,
  ) => {
    if (!csrfToken || !data || inFlight.current) return;
    const epoch = sessionGeneration.current;
    const current = () =>
      mounted.current && sessionGeneration.current === epoch;
    inFlight.current = true;
    setBusy(true);
    setError('');
    try {
      const next = await operation(csrfToken, data.revision);
      if (current()) {
        setData(next);
        setStale(false);
      }
    } catch (e) {
      const code = e instanceof DpiError ? e.code : '';
      if (current())
        setError(
          code === 'stale_revision'
            ? code
            : knownErrors.has(code) &&
                ['unauthorized', 'forbidden'].includes(code)
              ? code
              : 'action_unknown',
        );
      // Reconcile once. The operation itself is never retried after an uncertain reply.
      if (!current()) return;
      try {
        const next = await getIpHealthStatus(csrfToken);
        if (current()) {
          setData(next);
          setStale(false);
        }
      } catch {
        if (current()) setStale(true);
      }
    } finally {
      if (current()) {
        inFlight.current = false;
        setBusy(false);
      }
    }
  };

  const runtime = !data?.enabled ? 'stopped' : data.runtime.state;
  const runtimeKey = !data?.enabled
    ? 'stopped'
    : runtime === 'active'
      ? 'active'
      : data?.runtime.code && runtimeCodes.has(data.runtime.code)
        ? data.runtime.code
        : runtime;
  const disabled = busy || !data || !csrfToken || stale;
  const dnsActive =
    data?.enabled &&
    data.runtime.state === 'active' &&
    data.runtime.dns === 'router_udp';
  const date = (value: number) =>
    new Intl.DateTimeFormat(langcode, {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(value * 1000);
  const remaining = (until: number) => {
    const seconds = until - Math.floor(Date.now() / 1000);
    if (seconds <= 0) return t('ip_health.expired');
    const unit = seconds >= 86400 ? 'day' : seconds >= 3600 ? 'hour' : 'minute';
    const size = unit === 'day' ? 86400 : unit === 'hour' ? 3600 : 60;
    return new Intl.NumberFormat(langcode, {
      style: 'unit',
      unit,
      unitDisplay: 'long',
    }).format(Math.ceil(seconds / size));
  };
  const panel = {
    borderRadius: '10px',
    border: '1px solid',
    borderColor: 'divider',
    overflow: 'hidden',
  };
  const heading = { fontSize: 15, fontWeight: 600 };
  const caption = { fontSize: 11, color: 'text.secondary' };
  return (
    <Box
      component="main"
      aria-busy={busy}
      sx={{
        position: 'absolute',
        inset: 0,
        overflowY: 'auto',
        p: { xs: 2, sm: 3 },
      }}
    >
      <Stack spacing={2} sx={{ maxWidth: 1000, mx: 'auto', minWidth: 0 }}>
        <Box>
          <Stack
            direction="row"
            justifyContent="space-between"
            alignItems="center"
            gap={1}
            flexWrap="wrap"
          >
            <Typography
              component="h1"
              sx={{
                fontSize: { xs: 25, sm: 27 },
                fontWeight: 600,
                letterSpacing: '-.5px',
              }}
            >
              {t('ip_health.title')}
            </Typography>
            <Button
              size="small"
              startIcon={<RefreshIcon />}
              disabled={busy || !csrfToken}
              onClick={() => void load(true)}
            >
              {t('ip_health.refresh')}
            </Button>
          </Stack>
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ mt: 1, fontSize: 13 }}
          >
            {t('ip_health.intro')}
          </Typography>
        </Box>
        {error && (
          <Alert severity="warning">
            {t(`ip_health.errors.${error}` as TranslationKey)}
          </Alert>
        )}
        {stale && data && (
          <Typography variant="body2" color="warning.main" role="status">
            {t('ip_health.last_known')}
          </Typography>
        )}
        {!data && !error && (
          <Stack direction="row" spacing={1} alignItems="center" role="status">
            <CircularProgress size={18} />
            <Typography variant="body2">
              {t(csrfToken ? 'ip_health.loading' : 'ip_health.auth_wait')}
            </Typography>
          </Stack>
        )}
        <Paper
          elevation={0}
          sx={panel}
          component="section"
          aria-labelledby="ip-health-toggle-title"
        >
          <Stack
            direction="row"
            alignItems="flex-start"
            justifyContent="space-between"
            gap={1}
            sx={{ p: { xs: 2, sm: 2.5 } }}
          >
            <Box sx={{ minWidth: 0 }}>
              <Typography
                component="h2"
                id="ip-health-toggle-title"
                sx={heading}
              >
                {t('ip_health.toggle')}
              </Typography>
              <Typography
                variant="body2"
                color="text.secondary"
                sx={{ mt: 0.5, fontSize: 12 }}
              >
                {t('ip_health.toggle_help')}
              </Typography>
            </Box>
            <Stack
              direction="row"
              alignItems="center"
              spacing={0.5}
              sx={{ flexShrink: 0 }}
            >
              {data && (
                <Typography
                  sx={{ ...caption, display: { xs: 'none', sm: 'block' } }}
                >
                  {t(data.enabled ? 'ip_health.enabled' : 'ip_health.disabled')}
                </Typography>
              )}
              <Switch
                checked={data?.enabled ?? false}
                disabled={disabled}
                slotProps={{
                  input: {
                    role: 'switch',
                    'aria-labelledby': 'ip-health-toggle-title',
                  },
                }}
                onChange={(_, checked) =>
                  void action((csrf, revision) =>
                    configureIpHealth(csrf, checked, revision),
                  )
                }
              />
            </Stack>
          </Stack>
          <Box
            sx={{
              mx: { xs: 2, sm: 2.5 },
              mb: 2,
              pt: 2,
              borderTop: '1px solid',
              borderColor: 'divider',
              display: 'grid',
              gridTemplateColumns: { xs: '1fr 1fr', sm: '1fr 1fr 1.3fr' },
              gap: 2,
            }}
          >
            {[
              {
                icon: <AccessTimeOutlinedIcon fontSize="small" />,
                title: 'first_duration',
                help: 'first_help',
              },
              {
                icon: <RepeatIcon fontSize="small" />,
                title: 'repeat_duration',
                help: 'repeat_help',
              },
              {
                icon: <RefreshIcon fontSize="small" />,
                title: 'auto_check',
                help: 'auto_help',
              },
            ].map((item, index) => (
              <Stack
                key={item.title}
                direction="row"
                gap={1}
                sx={{
                  gridColumn: {
                    xs: index === 2 ? '1 / -1' : 'auto',
                    sm: 'auto',
                  },
                }}
              >
                <Box color="primary.main">{item.icon}</Box>
                <Box>
                  <Typography sx={{ fontSize: 13, fontWeight: 600 }}>
                    {t(`ip_health.${item.title}` as TranslationKey)}
                  </Typography>
                  <Typography sx={{ ...caption, mt: 0.25 }}>
                    {t(`ip_health.${item.help}` as TranslationKey)}
                  </Typography>
                </Box>
              </Stack>
            ))}
          </Box>
          <Stack
            direction="row"
            gap={1}
            sx={{
              px: { xs: 2, sm: 2.5 },
              py: 1.25,
              borderTop: '1px solid',
              borderColor: 'divider',
              bgcolor: 'action.hover',
            }}
          >
            <InfoOutlinedIcon
              sx={{ fontSize: 16, mt: 0.2, color: 'text.secondary' }}
            />
            <Typography
              sx={{
                fontSize: 12,
                color:
                  data?.enabled === false ? 'warning.main' : 'text.secondary',
              }}
            >
              {t(
                data?.enabled === false
                  ? 'ip_health.disabled_note'
                  : 'ip_health.evidence_note',
              )}
            </Typography>
          </Stack>
        </Paper>
        {data && (
          <Box role="status">
            <Chip
              size="small"
              color={
                runtime === 'active' && !stale
                  ? 'success'
                  : runtime === 'unavailable'
                    ? 'warning'
                    : 'default'
              }
              variant="outlined"
              label={t(`ip_health.runtime.${runtimeKey}` as TranslationKey)}
              sx={{
                height: 'auto',
                py: 0.5,
                maxWidth: '100%',
                '& .MuiChip-label': { whiteSpace: 'normal' },
              }}
            />
          </Box>
        )}
        <Paper
          elevation={0}
          component="section"
          aria-labelledby="ip-health-dns-title"
          sx={{ ...panel, display: 'flex', gap: 1.5, p: 2 }}
        >
          <DnsOutlinedIcon color="primary" fontSize="small" sx={{ mt: 0.25 }} />
          <Box sx={{ minWidth: 0 }}>
            <Stack direction="row" gap={1} alignItems="center" flexWrap="wrap">
              <Typography
                component="h2"
                id="ip-health-dns-title"
                sx={{ ...heading, fontSize: 13 }}
              >
                {t('ip_health.dns_title')}
              </Typography>
              <Chip
                size="small"
                label={t('ip_health.dns_scope')}
                variant="outlined"
                sx={{ height: 21, fontSize: 10 }}
              />
            </Stack>
            {data && (
              <Typography sx={{ ...caption, mt: 0.75 }}>
                {t(
                  dnsActive
                    ? 'ip_health.dns_available'
                    : 'ip_health.dns_unavailable',
                )}
              </Typography>
            )}
            <Typography sx={{ ...caption, mt: 0.5, lineHeight: 1.65 }}>
              {t('ip_health.dns_limit')}
            </Typography>
          </Box>
        </Paper>
        {data && (
          <Paper
            component="section"
            elevation={0}
            aria-labelledby="ip-health-saved-title"
            sx={{
              ...panel,
              bgcolor: { xs: 'transparent', md: 'background.paper' },
              border: { xs: 0, md: '1px solid' },
              borderColor: { md: 'divider' },
            }}
          >
            <Stack
              direction="row"
              justifyContent="space-between"
              alignItems="center"
              gap={1}
              flexWrap="wrap"
              sx={{ px: { xs: 0, md: 2.5 }, py: 2 }}
            >
              <Stack direction="row" alignItems="center" gap={1}>
                <Typography
                  component="h2"
                  id="ip-health-saved-title"
                  sx={heading}
                >
                  {t('ip_health.saved')}
                </Typography>
                <Chip
                  size="small"
                  label={data.entries.length}
                  sx={{ height: 22 }}
                />
              </Stack>
              <Stack direction="row" gap={0.5} flexWrap="wrap">
                <Button
                  size="small"
                  startIcon={<RefreshIcon />}
                  disabled={
                    disabled ||
                    !data.enabled ||
                    runtime !== 'active' ||
                    !data.entries.length
                  }
                  onClick={() =>
                    void action((csrf, revision) =>
                      recheckIpHealth(csrf, 'all', revision),
                    )
                  }
                >
                  {t('ip_health.recheck_all')}
                </Button>
                <Button
                  size="small"
                  startIcon={<DeleteOutlineIcon />}
                  disabled={disabled || !data.entries.length}
                  onClick={() => setConfirmClear(true)}
                >
                  {t('ip_health.clear')}
                </Button>
              </Stack>
            </Stack>
            {data.entries.length === 0 ? (
              <Stack
                spacing={1}
                alignItems="center"
                sx={{
                  p: 4,
                  borderTop: '1px solid',
                  borderColor: 'divider',
                  textAlign: 'center',
                  bgcolor: 'background.paper',
                }}
              >
                <Typography sx={heading}>{t('ip_health.empty')}</Typography>
                <Typography variant="body2" color="text.secondary">
                  {t('ip_health.empty_help')}
                </Typography>
              </Stack>
            ) : (
              <Box
                component="table"
                sx={{
                  width: '100%',
                  borderCollapse: 'collapse',
                  tableLayout: 'fixed',
                  textAlign: 'left',
                  display: { xs: 'block', md: 'table' },
                }}
              >
                <Box
                  component="thead"
                  sx={{
                    display: { xs: 'none', md: 'table-header-group' },
                    bgcolor: 'action.hover',
                  }}
                >
                  <Box component="tr">
                    {['address', 'protocol', 'remaining', 'actions'].map(
                      (key) => (
                        <Box
                          key={key}
                          component="th"
                          scope="col"
                          sx={{
                            ...caption,
                            width:
                              key === 'actions'
                                ? '29%'
                                : key === 'address'
                                  ? '27%'
                                  : '22%',
                            fontWeight: 500,
                            px: 2.5,
                            py: 1,
                            borderTop: '1px solid',
                            borderBottom: '1px solid',
                            borderColor: 'divider',
                          }}
                        >
                          {t(`ip_health.${key}` as TranslationKey)}
                        </Box>
                      ),
                    )}
                  </Box>
                </Box>
                <Box
                  component="tbody"
                  sx={{
                    display: { xs: 'grid', md: 'table-row-group' },
                    gap: 1.5,
                  }}
                >
                  {data.entries.map((entry) => (
                    <Box
                      component="tr"
                      key={entry.id}
                      sx={{
                        display: { xs: 'grid', md: 'table-row' },
                        gridTemplateColumns: '1fr 1fr',
                        border: { xs: '1px solid', md: 0 },
                        borderColor: { xs: 'divider' },
                        borderRadius: { xs: '9px', md: 0 },
                        overflow: 'hidden',
                        bgcolor: 'background.paper',
                        '& td': {
                          borderBottom: { md: '1px solid' },
                          borderColor: { md: 'divider' },
                          verticalAlign: 'middle',
                        },
                      }}
                    >
                      <Box
                        component="td"
                        sx={{
                          gridColumn: '1 / -1',
                          px: { xs: 1.75, md: 2.5 },
                          py: 1.75,
                          borderBottom: { xs: '1px solid' },
                          borderBottomColor: { xs: 'divider' },
                          minWidth: 0,
                        }}
                      >
                        <Typography
                          sx={{
                            fontFamily: 'monospace',
                            fontSize: 13,
                            overflowWrap: 'anywhere',
                          }}
                        >
                          {entry.ip}
                        </Typography>
                        <Typography
                          sx={{ ...caption, mt: 0.5, overflowWrap: 'anywhere' }}
                        >
                          {entry.host || t('ip_health.unknown_host')}
                        </Typography>
                      </Box>
                      <Box
                        component="td"
                        sx={{ px: { xs: 1.75, md: 2.5 }, py: 1.5, minWidth: 0 }}
                      >
                        <Typography
                          sx={{
                            ...caption,
                            fontSize: 10,
                            mb: 0.75,
                            display: { md: 'none' },
                          }}
                        >
                          {t('ip_health.protocol')}
                        </Typography>
                        <Stack direction="row" gap={0.5} flexWrap="wrap">
                          {['TCP 443', 'UDP 443'].map((protocol) => (
                            <Chip
                              key={protocol}
                              label={protocol}
                              size="small"
                              variant="outlined"
                              sx={{
                                fontSize: 10,
                                height: 23,
                                '& .MuiChip-label': { px: 0.75 },
                              }}
                            />
                          ))}
                        </Stack>
                      </Box>
                      <Box
                        component="td"
                        sx={{ px: { xs: 1.75, md: 2.5 }, py: 1.5, minWidth: 0 }}
                      >
                        <Typography
                          sx={{
                            ...caption,
                            fontSize: 10,
                            mb: 0.75,
                            display: { md: 'none' },
                          }}
                        >
                          {t('ip_health.remaining')}
                        </Typography>
                        <Typography
                          sx={{ fontSize: 13 }}
                          title={`${t('ip_health.until')} ${date(entry.until)}`}
                        >
                          {remaining(entry.until)}
                        </Typography>
                        <Typography sx={{ ...caption, fontSize: 10, mt: 0.5 }}>
                          {t(
                            entry.incident === 1
                              ? 'ip_health.first_incident'
                              : 'ip_health.repeat_incident',
                          )}
                        </Typography>
                        <Typography
                          data-check-state={entry.check_state}
                          sx={{ ...caption, fontSize: 10, mt: 0.5 }}
                          title={
                            entry.last_check === null
                              ? t('ip_health.never_checked')
                              : `${t('ip_health.last_check')}: ${date(entry.last_check)}`
                          }
                        >
                          {t(`ip_health.check.${entry.check_state}`)}
                        </Typography>
                      </Box>
                      <Box
                        component="td"
                        sx={{
                          gridColumn: '1 / -1',
                          px: { xs: 1.75, md: 1 },
                          py: 1,
                          bgcolor: { xs: 'action.hover', md: 'transparent' },
                          borderTop: { xs: '1px solid', md: 0 },
                          borderTopColor: { xs: 'divider' },
                        }}
                      >
                        <Stack
                          direction="row"
                          gap={0.5}
                          alignItems="center"
                          flexWrap="wrap"
                        >
                          <Button
                            size="small"
                            variant="outlined"
                            startIcon={
                              <RefreshIcon
                                sx={{ fontSize: '14px !important' }}
                              />
                            }
                            aria-label={`${t('ip_health.recheck')} ${entry.ip}`}
                            disabled={
                              disabled ||
                              !data.enabled ||
                              runtime !== 'active' ||
                              entry.check_state === 'checking'
                            }
                            onClick={() =>
                              void action((csrf, revision) =>
                                recheckIpHealth(csrf, entry.id, revision),
                              )
                            }
                            sx={{ fontSize: 11 }}
                          >
                            {t('ip_health.recheck')}
                          </Button>
                          <Button
                            size="small"
                            aria-label={`${t('ip_health.remove')} ${entry.ip}`}
                            disabled={disabled}
                            onClick={() =>
                              void action((csrf, revision) =>
                                removeIpHealth(csrf, entry.id, revision),
                              )
                            }
                            sx={{ fontSize: 11, ml: { xs: 'auto', md: 0 } }}
                          >
                            {t('ip_health.remove')}
                          </Button>
                        </Stack>
                      </Box>
                    </Box>
                  ))}
                </Box>
              </Box>
            )}
            <Stack
              direction="row"
              gap={1}
              sx={{ px: { xs: 0.25, md: 2.5 }, pt: 1.5, pb: 1.5 }}
            >
              <RefreshIcon
                sx={{ fontSize: 15, mt: 0.2, color: 'text.secondary' }}
              />
              <Typography sx={{ ...caption, lineHeight: 1.6 }}>
                {t('ip_health.list_note')}
              </Typography>
            </Stack>
          </Paper>
        )}
      </Stack>
      <Dialog
        open={confirmClear}
        onClose={() => setConfirmClear(false)}
        aria-labelledby="ip-health-clear-title"
      >
        <DialogTitle id="ip-health-clear-title">
          {t('ip_health.clear_title')}
        </DialogTitle>
        <DialogContent>
          <DialogContentText>{t('ip_health.clear_help')}</DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button autoFocus onClick={() => setConfirmClear(false)}>
            {t('ip_health.cancel')}
          </Button>
          <Button
            disabled={disabled}
            onClick={() => {
              setConfirmClear(false);
              void action(clearIpHealth);
            }}
          >
            {t('ip_health.confirm_clear')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

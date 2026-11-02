import { useEffect, useRef, useState } from 'react';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  FormControlLabel,
  IconButton,
  LinearProgress,
  Radio,
  RadioGroup,
  Stack,
  Switch,
  TextField,
  Tooltip,
} from '@mui/material';

import { API } from '@/api/client';
import {
  RestartScheduleError,
  restartScheduleRequest,
  validRestartHours,
} from '@/api/restartSchedule';

import { LoginDialog } from '@/components/LoginDialog';

import { useAppStore } from '@/store/useAppStore';

import { useTranslation } from '@/hooks/useTranslation';

export const RestartScheduleDialog = ({
  csrfToken,
  onClose,
}: {
  csrfToken?: string;
  onClose: VoidFunction;
}) => {
  const { t } = useTranslation();
  const status = API.status();
  const { auth } = useAppStore();
  const [selection, setSelection] = useState('off');
  const [hours, setHours] = useState('24');
  const [savedHours, setSavedHours] = useState(24);
  const [watchdog, setWatchdog] = useState(false);
  const [schedulerAvailable, setSchedulerAvailable] = useState(true);
  const [lockedAttempts, setLockedAttempts] = useState<number | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [reading, setReading] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [recovering, setRecovering] = useState(false);
  const [loginOpen, setLoginOpen] = useState(false);
  const request = useRef<AbortController | null>(null);
  const dirty = useRef(false);
  const mounted = useRef(true);
  const recoveryInFlight = useRef(false);
  const sessionAvailable =
    !status.isError &&
    status.data?.status === 0 &&
    ((status.data.authenticated ?? !status.data.anonym) || status.data.anonym);
  const statusToken = status.data?.csrf_token;
  const sessionError = error === 'auth_required' || error === 'csrf_failed';
  const working = pending || recovering;
  const valid = selection !== 'custom' || validRestartHours(hours);
  const errorMessage =
    error === 'busy'
      ? t('restart_schedule.busy')
      : error === 'unsupported_scheduler'
        ? t('restart_schedule.unsupported')
        : error === 'auth_required'
          ? t('restart_schedule.session')
          : error === 'csrf_failed'
            ? t('restart_schedule.csrf')
            : t('restart_schedule.request_failed');

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      request.current?.abort();
    };
  }, []);

  useEffect(() => {
    // A rejected login also activates the App's global sign-in dialog. Hand
    // ownership to that dialog so local sign-in cannot reappear after success.
    if (auth === false) setLoginOpen(false);
  }, [auth]);

  useEffect(() => {
    setPending(false);
    setReading(false);
    // Both login modes use the token from a successful current status response.
    if (!csrfToken || !sessionAvailable || statusToken !== csrfToken) return;
    const controller = new AbortController();
    request.current = controller;
    setReading(true);
    restartScheduleRequest(csrfToken, controller.signal)
      .then((schedule) => {
        if (controller.signal.aborted) return;
        if (!dirty.current) {
          setHours(String(schedule.interval_hours));
          setWatchdog(schedule.watchdog_enabled);
          setSelection(
            !schedule.enabled
              ? 'off'
              : [4, 12, 24].includes(schedule.interval_hours)
                ? String(schedule.interval_hours)
                : 'custom',
          );
        }
        setSavedHours(schedule.interval_hours);
        setSchedulerAvailable(schedule.scheduler_available);
        setLockedAttempts(
          schedule.watchdog_state === 'locked'
            ? schedule.watchdog_attempts
            : null,
        );
        setLoaded(true);
        setError('');
      })
      .catch((error) => {
        if (!controller.signal.aborted)
          setError(
            error instanceof RestartScheduleError
              ? error.code
              : 'request_failed',
          );
      })
      .finally(() => {
        if (request.current === controller) {
          request.current = null;
          if (!controller.signal.aborted) setReading(false);
        }
      });
    return () => {
      controller.abort();
      request.current?.abort();
    };
  }, [csrfToken, sessionAvailable, statusToken, attempt]);

  const recoverSession = async () => {
    if (recoveryInFlight.current) return;
    recoveryInFlight.current = true;
    setRecovering(true);
    try {
      const fresh = await status.refetch();
      if (!mounted.current) return;
      if (fresh.error || !fresh.data || fresh.data.status !== 0) {
        // The App already supplies its global login on an actual status401.
        setError(
          useAppStore.getState().auth === false
            ? 'auth_required'
            : 'request_failed',
        );
        return;
      }
      if (
        !(fresh.data.authenticated ?? !fresh.data.anonym) &&
        !fresh.data.anonym
      ) {
        setError('auth_required');
        setLoginOpen(true);
        return;
      }
      setLoginOpen(false);
      setError('');
      // A changed token triggers the read effect itself. Never start a read
      // with the old token while the refreshed status is being rendered.
      if (!loaded && fresh.data.csrf_token === csrfToken)
        setAttempt((value) => value + 1);
    } catch {
      if (mounted.current) setError('request_failed');
    } finally {
      recoveryInFlight.current = false;
      if (mounted.current) setRecovering(false);
    }
  };

  const save = async () => {
    if (
      request.current ||
      !csrfToken ||
      !loaded ||
      !valid ||
      sessionError ||
      recovering ||
      !sessionAvailable ||
      statusToken !== csrfToken
    )
      return;
    const controller = new AbortController();
    request.current = controller;
    setPending(true);
    setError('');
    try {
      await restartScheduleRequest(csrfToken, controller.signal, {
        enabled: selection !== 'off',
        interval_hours: Number(
          selection === 'off'
            ? savedHours
            : selection === 'custom'
              ? hours
              : selection,
        ),
        watchdog_enabled: watchdog,
      });
      if (!controller.signal.aborted) onClose();
    } catch (error) {
      if (!controller.signal.aborted)
        setError(
          error instanceof RestartScheduleError ? error.code : 'request_failed',
        );
    } finally {
      if (!controller.signal.aborted) setPending(false);
      if (request.current === controller) request.current = null;
    }
  };

  return (
    <>
      <Dialog
        open
        onClose={() => {
          if (!pending) onClose();
        }}
        maxWidth="xs"
        fullWidth
        aria-labelledby="restart-schedule-title"
        aria-describedby="restart-schedule-description"
        slotProps={{ paper: { sx: { m: 2, width: 'calc(100% - 32px)' } } }}
      >
        <DialogTitle id="restart-schedule-title" sx={{ pb: 1 }}>
          {t('restart_schedule.title')}
        </DialogTitle>
        {((!loaded && !error) || working) && (
          <LinearProgress aria-label={t('restart_schedule.loading')} />
        )}
        <DialogContent sx={{ pt: 1 }}>
          <DialogContentText
            id="restart-schedule-description"
            sx={{ mb: 1.5, fontSize: 14 }}
          >
            {t('restart_schedule.description')}
          </DialogContentText>
          <RadioGroup
            aria-label={t('restart_schedule.interval')}
            value={selection}
            onChange={(event) => {
              dirty.current = true;
              setSelection(event.target.value);
            }}
          >
            <FormControlLabel
              value="off"
              control={<Radio size="small" />}
              label={t('restart_schedule.off')}
              disabled={!loaded || working}
            />
            {[4, 12, 24].map((value) => (
              <FormControlLabel
                key={value}
                value={String(value)}
                control={<Radio size="small" />}
                label={t('restart_schedule.every', { hours: value })}
                disabled={!loaded || working}
              />
            ))}
            <FormControlLabel
              value="custom"
              control={<Radio size="small" />}
              label={t('restart_schedule.custom')}
              disabled={!loaded || working}
            />
          </RadioGroup>
          {selection === 'custom' && (
            <TextField
              fullWidth
              size="small"
              type="number"
              label={t('restart_schedule.hours')}
              value={hours}
              onChange={(event) => {
                dirty.current = true;
                setHours(event.target.value);
              }}
              disabled={!loaded || working}
              error={!valid}
              helperText={
                valid
                  ? t('restart_schedule.range')
                  : t('restart_schedule.invalid')
              }
              slotProps={{
                htmlInput: { min: 1, max: 168, step: 1, inputMode: 'numeric' },
              }}
              sx={{ mt: 1, mb: 0.5 }}
            />
          )}
          <DialogContentText sx={{ mt: 1.5, fontSize: 13 }}>
            {t('restart_schedule.running_only')}
          </DialogContentText>
          <Stack direction="row" alignItems="center" sx={{ mt: 1.5 }}>
            <FormControlLabel
              control={
                <Switch
                  size="small"
                  checked={watchdog}
                  onChange={(event) => {
                    dirty.current = true;
                    setWatchdog(event.target.checked);
                  }}
                  slotProps={{ input: { role: 'switch' } }}
                />
              }
              label={t('restart_schedule.watchdog')}
              disabled={!loaded || working}
              sx={{ flex: 1, mr: 0 }}
            />
            <Tooltip
              title={t('restart_schedule.watchdog_tooltip')}
              enterTouchDelay={0}
            >
              <IconButton
                size="small"
                aria-label={t('restart_schedule.watchdog_help')}
              >
                <HelpOutlineIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Stack>
          {lockedAttempts !== null && (
            <Alert severity="warning" sx={{ mt: 1 }}>
              {t('restart_schedule.watchdog_locked', {
                attempts: lockedAttempts,
              })}
            </Alert>
          )}
          {!schedulerAvailable && (
            <Alert severity="warning" sx={{ mt: 1 }}>
              {t('restart_schedule.scheduler_unavailable')}
            </Alert>
          )}
          {error && (
            <Alert
              severity="error"
              sx={{ mt: 1.5 }}
              action={
                sessionError ? (
                  <Button
                    color="inherit"
                    size="small"
                    disabled={working}
                    onClick={() => void recoverSession()}
                  >
                    {t('restart_schedule.recover')}
                  </Button>
                ) : (
                  !loaded && (
                    <Button
                      color="inherit"
                      size="small"
                      onClick={() => {
                        setError('');
                        setAttempt((value) => value + 1);
                      }}
                    >
                      {t('restart_schedule.retry')}
                    </Button>
                  )
                )
              }
            >
              {errorMessage}
            </Alert>
          )}
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={onClose} disabled={pending}>
            {t('common.cancel')}
          </Button>
          <Button
            variant="contained"
            onClick={() => void save()}
            disabled={
              !loaded ||
              reading ||
              working ||
              !valid ||
              sessionError ||
              !csrfToken ||
              !sessionAvailable ||
              statusToken !== csrfToken
            }
          >
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>
      {loginOpen && auth !== false && (
        <LoginDialog
          onSuccess={recoverSession}
          onCancel={() => setLoginOpen(false)}
        />
      )}
    </>
  );
};

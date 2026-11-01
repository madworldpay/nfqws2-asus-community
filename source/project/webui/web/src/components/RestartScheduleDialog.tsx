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

import {
  RestartScheduleError,
  restartScheduleRequest,
  validRestartHours,
} from '@/api/restartSchedule';

import { useTranslation } from '@/hooks/useTranslation';

export const RestartScheduleDialog = ({
  csrfToken,
  onClose,
}: {
  csrfToken: string;
  onClose: VoidFunction;
}) => {
  const { t } = useTranslation();
  const [selection, setSelection] = useState('off');
  const [hours, setHours] = useState('24');
  const [savedHours, setSavedHours] = useState(24);
  const [watchdog, setWatchdog] = useState(false);
  const [schedulerAvailable, setSchedulerAvailable] = useState(true);
  const [lockedAttempts, setLockedAttempts] = useState<number | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const request = useRef<AbortController | null>(null);
  const valid = selection !== 'custom' || validRestartHours(hours);
  const errorMessage =
    error === 'busy'
      ? t('restart_schedule.busy')
      : error === 'unsupported_scheduler'
        ? t('restart_schedule.unsupported')
        : error === 'session'
          ? t('restart_schedule.session')
          : t('restart_schedule.request_failed');

  useEffect(() => {
    const controller = new AbortController();
    request.current = controller;
    restartScheduleRequest(csrfToken, controller.signal)
      .then((schedule) => {
        if (controller.signal.aborted) return;
        setHours(String(schedule.interval_hours));
        setSavedHours(schedule.interval_hours);
        setWatchdog(schedule.watchdog_enabled);
        setSchedulerAvailable(schedule.scheduler_available);
        setLockedAttempts(
          schedule.watchdog_state === 'locked'
            ? schedule.watchdog_attempts
            : null,
        );
        setSelection(
          !schedule.enabled
            ? 'off'
            : [4, 12, 24].includes(schedule.interval_hours)
              ? String(schedule.interval_hours)
              : 'custom',
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
        if (request.current === controller) request.current = null;
      });
    return () => {
      controller.abort();
      request.current?.abort();
    };
  }, [csrfToken, attempt]);

  const save = async () => {
    if (request.current || !loaded || !valid) return;
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
      {((!loaded && !error) || pending) && (
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
          onChange={(event) => setSelection(event.target.value)}
        >
          <FormControlLabel
            value="off"
            control={<Radio size="small" />}
            label={t('restart_schedule.off')}
            disabled={!loaded || pending}
          />
          {[4, 12, 24].map((value) => (
            <FormControlLabel
              key={value}
              value={String(value)}
              control={<Radio size="small" />}
              label={t('restart_schedule.every', { hours: value })}
              disabled={!loaded || pending}
            />
          ))}
          <FormControlLabel
            value="custom"
            control={<Radio size="small" />}
            label={t('restart_schedule.custom')}
            disabled={!loaded || pending}
          />
        </RadioGroup>
        {selection === 'custom' && (
          <TextField
            fullWidth
            size="small"
            type="number"
            label={t('restart_schedule.hours')}
            value={hours}
            onChange={(event) => setHours(event.target.value)}
            disabled={!loaded || pending}
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
                onChange={(event) => setWatchdog(event.target.checked)}
                slotProps={{ input: { role: 'switch' } }}
              />
            }
            label={t('restart_schedule.watchdog')}
            disabled={!loaded || pending}
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
          disabled={!loaded || pending || !valid}
        >
          {t('common.save')}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

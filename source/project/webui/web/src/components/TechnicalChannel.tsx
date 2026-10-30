import { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
  Typography,
} from '@mui/material';

import { ShareError } from '@/api/shareClient';
import {
  technicalRequest,
  type TechnicalState,
} from '@/api/technicalChannelClient';

import { InlineHelp } from '@/components/InlineHelp';

import { useStatus } from '@/hooks/useStatus';
import { useTranslation } from '@/hooks/useTranslation';

const idle: TechnicalState = {
  state: 'idle',
  session_id: null,
  expires_at: null,
  code: null,
};
export const TechnicalChannel = () => {
  const { t, langcode } = useTranslation();
  const { csrfToken, anonym } = useStatus();
  const [open, setOpen] = useState(false);
  const [invitation, setInvitation] = useState('');
  const [state, setState] = useState<TechnicalState>(idle);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const active = state.state === 'connecting' || state.state === 'connected';
  const refresh = useCallback(async () => {
    if (!csrfToken || anonym) return;
    try {
      setState(await technicalRequest(csrfToken, 'technicalstatus'));
      setError(null);
    } catch (e) {
      setError(e instanceof ShareError ? e.code : 'connection_failed');
    }
  }, [csrfToken, anonym]);
  useEffect(() => {
    void refresh();
  }, [refresh]);
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => {
      void refresh();
    }, 2000);
    return () => window.clearInterval(timer);
  }, [active, refresh]);
  const close = () => {
    setOpen(false);
    setInvitation('');
  };
  const action = async (cmd: 'technicalstart' | 'technicalstop') => {
    if (!csrfToken || busy) return;
    const link = invitation;
    setInvitation('');
    setBusy(true);
    setError(null);
    try {
      setState(await technicalRequest(csrfToken, cmd, link));
    } catch (e) {
      setError(e instanceof ShareError ? e.code : 'connection_failed');
    } finally {
      setBusy(false);
    }
  };
  const labels = {
    idle: t('technical.idle'),
    connecting: t('technical.connecting'),
    connected: t('technical.connected'),
    stopped: t('technical.stopped'),
    expired: t('technical.expired'),
    failed: t('technical.failed'),
  };
  const messages: Record<string, string> = {
    auth_required: t('technical.auth_required'),
    invalid_invitation: t('technical.invalid_invitation'),
    key_conflict: t('technical.key_conflict'),
    unsafe_key_file: t('technical.unsafe_key_file'),
    unsupported_runtime: t('technical.unsupported_runtime'),
    root_required: t('technical.unsupported_runtime'),
    busy: t('technical.busy'),
    expired: t('technical.expired'),
    interrupted: t('technical.interrupted'),
  };
  const problem = error ?? state.code;
  return (
    <>
      <Box
        sx={{
          px: 'max(15px, 1.6vh)',
          py: 0.5,
          display: 'flex',
          alignItems: 'center',
          gap: 0.5,
          flexWrap: 'wrap',
        }}
      >
        <Button
          size="small"
          color="inherit"
          sx={{ color: 'text.secondary', textTransform: 'none', fontSize: 12 }}
          onClick={() => {
            setOpen(true);
            void refresh();
          }}
        >
          {t('technical.title')}
        </Button>
        <InlineHelp title={t('technical.help_title')}>
          <Stack spacing={1}>
            {[
              'arrangement',
              'invitation_help',
              'not_support',
              'not_request',
              'disconnect_help',
            ].map((key) => (
              <Typography key={key}>
                {t(`technical.${key}` as 'technical.arrangement')}
              </Typography>
            ))}
          </Stack>
        </InlineHelp>
        {active && (
          <Typography variant="caption" color="text.secondary">
            {labels[state.state]}
          </Typography>
        )}
      </Box>
      <Dialog open={open} fullWidth maxWidth="sm" onClose={close}>
        <DialogTitle>{t('technical.title')}</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2}>
            <Typography>{t('technical.arrangement')}</Typography>
            <Typography variant="body2" color="text.secondary">
              {t('technical.access')}
            </Typography>
            <Typography role="status">{labels[state.state]}</Typography>
            {state.expires_at !== null && (
              <Typography variant="body2">
                {t('technical.deadline', {
                  time: new Date(state.expires_at * 1000).toLocaleString(
                    langcode === 'en' ? 'en-GB' : 'ru-RU',
                  ),
                })}
              </Typography>
            )}
            {(anonym || problem) && (
              <Alert severity="warning">
                {anonym
                  ? messages.auth_required
                  : (messages[problem ?? ''] ??
                    t('technical.connection_failed'))}
              </Alert>
            )}
            {!active && (
              <TextField
                label={t('technical.link')}
                value={invitation}
                onChange={(e) => setInvitation(e.target.value)}
                multiline
                minRows={2}
                autoComplete="off"
                spellCheck={false}
                disabled={busy || anonym}
                slotProps={{ htmlInput: { maxLength: 16384 } }}
                helperText={t('technical.link_hint')}
              />
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={close}>{t('common.close')}</Button>
          {active ? (
            <Button
              disabled={busy || anonym}
              color="error"
              onClick={() => void action('technicalstop')}
            >
              {t('technical.disconnect')}
            </Button>
          ) : (
            <Button
              disabled={busy || anonym || !csrfToken || !invitation.trim()}
              onClick={() => void action('technicalstart')}
            >
              {t('technical.connect')}
            </Button>
          )}
        </DialogActions>
      </Dialog>
    </>
  );
};

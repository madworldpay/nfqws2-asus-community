import { useEffect, useRef, useState, type FormEvent } from 'react';
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  TextField,
} from '@mui/material';

import { API } from '@/api/client';

import { useTranslation } from '@/hooks/useTranslation';

export const LoginDialog = ({
  onSuccess,
  onCancel,
}: {
  onSuccess?: () => void | Promise<void>;
  onCancel?: VoidFunction;
} = {}) => {
  const [user, setUser] = useState('');
  const [password, setPassword] = useState('');
  const [loginError, setLoginError] = useState(false);
  const [pending, setPending] = useState(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const { t } = useTranslation();

  const handleLogin = async () => {
    if (!user || !password || pending) {
      return;
    }

    setLoginError(false);
    setPending(true);
    try {
      const { data } = await API.login(user, password);
      const success = data?.status === 0;
      // The shared login client may unmount the global dialog by setting auth.
      // Its fresh status is still required; cancelled local dialogs stay closed.
      if (success && !onSuccess) void API.invalidateStatus();
      if (!mounted.current) return;
      setLoginError(!success);
      if (success) {
        if (onSuccess) await onSuccess();
      }
    } catch {
      if (mounted.current) setLoginError(true);
    } finally {
      if (mounted.current) setPending(false);
    }
  };

  return (
    <>
      <Dialog
        open={true}
        maxWidth="xs"
        aria-label={t('auth.login')}
        onClose={onCancel}
        disableEscapeKeyDown={!onCancel}
        slotProps={{
          paper: {
            component: 'form',
            autoComplete: 'off',
            // @ts-expect-error - MUI Dialog does not support types for the `onSubmit` prop directly
            onSubmit: (event: FormEvent<HTMLFormElement>) => {
              event.preventDefault();
              void handleLogin();
            },
          },
        }}
      >
        <DialogContent sx={{ pt: 4, pb: 0 }}>
          <TextField
            autoFocus
            autoComplete="off"
            margin="dense"
            label={t('auth.username')}
            fullWidth
            variant="outlined"
            value={user}
            disabled={pending}
            onChange={(e) => setUser(e.target.value)}
            sx={{ mb: 2, mt: 0 }}
          />

          <TextField
            autoComplete="off"
            type="password"
            margin="dense"
            label={t('auth.password')}
            fullWidth
            variant="outlined"
            value={password}
            disabled={pending}
            onChange={(e) => setPassword(e.target.value)}
            sx={{ mb: 2, mt: 0 }}
          />

          {loginError && (
            <Alert severity="error" variant="outlined" sx={{ mb: 1 }}>
              {t('auth.error')}
            </Alert>
          )}
        </DialogContent>
        <DialogActions
          sx={{
            justifyContent: 'center',
            pb: 3,
          }}
        >
          {onCancel && <Button onClick={onCancel}>{t('common.cancel')}</Button>}
          <Button
            type="submit"
            variant="contained"
            disabled={pending}
            sx={{ px: 7 }}
          >
            {t('auth.login')}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
};

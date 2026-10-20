import { useState, type FormEvent } from 'react';
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  TextField,
  Typography,
} from '@mui/material';

import { API } from '@/api/client';

import { useStatus } from '@/hooks/useStatus';
import { useTranslation } from '@/hooks/useTranslation';

export const PasswordDialog = ({ onClose }: { onClose: VoidFunction }) => {
  const { t } = useTranslation();
  const { csrfToken, username } = useStatus();
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);

  const handleSave = async () => {
    if (pending || !csrfToken) return;
    if (password !== confirmation) {
      setError(t('auth.password_mismatch'));
      return;
    }
    if (
      new TextEncoder().encode(password).length > 72 ||
      password.includes('\0')
    ) {
      setError(t('auth.password_invalid'));
      return;
    }
    setError('');
    setPending(true);
    try {
      const { data } = await API.changePassword(
        password,
        confirmation,
        csrfToken,
      );
      if (data?.status === 0) {
        await API.invalidateStatus();
        onClose();
      } else {
        setError(t('auth.password_save_error'));
      }
    } catch {
      setError(t('auth.password_save_error'));
    } finally {
      setPending(false);
    }
  };

  return (
    <Dialog
      open
      maxWidth="xs"
      fullWidth
      onClose={() => !pending && onClose()}
      slotProps={{
        paper: {
          component: 'form',
          // @ts-expect-error - MUI Dialog does not type the form's onSubmit
          onSubmit: (event: FormEvent<HTMLFormElement>) => {
            event.preventDefault();
            void handleSave();
          },
        },
      }}
    >
      <DialogTitle>{t('auth.change_password')}</DialogTitle>
      <DialogContent>
        <Typography variant="body2" sx={{ mb: 1 }}>
          {t('auth.panel_username', { username: username ?? '' })}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {t('auth.password_hint')}
        </Typography>
        <TextField
          autoFocus
          fullWidth
          margin="dense"
          type="password"
          autoComplete="new-password"
          label={t('auth.new_password')}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          disabled={pending}
        />
        <TextField
          fullWidth
          margin="dense"
          type="password"
          autoComplete="new-password"
          label={t('auth.confirm_password')}
          value={confirmation}
          onChange={(event) => setConfirmation(event.target.value)}
          disabled={pending}
        />
        {error && (
          <Alert severity="error" sx={{ mt: 2 }}>
            {error}
          </Alert>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={pending}>
          {t('common.cancel')}
        </Button>
        <Button
          type="submit"
          variant="contained"
          disabled={pending || !csrfToken}
        >
          {t('common.save')}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

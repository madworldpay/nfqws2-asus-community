import CloseIcon from '@mui/icons-material/Close';
import {
  Alert,
  Box,
  IconButton,
  Paper,
  Snackbar,
  Stack,
  Typography,
} from '@mui/material';

import type { Appearance } from '@/store/useAppearanceStore';

import { useTranslation } from '@/hooks/useTranslation';

export function ShareThanks({
  appearance,
  event,
  onClose,
}: {
  appearance: Appearance;
  event: number;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  if (!event) return null;
  return (
    <Snackbar
      open
      autoHideDuration={10000}
      anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      onClose={(_, reason) => {
        if (reason !== 'clickaway') onClose();
      }}
    >
      {appearance === 'rabbit' ? (
        <Paper
          role="status"
          aria-live="polite"
          elevation={12}
          sx={{
            position: 'relative',
            width: { xs: 'min(360px, calc(100vw - 32px))', lg: 400 },
            '@media (min-width: 2560px)': { width: 448 },
            '@media (min-width: 3200px)': { width: 480 },
            boxSizing: 'border-box',
            p: 3,
            pt: 2.5,
            border: '1px solid #35475e',
            borderRadius: 4,
            background:
              'radial-gradient(ellipse at 50% 0%, #233249 0%, #101925 70%)',
            color: '#e8edf5',
            boxShadow: '0 12px 48px #0008',
          }}
        >
          <IconButton
            aria-label={t('common.close')}
            onClick={onClose}
            size="small"
            sx={{ position: 'absolute', top: 8, right: 8, color: '#b7c7da' }}
          >
            <CloseIcon fontSize="small" />
          </IconButton>
          <Stack spacing={2} alignItems="center">
            <Box
              component="img"
              src={`/community/rabbit-respect-once.gif?sent=${event}`}
              alt=""
              aria-hidden="true"
              width={192}
              height={192}
              sx={{
                display: 'block',
                width: { xs: 176, sm: 192, lg: 224 },
                height: { xs: 176, sm: 192, lg: 224 },
                '@media (min-width: 2560px)': { width: 288, height: 288 },
                '@media (min-width: 3200px)': { width: 352, height: 352 },
                borderRadius: '50%',
                objectFit: 'cover',
                flexShrink: 0,
                border: '1px solid #60758d',
                backgroundColor: '#0b1119',
                boxShadow: '0 0 28px #93b7df18',
              }}
            />
            <Typography
              sx={{
                fontSize: 18,
                fontWeight: 500,
                lineHeight: 1.5,
                textAlign: 'center',
                maxWidth: 280,
              }}
            >
              {t('report.mail_states.accepted')}
            </Typography>
          </Stack>
        </Paper>
      ) : (
        <Alert severity="success" variant="filled" onClose={onClose}>
          {t('report.mail_states.accepted')}
        </Alert>
      )}
    </Snackbar>
  );
}

import { useState } from 'react';
import CloseIcon from '@mui/icons-material/Close';
import {
  Alert,
  Box,
  ButtonBase,
  IconButton,
  Paper,
  Snackbar,
  Stack,
  Typography,
} from '@mui/material';

import type { Appearance } from '@/store/useAppearanceStore';

import { useTranslation } from '@/hooks/useTranslation';

type ShareThanksProps = {
  appearance: Appearance;
  event: number;
  onClose: () => void;
};

export function ShareThanks(props: ShareThanksProps) {
  return props.event ? <AcceptedThanks key={props.event} {...props} /> : null;
}

function AcceptedThanks({ appearance, event, onClose }: ShareThanksProps) {
  const { t } = useTranslation();
  const [interaction, setInteraction] = useState({ clicks: 0, replays: 0 });
  const nod = () =>
    setInteraction(({ clicks, replays }) =>
      clicks === 27
        ? { clicks: 0, replays: replays + 1 }
        : { clicks: clicks + 1, replays },
    );
  return (
    <Snackbar
      open
      autoHideDuration={10000}
      anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      sx={
        appearance === 'rabbit'
          ? {
              '&&': {
                inset: '50% auto auto 50%',
                transform: 'translate(-50%, -50%)',
                width: 'max-content',
                maxWidth: 'calc(100vw - 32px)',
              },
            }
          : undefined
      }
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
            <ButtonBase
              aria-label={t('report.frank')}
              disableRipple
              onClick={nod}
              sx={{ borderRadius: '50%', flexShrink: 0 }}
            >
              <Box
                key={interaction.replays}
                component="img"
                src={`/community/rabbit-respect-once.gif?sent=${event}${interaction.replays ? `&replay=${interaction.replays}` : ''}`}
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
            </ButtonBase>
            <Typography
              sx={{
                fontSize: 18,
                fontWeight: 500,
                lineHeight: 1.5,
                textAlign: 'center',
                maxWidth: 280,
              }}
            >
              {t(
                interaction.replays
                  ? 'report.mail_states.watching'
                  : 'report.mail_states.accepted',
              )}
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

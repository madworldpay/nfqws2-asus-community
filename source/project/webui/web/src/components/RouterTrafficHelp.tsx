import { useId, useState, type ReactNode } from 'react';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';
import { Alert, IconButton, Stack, Tooltip, Typography } from '@mui/material';

import { useStatus } from '@/hooks/useStatus';
import { useTranslation } from '@/hooks/useTranslation';

export const RouterTrafficHelp = ({
  children,
  title,
}: {
  children: ReactNode;
  title?: string;
}) => {
  const { t } = useTranslation();
  const { platform } = useStatus();
  const [open, setOpen] = useState(false);
  const id = useId();
  const helpTitle = title ?? t('share.dpi_help_title');
  return (
    <Stack spacing={1}>
      <Stack direction="row" alignItems="center" spacing={0.5}>
        {children}
        <Tooltip title={helpTitle}>
          <IconButton
            size="small"
            aria-label={helpTitle}
            aria-expanded={open}
            aria-controls={open ? id : undefined}
            onClick={() => setOpen(!open)}
          >
            <HelpOutlineIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Stack>
      {open && (
        <Alert severity="info" id={id}>
          <Stack spacing={1}>
            <Typography variant="body2">{t('share.dpi_help_scope')}</Typography>
            <Typography variant="body2">
              {t('share.dpi_help_clients')}
            </Typography>
            <Typography variant="body2">
              {t('share.dpi_help_address')}
            </Typography>
            <Typography
              component="code"
              sx={{ userSelect: 'all', overflowWrap: 'anywhere' }}
            >
              ip -4 route get 1.1.1.1
            </Typography>
            <Typography variant="body2">
              {t(
                platform === 'openwrt'
                  ? 'share.dpi_help_command_openwrt'
                  : 'share.dpi_help_command',
              )}
            </Typography>
            <Typography variant="body2">{t('share.dpi_help_all')}</Typography>
            <Typography variant="body2">{t('share.dpi_help_paths')}</Typography>
          </Stack>
        </Alert>
      )}
    </Stack>
  );
};

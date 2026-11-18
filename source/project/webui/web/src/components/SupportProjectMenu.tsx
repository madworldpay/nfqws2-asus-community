import { useId, useState } from 'react';
import CheckIcon from '@mui/icons-material/Check';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import FavoriteBorderIcon from '@mui/icons-material/FavoriteBorder';
import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown';
import TelegramIcon from '@mui/icons-material/Telegram';
import {
  Box,
  Button,
  Divider,
  ListItemIcon,
  ListItemText,
  Menu,
  MenuItem,
  Typography,
} from '@mui/material';

import { SupportAssetIcon } from '@/components/SupportAssetIcon';
import { supportWallets } from '@/components/supportWallets';

import { useTranslation } from '@/hooks/useTranslation';

import { copyText } from '@/utils/copyText';

export function SupportProjectMenu() {
  const { t } = useTranslation();
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const [copyResult, setCopyResult] = useState<{
    key: string;
    ok: boolean;
  } | null>(null);
  const buttonId = useId();
  const menuId = useId();
  const open = anchor !== null;

  return (
    <>
      <Button
        id={buttonId}
        size="small"
        color="inherit"
        startIcon={<FavoriteBorderIcon />}
        endIcon={<KeyboardArrowDownIcon />}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={(event) => {
          setCopyResult(null);
          setAnchor(event.currentTarget);
        }}
        sx={{ color: 'text.secondary', fontSize: 14, py: 0.25 }}
      >
        {t('support.button')}
      </Button>
      <Menu
        id={menuId}
        anchorEl={anchor}
        open={open}
        onClose={() => setAnchor(null)}
        MenuListProps={{ 'aria-labelledby': buttonId }}
        slotProps={{
          paper: {
            sx: {
              width: 380,
              maxWidth: 'calc(100vw - 32px)',
              maxHeight: 'calc(100dvh - 32px)',
              colorScheme: 'dark',
            },
          },
        }}
      >
        <Box component="li" role="presentation" sx={{ px: 2, py: 1 }}>
          <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 0.75 }}>
            {t('support.title')}
          </Typography>
          <Typography variant="body2" sx={{ whiteSpace: 'normal' }}>
            {t('support.intro')}
          </Typography>
        </Box>
        <MenuItem
          component="a"
          href="https://yoomoney.ru/to/4100119670967911"
          target="_blank"
          rel="noopener noreferrer"
          onClick={() => setAnchor(null)}
        >
          <ListItemIcon>
            <SupportAssetIcon asset="YOOMONEY" />
          </ListItemIcon>
          <ListItemText
            primary={t('support.yoomoney')}
            secondary="4100119670967911"
          />
        </MenuItem>
        <MenuItem
          component="a"
          href="https://boosty.to/madworldpay/donate"
          target="_blank"
          rel="noopener noreferrer"
          onClick={() => setAnchor(null)}
        >
          <ListItemIcon>
            <FavoriteBorderIcon fontSize="small" sx={{ color: '#f15f2c' }} />
          </ListItemIcon>
          <ListItemText>Boosty</ListItemText>
        </MenuItem>
        <Divider component="li" />
        <Box component="li" role="presentation" sx={{ px: 2, pt: 1, pb: 0.5 }}>
          <Typography variant="caption" color="text.secondary">
            {t('support.crypto')}
          </Typography>
        </Box>
        {supportWallets.map((wallet) => {
          const key = wallet.network;
          const copied = copyResult?.key === key && copyResult.ok;
          return (
            <MenuItem
              key={key}
              aria-label={`${t('support.copy_address')}: ${wallet.network} · ${wallet.assets}`}
              onClick={() => {
                void copyText(wallet.address)
                  .then((ok) => setCopyResult({ key, ok }))
                  .catch(() => setCopyResult({ key, ok: false }));
              }}
              sx={{ gap: 1, py: 1, whiteSpace: 'normal', alignItems: 'center' }}
            >
              <ListItemIcon sx={{ minWidth: '28px !important' }}>
                <SupportAssetIcon asset={wallet.icon} />
              </ListItemIcon>
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography variant="body2" fontWeight={600}>
                  {wallet.network}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {wallet.assets}
                </Typography>
                <Typography
                  component="div"
                  variant="caption"
                  sx={{
                    fontFamily: 'monospace',
                    overflowWrap: 'anywhere',
                    lineHeight: 1.4,
                    userSelect: 'text',
                  }}
                >
                  {wallet.address}
                </Typography>
              </Box>
              {copied ? (
                <CheckIcon fontSize="small" color="success" />
              ) : (
                <ContentCopyIcon
                  fontSize="small"
                  sx={{ color: 'text.secondary' }}
                />
              )}
            </MenuItem>
          );
        })}
        {copyResult && (
          <Box component="li" role="presentation" sx={{ px: 2, py: 1 }}>
            <Typography
              variant="caption"
              role="status"
              color={copyResult.ok ? 'success.main' : 'error.main'}
            >
              {t(copyResult.ok ? 'support.copied' : 'support.copy_failed')}
            </Typography>
          </Box>
        )}
        <Divider component="li" />
        <MenuItem
          component="a"
          href="https://t.me/Profy13"
          target="_blank"
          rel="noopener noreferrer"
          onClick={() => setAnchor(null)}
        >
          <ListItemIcon>
            <TelegramIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText>{t('support.contact_admin')}</ListItemText>
        </MenuItem>
        <Box component="li" role="presentation" sx={{ px: 2, py: 1 }}>
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ whiteSpace: 'normal' }}
          >
            {t('support.thanks')}
          </Typography>
        </Box>
      </Menu>
    </>
  );
}

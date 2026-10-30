import { useState } from 'react';
import DarkModeIcon from '@mui/icons-material/DarkMode';
import GitHubIcon from '@mui/icons-material/GitHub';
import LightModeIcon from '@mui/icons-material/LightMode';
import LogoutOutlinedIcon from '@mui/icons-material/LogoutOutlined';
import MenuBookIcon from '@mui/icons-material/MenuBook';
import {
  Box,
  IconButton,
  Link,
  Stack,
  Typography,
  useColorScheme,
} from '@mui/material';

import { API } from '@/api/client';

import { TechnicalChannel } from '@/components/TechnicalChannel';
import { ThemeMenu } from '@/components/ThemeMenu';

import { useAppStore } from '@/store/useAppStore';

import { useStatus } from '@/hooks/useStatus';
import { useTranslation } from '@/hooks/useTranslation';

export const Footer = () => {
  const { auth } = useAppStore();
  const { anonym } = useStatus();
  const { t, langcode, setLanguage } = useTranslation();

  const { mode } = useColorScheme();
  const [themeAnchor, setThemeAnchor] = useState<HTMLElement | null>(null);

  return (
    <>
      <TechnicalChannel />
      <Box
        sx={{
          display: 'flex',
          px: 'max(15px, 1.6vh)',
          pt: 1,
          pb: 1.5,
          borderTop: '1px solid',
          borderColor: 'divider',
          backgroundColor: 'background.paper',
          justifyContent: 'space-between',
          gap: 2,
          alignItems: 'center',
          lineHeight: '28px',
        }}
      >
        <Stack
          direction="row"
          spacing={2}
          useFlexGap
          alignSelf="center"
          fontSize={14}
          sx={{
            flexWrap: 'wrap',
            '& > *': {
              display: 'inline-flex',
              gap: 0.85,
              alignItems: 'center',
            },
          }}
        >
          <Typography component="span" variant="body2" color="text.secondary">
            {t('system.thanks_projects')}
          </Typography>
          <Link
            href="https://github.com/nfqws/nfqws-keenetic"
            target="_blank"
            rel="noreferrer"
            underline="none"
            color="text.secondary"
            sx={{
              display: 'inline-flex',
              gap: 0.85,
              fontSize: 14,
              '&:hover': {
                color: 'primary.main',
              },
            }}
          >
            <GitHubIcon sx={{ fontSize: '1.2em' }} />
            nfqws
          </Link>

          <Link
            href="https://github.com/nfqws/nfqws2-keenetic"
            target="_blank"
            rel="noreferrer"
            underline="none"
            color="text.secondary"
            sx={{
              display: 'inline-flex',
              gap: 0.85,
              fontSize: 14,
              '&:hover': {
                color: 'primary.main',
              },
            }}
          >
            <GitHubIcon sx={{ fontSize: '1.2em' }} />
            NFQWS2 Keenetic
          </Link>

          <Link
            href="https://github.com/bol-van/zapret2"
            target="_blank"
            rel="noreferrer"
            underline="none"
            color="text.secondary"
            sx={{
              display: 'inline-flex',
              gap: 0.85,
              fontSize: 14,
              '&:hover': { color: 'primary.main' },
            }}
          >
            <GitHubIcon sx={{ fontSize: '1.2em' }} />
            zapret2 (bol-van)
          </Link>

          <Link
            href="https://github.com/Runnin4ik/dpi-detector"
            target="_blank"
            rel="noopener noreferrer"
            underline="none"
            color="text.secondary"
            sx={{ '&:hover': { color: 'primary.main' } }}
          >
            <GitHubIcon sx={{ fontSize: '1.2em' }} />
            DPI Detector
          </Link>
          <Link
            href="https://wiki.zapret.moe/"
            target="_blank"
            rel="noopener noreferrer"
            underline="none"
            color="text.secondary"
            sx={{ '&:hover': { color: 'primary.main' } }}
          >
            <MenuBookIcon sx={{ fontSize: '1.2em' }} />
            Wiki Zapret
          </Link>
        </Stack>

        <Stack
          direction="row"
          spacing={2}
          alignSelf="center"
          fontSize={14}
          sx={{
            '& > *': {
              display: 'inline-flex',
              gap: 0.85,
              alignItems: 'center',
            },
          }}
        >
          <IconButton
            size="small"
            title={
              langcode === 'ru'
                ? t('system.change_lang_en')
                : t('system.change_lang_ru')
            }
            sx={{
              display: 'inline-flex',
              fontSize: 13,
              ml: 0.5,
              color: 'text.secondary',
              '&:hover': {
                color: 'primary.main',
              },
            }}
            onClick={async () => {
              setLanguage(langcode === 'ru' ? 'en' : 'ru');
            }}
          >
            EN / RU
          </IconButton>

          <IconButton
            size="small"
            title={t('system.change_theme')}
            aria-label={t('system.change_theme')}
            aria-haspopup="menu"
            aria-expanded={Boolean(themeAnchor)}
            sx={{
              display: 'inline-flex',
              fontSize: 15,
              ml: 0.5,
              color: 'text.secondary',
              '&:hover': {
                color: 'primary.main',
              },
            }}
            onClick={(event) => setThemeAnchor(event.currentTarget)}
          >
            {mode === 'light' ? (
              <DarkModeIcon sx={{ fontSize: '1.2em' }} />
            ) : (
              <LightModeIcon sx={{ fontSize: '1.2em' }} />
            )}
          </IconButton>

          <ThemeMenu
            anchorEl={themeAnchor}
            onClose={() => setThemeAnchor(null)}
          />

          {auth && !anonym && (
            <IconButton
              size="small"
              title={t('auth.logout')}
              sx={{
                display: 'inline-flex',
                fontSize: 15,
                ml: 0.5,
                color: 'text.secondary',
                '&:hover': {
                  color: 'primary.main',
                },
              }}
              onClick={async () => {
                await API.logout();
                void API.invalidateStatus();
              }}
            >
              <LogoutOutlinedIcon sx={{ fontSize: '1.2em' }} />
            </IconButton>
          )}
        </Stack>
      </Box>
    </>
  );
};

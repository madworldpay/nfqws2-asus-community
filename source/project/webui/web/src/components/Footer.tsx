import { useId, useState } from 'react';
import GitHubIcon from '@mui/icons-material/GitHub';
import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown';
import KeyboardArrowUpIcon from '@mui/icons-material/KeyboardArrowUp';
import LogoutOutlinedIcon from '@mui/icons-material/LogoutOutlined';
import MenuBookIcon from '@mui/icons-material/MenuBook';
import TelegramIcon from '@mui/icons-material/Telegram';
import {
  Box,
  Button,
  Collapse,
  IconButton,
  Link,
  Stack,
  Typography,
  useMediaQuery,
} from '@mui/material';

import { API } from '@/api/client';

import { CommunityChatLink } from '@/components/CommunityChatLink';
import { MtprotoInstallDialog } from '@/components/MtprotoInstallDialog';
import { TechnicalChannel } from '@/components/TechnicalChannel';
import { ThemeCycleButton } from '@/components/ThemeCycleButton';

import { useAppStore } from '@/store/useAppStore';

import { useStatus } from '@/hooks/useStatus';
import { useTranslation } from '@/hooks/useTranslation';

export const Footer = () => {
  const { auth } = useAppStore();
  const { anonym, csrfToken } = useStatus();
  const { t, langcode, setLanguage } = useTranslation();
  const mobile = useMediaQuery('(max-width: 599.95px)', { noSsr: true });

  const [mtprotoOpen, setMtprotoOpen] = useState(false);
  const [collapsedByLayout, setCollapsedByLayout] = useState(() => {
    let desktop = false;
    let mobile = true;
    try {
      desktop = localStorage.getItem('nfqws2-footer-collapsed') === '1';
      const savedMobile = localStorage.getItem(
        'nfqws2-footer-collapsed-mobile',
      );
      mobile = savedMobile === null || savedMobile === '1';
    } catch {
      // Default to a compact footer on phones when storage is unavailable.
    }
    return { desktop, mobile };
  });
  const layout = mobile ? 'mobile' : 'desktop';
  const collapsed = collapsedByLayout[layout];
  const footerId = useId();
  const reducedMotion = useMediaQuery('(prefers-reduced-motion: reduce)');
  const toggleFooter = () => {
    const next = !collapsed;
    setCollapsedByLayout((previous) => ({ ...previous, [layout]: next }));
    try {
      localStorage.setItem(
        mobile ? 'nfqws2-footer-collapsed-mobile' : 'nfqws2-footer-collapsed',
        next ? '1' : '0',
      );
    } catch {
      // The footer still works when browser storage is unavailable.
    }
  };

  return (
    <>
      {mtprotoOpen && (
        <MtprotoInstallDialog
          onClose={() => setMtprotoOpen(false)}
          csrfToken={csrfToken}
        />
      )}
      <Box component="footer" sx={{ flexShrink: 0, minWidth: 0 }}>
        <Collapse
          in={!collapsed}
          timeout={reducedMotion ? 0 : 180}
          id={footerId}
          sx={{
            '@media (max-width: 599.95px)': {
              maxHeight: 'min(35svh, 240px)',
              overflowY: 'auto',
            },
          }}
        >
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
              flexWrap: 'wrap',
              columnGap: 2,
              rowGap: 1,
              alignItems: 'center',
              lineHeight: '28px',
            }}
          >
            <Button
              size="small"
              startIcon={<TelegramIcon />}
              onClick={() => setMtprotoOpen(true)}
            >
              {t('mtproto.button')}
            </Button>
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
              <CommunityChatLink />
              <Link
                href="https://github.com/madworldpay/nfqws2-asus-community/releases"
                target="_blank"
                rel="noopener noreferrer"
                underline="hover"
                variant="body2"
                sx={{ display: 'inline-flex', gap: 0.75, alignItems: 'center' }}
              >
                <GitHubIcon sx={{ fontSize: '1.2em' }} />
                {t('community.releases')}
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
              <ThemeCycleButton />

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
            <Stack
              direction="row"
              spacing={2}
              useFlexGap
              fontSize={14}
              sx={{
                flexBasis: '100%',
                flexWrap: 'wrap',
                rowGap: 0.5,
                '& > *': {
                  display: 'inline-flex',
                  gap: 0.85,
                  alignItems: 'center',
                },
              }}
            >
              <Typography
                component="span"
                variant="body2"
                color="text.secondary"
              >
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
          </Box>
        </Collapse>
        <Button
          type="button"
          onClick={toggleFooter}
          aria-expanded={!collapsed}
          aria-controls={footerId}
          startIcon={
            collapsed ? <KeyboardArrowUpIcon /> : <KeyboardArrowDownIcon />
          }
          sx={{
            display: 'flex',
            width: '100%',
            minHeight: { xs: 36, sm: 28 },
            py: 0.25,
            borderRadius: 0,
            borderTop: '1px solid',
            borderColor: 'divider',
            backgroundColor: 'background.paper',
            color: 'text.secondary',
            fontSize: 12,
            '@media (pointer:coarse)': { minHeight: 36 },
          }}
        >
          {t(collapsed ? 'system.footer_expand' : 'system.footer_collapse')}
        </Button>
      </Box>
    </>
  );
};

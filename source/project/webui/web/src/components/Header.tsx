import { useState } from 'react';
import { useConfig } from '@/config/useConfig';
import CloudDoneIcon from '@mui/icons-material/CloudDone';
import CloudOffIcon from '@mui/icons-material/CloudOff';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';
import MenuIcon from '@mui/icons-material/Menu';
import PaletteOutlinedIcon from '@mui/icons-material/PaletteOutlined';
import PasswordIcon from '@mui/icons-material/Password';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import ReplayIcon from '@mui/icons-material/Replay';
import SaveIcon from '@mui/icons-material/Save';
import StopCircleIcon from '@mui/icons-material/StopCircle';
import {
  Box,
  Button,
  IconButton,
  Link,
  ListItemIcon,
  Menu,
  MenuItem,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material';
import { Link as RouterLink, useNavigate } from '@tanstack/react-router';

import { API } from '@/api/client';
import { type ServiceActionRequest } from '@/api/schema';

import { ArkDialog } from '@/components/ArkDialog';
import { CommunityActions } from '@/components/CommunityActions';
import { CurrentVersion } from '@/components/CurrentVersion';
import { ImportDialog } from '@/components/ImportDialog';
import { OutputLogDialog } from '@/components/OutputLogDialog';
import { PasswordDialog } from '@/components/PasswordDialog';
import { RequirementsDialog } from '@/components/RequirementsDialog';
import { ShareDialog } from '@/components/ShareDialog';
import { ShareThanks } from '@/components/ShareThanks';
import { ThemeMenu } from '@/components/ThemeMenu';
import { Trans } from '@/components/Trans';

import { useAppearanceStore } from '@/store/useAppearanceStore';
import { useAppStore } from '@/store/useAppStore';

import { useStatus } from '@/hooks/useStatus';
import { useTranslation } from '@/hooks/useTranslation';

export const Header = () => {
  const { t, langcode, setLanguage } = useTranslation();
  const navigate = useNavigate();
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const open = Boolean(anchorEl);
  const [themeAnchor, setThemeAnchor] = useState<HTMLElement | null>(null);

  const { service, nfqws2 } = useStatus();

  const config = useConfig(nfqws2);

  const { auth, needSave, onSave, needReload, setNeedReload } = useAppStore();

  const [output, setOutput] = useState<boolean | string>(false);
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [arkOpen, setArkOpen] = useState(false);
  const [requirementsOpen, setRequirementsOpen] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [shareThanks, setShareThanks] = useState(0);
  const { appearance } = useAppearanceStore();

  const handleMenuOpen = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget);
  };

  const handleMenuClose = () => {
    setAnchorEl(null);
  };

  const handleMenuClick = async (command: ServiceActionRequest['cmd']) => {
    handleMenuClose();
    setOutput(true);
    const { data } = await API.action(command);
    setOutput(`> nfqws2-asus ${command}\n${data?.output?.join('\n') || ''}`);
    void API.invalidateStatus();

    if (command === 'upgrade') {
      setNeedReload(true);
    }
  };

  return (
    <>
      <Box
        sx={{
          px: 'max(15px, 1.6vh)',
          py: 'max(15px, 1.6vh)',
          borderBottom: '1px solid',
          borderColor: 'divider',
          backgroundColor: 'background.paper',
          whiteSpace: 'nowrap',
        }}
      >
        <Box
          display="flex"
          alignItems="baseline"
          justifyContent="space-between"
          flexWrap="wrap"
          rowGap={2}
          columnGap={1.7}
        >
          <Stack
            direction="row"
            spacing={1.3}
            alignItems="center"
            flexGrow={1000}
            useFlexGap
            flexWrap="wrap"
          >
            <Link
              component={RouterLink}
              underline="none"
              to="/"
              sx={{
                display: 'inline-flex',
                gap: 1.3,
                alignItems: 'center',
                direction: 'row',
                userSelect: 'none',
              }}
            >
              <Typography
                component="h2"
                fontFamily={'Roboto, sans-serif'}
                textTransform="uppercase"
                color="primary.main"
                fontSize="1.25em"
                lineHeight={1}
                sx={{
                  '@media (max-width: 475px)': {
                    fontSize: '0.85em',
                  },
                }}
              >
                ASUS
              </Typography>
              <Typography
                component="h2"
                fontFamily={'Device Model, Roboto, sans-serif'}
                textTransform="uppercase"
                color="textPrimary"
                fontSize="1.131em"
                lineHeight={1}
                pt="3px"
                sx={{
                  '@media (max-width: 475px)': {
                    fontSize: '0.8em',
                  },
                }}
              >
                {config.title}
              </Typography>

              {auth && service && (
                <CloudDoneIcon
                  sx={{
                    fontSize: '1.25em',
                    color: 'success.main',
                    alignSelf: 'center',
                    opacity: 0.9,
                    '@media (max-width: 475px)': {
                      fontSize: '1em',
                    },
                  }}
                />
              )}
              {auth && !service && (
                <CloudOffIcon
                  sx={{
                    fontSize: '1.25em',
                    color: 'error.main',
                    alignSelf: 'center',
                    opacity: 0.9,
                    '@media (max-width: 475px)': {
                      fontSize: '1em',
                    },
                  }}
                />
              )}
            </Link>
            <CurrentVersion
              sx={{
                justifyContent: 'flex-end',
                flexGrow: 500,
              }}
            />
          </Stack>

          <Stack
            direction="row"
            spacing={{ xs: 0.5, sm: 1 }}
            useFlexGap
            flexWrap="wrap"
            flexGrow={1}
            justifyContent="flex-end"
            sx={{ rowGap: 1 }}
          >
            <Button
              variant="outlined"
              size="small"
              onClick={() => setRequirementsOpen(true)}
              startIcon={<HelpOutlineIcon />}
            >
              <Trans i18nKey="requirements.title" />
            </Button>
            {auth && (
              <Button
                variant="outlined"
                size="small"
                onClick={() => setArkOpen(true)}
              >
                <Trans i18nKey="ark.title" />
              </Button>
            )}
            {auth && (
              <CommunityActions
                onImport={() => setImportOpen(true)}
                importDisabled={needSave}
                onShare={() => {
                  setShareThanks(0);
                  setShareOpen(true);
                }}
              />
            )}
            <Button
              variant="text"
              size="small"
              title={
                langcode === 'ru'
                  ? t('system.change_lang_en')
                  : t('system.change_lang_ru')
              }
              aria-label={
                langcode === 'ru'
                  ? t('system.change_lang_en')
                  : t('system.change_lang_ru')
              }
              onClick={() => setLanguage(langcode === 'ru' ? 'en' : 'ru')}
              sx={{ minWidth: 60, gap: 0.5 }}
            >
              <span style={{ fontWeight: langcode === 'en' ? 700 : 400 }}>
                EN
              </span>
              /
              <span style={{ fontWeight: langcode === 'ru' ? 700 : 400 }}>
                RU
              </span>
            </Button>
            {auth && (
              <Tooltip title={t('auth.change_password')} enterTouchDelay={0}>
                <IconButton
                  size="small"
                  aria-label={t('auth.change_password')}
                  onClick={() => setPasswordOpen(true)}
                  sx={{
                    width: 34,
                    height: 34,
                    border: '1px solid',
                    borderColor: 'divider',
                    borderRadius: 1,
                  }}
                >
                  <PasswordIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            )}
            <Button
              variant="contained"
              size="small"
              startIcon={<SaveIcon />}
              disabled={!needSave}
              color="error"
              onClick={onSave}
            >
              <Trans i18nKey="common.save" />
            </Button>

            <Stack
              direction="row"
              alignItems="center"
              flexGrow={1}
              justifyContent="flex-end"
            >
              <Button
                variant="text"
                size="small"
                onClick={handleMenuOpen}
                sx={{
                  color: 'text.secondary',
                  transition: 'color 0.1s ease-in-out',
                  minWidth: 0,
                  '&:hover': {
                    color: 'primary.main',
                  },
                }}
              >
                <MenuIcon />
              </Button>

              <Menu
                anchorEl={anchorEl}
                open={open}
                onClose={handleMenuClose}
                anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
                transformOrigin={{ vertical: 'top', horizontal: 'right' }}
                slotProps={{
                  paper: {
                    sx: {
                      bgcolor: 'background.default',
                      backgroundImage: 'none',
                      border: '1px solid',
                      borderColor: 'divider',
                    },
                  },
                }}
              >
                <MenuItem
                  onClick={() => {
                    setThemeAnchor(anchorEl);
                    handleMenuClose();
                  }}
                  sx={{ fontSize: 14 }}
                >
                  <ListItemIcon>
                    <PaletteOutlinedIcon />
                  </ListItemIcon>
                  <Trans i18nKey="system.change_theme" />
                </MenuItem>
                {service && (
                  <MenuItem
                    onClick={() => handleMenuClick('restart')}
                    sx={{ fontSize: 14 }}
                  >
                    <ListItemIcon>
                      <ReplayIcon />
                    </ListItemIcon>
                    <Trans i18nKey="common.restart" />
                  </MenuItem>
                )}

                {service ? (
                  <MenuItem
                    onClick={() => handleMenuClick('stop')}
                    sx={{ fontSize: 14 }}
                  >
                    <ListItemIcon>
                      <StopCircleIcon />
                    </ListItemIcon>
                    <Trans i18nKey="common.stop" />
                  </MenuItem>
                ) : (
                  <MenuItem
                    onClick={() => handleMenuClick('start')}
                    sx={{ fontSize: 14 }}
                  >
                    <ListItemIcon>
                      <PlayArrowIcon />
                    </ListItemIcon>
                    <Trans i18nKey="common.start" />
                  </MenuItem>
                )}
              </Menu>
            </Stack>
          </Stack>
        </Box>
      </Box>

      <ThemeMenu anchorEl={themeAnchor} onClose={() => setThemeAnchor(null)} />
      <OutputLogDialog
        content={output}
        open={Boolean(output)}
        onClose={() => {
          setOutput('');
          if (needReload) {
            window.location.reload();
          }
        }}
      />
      {requirementsOpen && (
        <RequirementsDialog
          onClose={() => setRequirementsOpen(false)}
          onOpenSmartDns={() => {
            setRequirementsOpen(false);
            void navigate({ to: '/smartdns' });
          }}
          onOpenArk={() => {
            setRequirementsOpen(false);
            setArkOpen(true);
          }}
        />
      )}
      {auth && arkOpen && <ArkDialog onClose={() => setArkOpen(false)} />}
      {auth && shareOpen && (
        <ShareDialog
          onClose={() => setShareOpen(false)}
          onSent={() => {
            setShareOpen(false);
            setShareThanks(Date.now());
          }}
        />
      )}
      {auth && importOpen && (
        <ImportDialog onClose={() => setImportOpen(false)} />
      )}
      <ShareThanks
        appearance={appearance}
        event={shareThanks}
        onClose={() => setShareThanks(0)}
      />
      {auth && passwordOpen && (
        <PasswordDialog onClose={() => setPasswordOpen(false)} />
      )}
    </>
  );
};

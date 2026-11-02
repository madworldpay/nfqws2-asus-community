import { useRef, useState } from 'react';
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
  Alert,
  AlertTitle,
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
import { RestartScheduleDialog } from '@/components/RestartScheduleDialog';
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

  const {
    service,
    nfqws2,
    arkLoaded,
    platform,
    authenticated,
    anonym,
    csrfToken,
    isReady,
  } = useStatus();

  const config = useConfig(nfqws2);

  const { auth, needSave, onSave, needReload, setNeedReload } = useAppStore();

  // Basic service actions also work in the intentionally password-free panel.
  // Scheduling keeps its authenticated-session requirement below.
  const canControlService = auth && isReady && (authenticated || anonym);

  const [output, setOutput] = useState<boolean | string>(false);
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [arkOpen, setArkOpen] = useState(false);
  const [requirementsOpen, setRequirementsOpen] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [shareThanks, setShareThanks] = useState(0);
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [actionPending, setActionPending] = useState(false);
  const actionInFlight = useRef(false);
  const { appearance } = useAppearanceStore();

  const handleMenuOpen = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget);
  };

  const handleMenuClose = () => {
    setAnchorEl(null);
  };

  const handleMenuClick = async (command: ServiceActionRequest['cmd']) => {
    if (!canControlService || actionInFlight.current) return;
    actionInFlight.current = true;
    setActionPending(true);
    handleMenuClose();
    setOutput(true);
    try {
      const { data, error } = await API.action(command);
      const lines = data?.output?.join('\n') || '';
      const failed = error || !data || data.status !== 0;
      setOutput(
        `> ${platform === 'openwrt' ? 'nfqws2-native' : 'nfqws2-asus'} ${command}\n${lines}${failed ? `\n${t(command === 'restart' ? 'restart_schedule.restart_failed' : 'restart_schedule.action_failed')}` : ''}`,
      );
      if (!failed && command === 'upgrade') setNeedReload(true);
    } catch {
      setOutput(
        t(
          command === 'restart'
            ? 'restart_schedule.restart_failed'
            : 'restart_schedule.action_failed',
        ),
      );
    } finally {
      actionInFlight.current = false;
      setActionPending(false);
      void API.invalidateStatus();
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
                {platform === 'openwrt' ? 'OpenWrt' : 'ASUS'}
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
              {canControlService && (
                <>
                  <Tooltip
                    title={t('restart_schedule.restart')}
                    enterTouchDelay={0}
                  >
                    <span>
                      <IconButton
                        size="small"
                        aria-label={t('restart_schedule.restart')}
                        disabled={!service || actionPending}
                        onClick={() => void handleMenuClick('restart')}
                        sx={{ width: 36, height: 36 }}
                      >
                        <Box
                          component="span"
                          aria-hidden="true"
                          sx={{ fontSize: 26, lineHeight: 1 }}
                        >
                          ↻
                        </Box>
                      </IconButton>
                    </span>
                  </Tooltip>
                  {authenticated && csrfToken && (
                    <Tooltip
                      title={t('restart_schedule.title')}
                      enterTouchDelay={0}
                    >
                      <IconButton
                        size="small"
                        aria-label={t('restart_schedule.title')}
                        aria-haspopup="dialog"
                        aria-expanded={scheduleOpen}
                        onClick={() => setScheduleOpen(true)}
                        sx={{ width: 36, height: 36 }}
                      >
                        <Box
                          component="span"
                          aria-hidden="true"
                          sx={{ fontSize: 21, lineHeight: 1 }}
                        >
                          ⏱
                        </Box>
                      </IconButton>
                    </Tooltip>
                  )}
                </>
              )}
              <Button
                variant="text"
                size="small"
                aria-label={t('restart_schedule.menu')}
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
                {canControlService && service && (
                  <MenuItem
                    onClick={() => handleMenuClick('restart')}
                    disabled={actionPending}
                    sx={{ fontSize: 14 }}
                  >
                    <ListItemIcon>
                      <ReplayIcon />
                    </ListItemIcon>
                    <Trans i18nKey="common.restart" />
                  </MenuItem>
                )}

                {canControlService &&
                  (service ? (
                    <MenuItem
                      onClick={() => handleMenuClick('stop')}
                      disabled={actionPending}
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
                      disabled={actionPending}
                      sx={{ fontSize: 14 }}
                    >
                      <ListItemIcon>
                        <PlayArrowIcon />
                      </ListItemIcon>
                      <Trans i18nKey="common.start" />
                    </MenuItem>
                  ))}
              </Menu>
            </Stack>
          </Stack>
        </Box>
        {auth && arkLoaded === true && (
          <Alert
            severity="error"
            sx={{ mt: 2, whiteSpace: 'normal' }}
            action={
              <Button
                color="inherit"
                size="small"
                onClick={() => setArkOpen(true)}
              >
                {t('ark.title')}
              </Button>
            }
          >
            <AlertTitle>{t('ark.runtime_loaded_title')}</AlertTitle>
            {t('ark.runtime_loaded_hint')}
          </Alert>
        )}
      </Box>

      <ThemeMenu anchorEl={themeAnchor} onClose={() => setThemeAnchor(null)} />
      {canControlService && (
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
      )}
      {scheduleOpen && (
        <RestartScheduleDialog
          csrfToken={csrfToken}
          onClose={() => setScheduleOpen(false)}
        />
      )}
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

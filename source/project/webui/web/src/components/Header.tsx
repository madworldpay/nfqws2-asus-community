import { lazy, Suspense, useRef, useState } from 'react';
import { useConfig } from '@/config/useConfig';
import CloudDoneIcon from '@mui/icons-material/CloudDone';
import CloudOffIcon from '@mui/icons-material/CloudOff';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';
import PasswordIcon from '@mui/icons-material/Password';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import SaveIcon from '@mui/icons-material/Save';
import StopCircleIcon from '@mui/icons-material/StopCircle';
import TerminalIcon from '@mui/icons-material/Terminal';
import {
  Alert,
  AlertTitle,
  Box,
  Button,
  IconButton,
  LinearProgress,
  Link,
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
import { Trans } from '@/components/Trans';

import { useAppearanceStore } from '@/store/useAppearanceStore';
import { useAppStore } from '@/store/useAppStore';

import { useStatus } from '@/hooks/useStatus';
import { useTranslation } from '@/hooks/useTranslation';

const DpiTerminalDialog = lazy(() =>
  import('@/components/DpiTerminalDialog').then((module) => ({
    default: module.DpiTerminalDialog,
  })),
);

export const Header = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();

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
  // Session CSRF protection also applies in the intentionally password-free mode.
  const canControlService = auth && isReady && (authenticated || anonym);

  const [output, setOutput] = useState<boolean | string>(false);
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [arkOpen, setArkOpen] = useState(false);
  const [requirementsOpen, setRequirementsOpen] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [shareThanks, setShareThanks] = useState(0);
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [dpiTerminalOpen, setDpiTerminalOpen] = useState(false);
  const [actionPending, setActionPending] = useState(false);
  const actionInFlight = useRef(false);
  const { appearance } = useAppearanceStore();

  const handleMenuClick = async (command: ServiceActionRequest['cmd']) => {
    if (!canControlService || actionInFlight.current) return;
    actionInFlight.current = true;
    setActionPending(true);
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
        component="header"
        sx={{
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          px: 'max(15px, 1.6vh)',
          py: 'max(15px, 1.6vh)',
          borderBottom: '1px solid',
          borderColor: 'divider',
          backgroundColor: 'background.paper',
          whiteSpace: 'nowrap',
          minHeight: {
            xs: 0,
            sm:
              appearance === 'rabbit'
                ? 'calc(203.2px + 2 * max(15px, 1.6vh))'
                : 0,
          },
          '& .MuiButton-root, & .MuiIconButton-root, & .MuiChip-root': {
            height: 36,
            minHeight: 36,
            flexShrink: 0,
          },
          '& .MuiIconButton-root': { width: 36 },
          // Reserve the desktop artwork in the header, not between button rows.
          '& .rabbit-build-stage': {
            height: 36,
            '--rabbit-button-top': '0px',
            '--rabbit-seat': '36px',
          },
          '@media (max-height: 600px)': { minHeight: 0 },
          '@media (max-width: 599.95px)': {
            px: 1.25,
            py: 1,
            '& .MuiButton-root': {
              fontSize: 12,
              px: 0.75,
              minHeight: 36,
            },
            '& .MuiButton-startIcon': { ml: 0, mr: 0.5 },
            '& .MuiIconButton-root': { width: 36, height: 36 },
            '& .MuiButton-root img': { width: 22, height: 22 },
          },
        }}
      >
        <Box
          display="flex"
          alignItems="center"
          justifyContent="space-between"
          flexWrap="wrap"
          rowGap={{ xs: 1, sm: 2 }}
          columnGap={1}
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
              flexShrink: 0,
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
          <Stack
            direction="row"
            spacing={{ xs: 0.5, sm: 0.75 }}
            useFlexGap
            flexWrap="wrap"
            flexGrow={1}
            alignItems="center"
            justifyContent="flex-end"
            sx={{ rowGap: 1, flexBasis: { xs: '100%', lg: 0 }, minWidth: 0 }}
          >
            <CurrentVersion
              sx={{ alignItems: 'center', flexGrow: 0, height: 36 }}
            />
            <Button
              variant="outlined"
              size="small"
              onClick={() => setRequirementsOpen(true)}
              startIcon={<HelpOutlineIcon />}
              sx={{
                borderWidth: 2,
                borderColor: 'primary.main',
                '&:hover': { borderWidth: 2 },
              }}
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
            {canControlService && csrfToken && (
              <Button
                variant="outlined"
                size="small"
                startIcon={<TerminalIcon />}
                aria-haspopup="dialog"
                aria-expanded={dpiTerminalOpen}
                onClick={() => setDpiTerminalOpen(true)}
              >
                {t('dpi_terminal.title')}
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
              flexGrow={0}
              justifyContent="flex-end"
            >
              {canControlService && (
                <>
                  <Tooltip title={t('common.start')} enterTouchDelay={0}>
                    <span>
                      <IconButton
                        size="small"
                        aria-label={t('common.start')}
                        disabled={service || actionPending}
                        onClick={() => void handleMenuClick('start')}
                        sx={{ width: 36, height: 36 }}
                      >
                        <PlayArrowIcon fontSize="small" />
                      </IconButton>
                    </span>
                  </Tooltip>
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
                  <Tooltip title={t('common.stop')} enterTouchDelay={0}>
                    <span>
                      <IconButton
                        size="small"
                        aria-label={t('common.stop')}
                        disabled={!service || actionPending}
                        onClick={() => void handleMenuClick('stop')}
                        sx={{ width: 36, height: 36 }}
                      >
                        <StopCircleIcon fontSize="small" />
                      </IconButton>
                    </span>
                  </Tooltip>
                  {csrfToken && (
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
      {canControlService && csrfToken && dpiTerminalOpen && (
        <Suspense
          fallback={<LinearProgress aria-label={t('dpi_terminal.loading')} />}
        >
          <DpiTerminalDialog
            csrfToken={csrfToken}
            onClose={() => setDpiTerminalOpen(false)}
          />
        </Suspense>
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

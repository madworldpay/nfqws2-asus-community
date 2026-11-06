import { useEffect, useRef, useState } from 'react';
import CloseIcon from '@mui/icons-material/Close';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';
import MoreHorizIcon from '@mui/icons-material/MoreHoriz';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  IconButton,
  LinearProgress,
  Menu,
  MenuItem,
  Stack,
  Tooltip,
  Typography,
  useMediaQuery,
} from '@mui/material';
import { FitAddon } from '@xterm/addon-fit';
import { Terminal } from '@xterm/xterm';

import '@xterm/xterm/css/xterm.css';

import {
  DpiError,
  DpiTerminalSession,
  getDpiStatus,
  getDpiTerminalInfo,
  installDpi,
  removeDpiDetector,
  type DpiTerminalInfo,
  type DpiTerminalState,
} from '@/api/dpiClient';
import { newSupportSubmissionId } from '@/api/supportReport';

import { DpiSavedReports } from '@/components/DpiSavedReports';

import { useTranslation } from '@/hooks/useTranslation';

import { bindDpiTerminalScrolling } from '@/utils/dpiTerminalScroll';

const NativeTerminal = ({
  csrfToken,
  language,
  onState,
  onError,
}: {
  csrfToken: string;
  language: 'ru' | 'en';
  onState: (state: DpiTerminalState) => void;
  onError: (code: string) => void;
}) => {
  const { t } = useTranslation();
  const host = useRef<HTMLDivElement>(null);
  const terminal = useRef<Terminal | null>(null);
  const session = useRef<DpiTerminalSession | null>(null);
  const [running, setRunning] = useState(false);
  useEffect(() => {
    if (!host.current) return;
    let disposed = false;
    const term = new Terminal({
      fontSize: window.innerWidth < 600 ? 11 : 14,
      fontFamily: 'ui-monospace, SFMono-Regular, Consolas, monospace',
      cols: 100,
      rows: 24,
      scrollback: 10000,
      scrollSensitivity: 3,
      allowProposedApi: false,
      allowTransparency: false,
      convertEol: false,
      cursorBlink: true,
      theme: { background: '#101418', foreground: '#edf1f7' },
    });
    // The Detector receives native bytes. Do not enable browser clipboard or
    // hyperlink addons. Ignore native OSC 8 links and OSC 52 clipboard writes.
    const ignoredSequences = [8, 52].map((code) =>
      term.parser.registerOscHandler(code, () => true),
    );
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(host.current);
    const releaseScrolling = bindDpiTerminalScrolling(term, host.current);
    terminal.current = term;
    const owner = new DpiTerminalSession(csrfToken, language, {
      output: (bytes) => {
        if (!disposed) term.write(bytes);
      },
      state: (state) => {
        if (!disposed) {
          setRunning(state === 'running');
          onState(state);
        }
      },
      error: (error) => {
        if (!disposed) onError(error.code);
      },
    });
    session.current = owner;
    const dimensions = () => {
      term.options.fontSize = window.innerWidth < 600 ? 11 : 14;
      let proposed = fit.proposeDimensions();
      // Keep the complete native menu (including its title) in the viewport.
      // Size the grid to the visible viewport. Growing the host beyond it
      // hides xterm's real history scrollbar behind a short outer scrollbar.
      while (proposed && proposed.rows < 28 && term.options.fontSize! > 10) {
        term.options.fontSize = term.options.fontSize! - 1;
        proposed = fit.proposeDimensions();
      }
      const cols = Math.max(80, Math.min(240, proposed?.cols ?? 100));
      const rows = Math.max(28, Math.min(80, proposed?.rows ?? 28));
      return { cols, rows };
    };
    const initial = dimensions();
    term.resize(initial.cols, initial.rows);
    const input = term.onData((data) => owner.input(data));
    // Dialog focus belongs to its terminal; Escape must reach the native menu.
    term.focus();
    // StrictMode cleans up its first mount before this task runs. A discarded
    // mount must never start and then stop the real mount's shared session.
    const startTimer = setTimeout(() => {
      void owner.start(initial.cols, initial.rows);
    }, 0);
    const leave = () => {
      void owner.close();
    };
    window.addEventListener('pagehide', leave);
    let frame = 0;
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        if (disposed) return;
        const size = dimensions();
        if (size.cols !== term.cols || size.rows !== term.rows) {
          term.resize(size.cols, size.rows);
          owner.resize(size.cols, size.rows);
        }
      });
    });
    observer.observe(host.current);
    return () => {
      disposed = true;
      observer.disconnect();
      window.removeEventListener('pagehide', leave);
      cancelAnimationFrame(frame);
      input.dispose();
      releaseScrolling();
      clearTimeout(startTimer);
      ignoredSequences.forEach((handler) => handler.dispose());
      void owner.close();
      term.dispose();
      terminal.current = null;
      session.current = null;
    };
  }, [csrfToken, language, onState, onError]);
  const keys = [
    { key: 'up', label: '↑', data: '\u001b[A' },
    { key: 'down', label: '↓', data: '\u001b[B' },
    { key: 'left', label: '←', data: '\u001b[D' },
    { key: 'right', label: '→', data: '\u001b[C' },
    { key: 'space', label: t('dpi_terminal.space'), data: ' ' },
    { key: 'enter', label: 'Enter', data: '\r' },
    { key: 'escape', label: 'Esc', data: '\u001b' },
    { key: 'save', label: t('dpi_terminal.save_key'), data: 's' },
    { key: 'quit', label: t('dpi_terminal.quit_key'), data: 'q' },
  ] as const;
  return (
    <Stack spacing={1} sx={{ minHeight: 0, flex: '1 0 auto' }}>
      <Box
        sx={{
          bgcolor: '#101418',
          borderRadius: 1,
          p: 1,
          overflowX: 'auto',
          overflowY: 'hidden',
          flex: '1 0 auto',
          minHeight: 368,
          height: { xs: '48dvh', sm: '55dvh' },
          '& .xterm': { height: '100%' },
          '& .xterm-viewport': { overflow: 'hidden' },
          '& .xterm-scrollable-element > .scrollbar.vertical': {
            opacity: 1,
            pointerEvents: 'auto',
          },
        }}
      >
        <Box
          ref={host}
          aria-label={t('dpi_terminal.screen')}
          sx={{
            height: '100%',
            minHeight: 0,
            minWidth: { xs: 660, sm: 840 },
            touchAction: 'pan-x pinch-zoom',
          }}
        />
      </Box>
      <Stack
        direction="row"
        spacing={0.75}
        useFlexGap
        flexWrap="wrap"
        aria-label={t('dpi_terminal.scroll_controls')}
      >
        <Button
          size="small"
          variant="outlined"
          onClick={() => terminal.current?.scrollToTop()}
        >
          {t('dpi_terminal.scroll_top')}
        </Button>
        <Button
          size="small"
          variant="outlined"
          onClick={() => terminal.current?.scrollPages(-1)}
        >
          {t('dpi_terminal.scroll_up')}
        </Button>
        <Button
          size="small"
          variant="outlined"
          onClick={() => terminal.current?.scrollPages(1)}
        >
          {t('dpi_terminal.scroll_down')}
        </Button>
        <Button
          size="small"
          variant="outlined"
          onClick={() => terminal.current?.scrollToBottom()}
        >
          {t('dpi_terminal.scroll_bottom')}
        </Button>
      </Stack>
      <Stack
        direction="row"
        spacing={0.75}
        useFlexGap
        flexWrap="wrap"
        aria-label={t('dpi_terminal.controls')}
      >
        {keys.map(({ key, label, data }) => (
          <Button
            key={key}
            size="small"
            variant="outlined"
            disabled={!running}
            aria-label={t(`dpi_terminal.key_${key}`)}
            onClick={() => {
              session.current?.input(data);
              if (window.matchMedia('(pointer: fine)').matches)
                terminal.current?.focus();
            }}
            sx={{ minWidth: 44, minHeight: 40 }}
          >
            {label}
          </Button>
        ))}
      </Stack>
    </Stack>
  );
};

export const DpiTerminalDialog = ({
  csrfToken,
  onClose,
}: {
  csrfToken: string;
  onClose: VoidFunction;
}) => {
  const { t, langcode } = useTranslation();
  const fullScreen = useMediaQuery('(max-width:599.95px)');
  const [info, setInfo] = useState<DpiTerminalInfo | null>(null);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [terminalAttempt, setTerminalAttempt] = useState(0);
  const [confirmInstall, setConfirmInstall] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [moreAnchor, setMoreAnchor] = useState<HTMLElement | null>(null);
  const [deleteReports, setDeleteReports] = useState(false);
  const [removing, setRemoving] = useState(false);
  const removalInFlight = useRef(false);
  const [installing, setInstalling] = useState(false);
  const [installPending, setInstallPending] = useState(false);
  const [terminalState, setTerminalState] = useState<DpiTerminalState | null>(
    null,
  );
  const installInFlight = useRef(false);
  const mounted = useRef(true);
  const [language] = useState(langcode);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  useEffect(() => {
    let active = true;
    getDpiTerminalInfo(csrfToken).then(
      (value) => {
        if (active) setInfo(value);
      },
      (error) => {
        if (active)
          setError(error instanceof DpiError ? error.code : 'request_failed');
      },
    );
    return () => {
      active = false;
    };
  }, [csrfToken, attempt]);
  useEffect(() => {
    if (!installing) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const status = await getDpiStatus(csrfToken);
        if (!active) return;
        if (status.active?.kind === 'install') {
          timer = setTimeout(() => void poll(), 1500);
          return;
        }
        setInstalling(false);
        if (!status.installed.installed) {
          setError('install_failed');
          return;
        }
        setInfo(null);
        setAttempt((value) => value + 1);
      } catch (error) {
        if (active) {
          setInstalling(false);
          setError(error instanceof DpiError ? error.code : 'request_failed');
        }
      }
    };
    void poll();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [csrfToken, installing]);
  const install = async () => {
    if (installInFlight.current || installing) return;
    installInFlight.current = true;
    setInstallPending(true);
    setError('');
    try {
      await installDpi(csrfToken, newSupportSubmissionId());
      if (mounted.current) {
        setConfirmInstall(false);
        setInstalling(true);
      }
    } catch (error) {
      if (mounted.current)
        setError(error instanceof DpiError ? error.code : 'request_failed');
    } finally {
      installInFlight.current = false;
      if (mounted.current) setInstallPending(false);
    }
  };
  const remove = async () => {
    if (removalInFlight.current) return;
    removalInFlight.current = true;
    setRemoving(true);
    setError('');
    try {
      await removeDpiDetector(csrfToken, deleteReports);
      if (mounted.current) {
        setConfirmRemove(false);
        setTerminalState(null);
        setInfo(null);
        setAttempt((value) => value + 1);
      }
    } catch (error) {
      if (mounted.current)
        setError(error instanceof DpiError ? error.code : 'request_failed');
    } finally {
      removalInFlight.current = false;
      if (mounted.current) setRemoving(false);
    }
  };
  const message = [
    'unauthorized',
    'forbidden',
    'auth_required',
    'csrf_failed',
    'origin_rejected',
  ].includes(error)
    ? t('dpi_terminal.session_error')
    : ['busy', 'terminal_busy', 'dpi_busy', 'job_busy'].includes(error)
      ? t('dpi_terminal.busy')
      : error === 'input_limit'
        ? t('dpi_terminal.input_limit')
        : error === 'install_failed'
          ? t('dpi_terminal.install_failed')
          : error === 'reports_not_removed'
            ? t('dpi_terminal.reports_not_removed')
            : t('dpi_terminal.request_failed');
  const ready = info?.available && info.installed && !installing && !removing;
  return (
    <Dialog
      open
      onClose={(_event, reason) => {
        if (!removing && reason !== 'escapeKeyDown') onClose();
      }}
      fullScreen={fullScreen}
      fullWidth
      maxWidth="lg"
      aria-labelledby="dpi-terminal-title"
      aria-describedby="dpi-terminal-description"
      slotProps={{
        paper: {
          sx: {
            m: { xs: 0, sm: 2 },
            height: { xs: '100%', sm: 'auto' },
            maxHeight: { xs: '100%', sm: 'calc(100% - 32px)' },
          },
        },
      }}
    >
      <DialogTitle
        sx={{ display: 'flex', alignItems: 'center', gap: 1, py: 1.25 }}
      >
        <Box component="span" id="dpi-terminal-title" sx={{ flex: 1 }}>
          {t('dpi_terminal.title')}
        </Box>
        <Tooltip
          title={t('dpi_terminal.help')}
          enterTouchDelay={0}
          leaveTouchDelay={8000}
        >
          <IconButton
            aria-label={t('dpi_terminal.help_title')}
            aria-expanded={helpOpen}
            aria-controls="dpi-detector-help"
            onClick={() => setHelpOpen((value) => !value)}
          >
            <HelpOutlineIcon />
          </IconButton>
        </Tooltip>
        <IconButton
          disabled={removing}
          onClick={onClose}
          aria-label={t('common.close')}
        >
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      {((!info && !error) || installing || installPending) && (
        <LinearProgress
          aria-label={t(
            installing || installPending
              ? 'share.installing'
              : 'dpi_terminal.loading',
          )}
        />
      )}
      <DialogContent
        sx={{
          display: 'flex',
          flexDirection: 'column',
          gap: 1.5,
          minHeight: 0,
          px: { xs: 1, sm: 2 },
          pt: 0.5,
        }}
      >
        <Typography id="dpi-terminal-description" variant="body2">
          {t('dpi_terminal.description')}
        </Typography>
        <Accordion
          expanded={helpOpen}
          onChange={(_, expanded) => setHelpOpen(expanded)}
          disableGutters
          sx={{ flexShrink: 0 }}
        >
          <AccordionSummary
            expandIcon={<ExpandMoreIcon />}
            id="dpi-detector-help-title"
            aria-controls="dpi-detector-help"
          >
            <Typography variant="body2">
              {t('dpi_terminal.guide_title')}
            </Typography>
          </AccordionSummary>
          <AccordionDetails id="dpi-detector-help">
            <Stack spacing={1.5}>
              {(
                [
                  'purpose',
                  'install',
                  'run',
                  'compare',
                  'results',
                  'save',
                ] as const
              ).map((item) => (
                <Typography variant="body2" key={item}>
                  {t(`dpi_terminal.guide_${item}`)}
                </Typography>
              ))}
            </Stack>
          </AccordionDetails>
        </Accordion>
        {error && (
          <Alert severity={error === 'input_limit' ? 'warning' : 'error'}>
            {message}
          </Alert>
        )}
        {info &&
          !info.installed &&
          info.code !== 'unsupported_abi' &&
          !installing &&
          (confirmInstall ? (
            <Alert severity="info">
              {t('share.install_hint')}
              <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                <Button
                  variant="contained"
                  disabled={installPending}
                  onClick={() => void install()}
                >
                  {t('share.agree_install')}
                </Button>
                <Button
                  disabled={installPending}
                  onClick={() => setConfirmInstall(false)}
                >
                  {t('common.cancel')}
                </Button>
              </Stack>
            </Alert>
          ) : (
            <Button
              variant="contained"
              onClick={() => setConfirmInstall(true)}
              sx={{ alignSelf: 'flex-start' }}
            >
              {t('share.install_dpi')}
            </Button>
          ))}
        {installing && <Alert severity="info">{t('share.installing')}</Alert>}
        {info?.installed && !info.available && (
          <Alert severity="warning">{t('dpi_terminal.unavailable')}</Alert>
        )}
        {info?.code === 'unsupported_abi' && (
          <Alert severity="info">{t('dpi_terminal.unsupported_abi')}</Alert>
        )}
        {ready && (
          <NativeTerminal
            key={terminalAttempt}
            csrfToken={csrfToken}
            language={language}
            onState={setTerminalState}
            onError={setError}
          />
        )}
        {!confirmRemove && terminalState && terminalState !== 'running' && (
          <Alert
            severity={
              terminalState === 'exited' || terminalState === 'stopped'
                ? 'info'
                : 'warning'
            }
          >
            {t(`dpi_terminal.state_${terminalState}`)}
          </Alert>
        )}
        {ready && (
          <Typography variant="caption">
            {t('dpi_terminal.saved_hint')}
          </Typography>
        )}
        <DpiSavedReports
          key={attempt}
          csrfToken={csrfToken}
          disabled={removing || confirmRemove}
        />
      </DialogContent>
      <DialogActions sx={{ px: 2, flexWrap: 'wrap' }}>
        {info?.installed && !confirmRemove && !installing && (
          <Button
            startIcon={<MoreHorizIcon />}
            sx={{ mr: 'auto' }}
            aria-haspopup="menu"
            aria-expanded={!!moreAnchor}
            aria-controls={moreAnchor ? 'dpi-detector-more-menu' : undefined}
            onClick={(event) => setMoreAnchor(event.currentTarget)}
          >
            {t('dpi_terminal.more')}
          </Button>
        )}
        {ready && terminalState && terminalState !== 'running' && (
          <Button
            onClick={() => {
              setError('');
              setTerminalState(null);
              setTerminalAttempt((value) => value + 1);
            }}
          >
            {t('dpi_terminal.reopen')}
          </Button>
        )}
        {!ready && !confirmRemove && !installing && !installPending && (
          <Button
            onClick={() => {
              setError('');
              setInfo(null);
              setAttempt((value) => value + 1);
            }}
          >
            {t('dpi_terminal.retry')}
          </Button>
        )}
        <Button disabled={removing} onClick={onClose}>
          {t('common.close')}
        </Button>
      </DialogActions>
      <Menu
        id="dpi-detector-more-menu"
        anchorEl={moreAnchor}
        open={!!moreAnchor}
        onClose={() => setMoreAnchor(null)}
      >
        <MenuItem
          onClick={() => {
            setMoreAnchor(null);
            setDeleteReports(false);
            setError('');
            setConfirmRemove(true);
          }}
          sx={{ color: 'error.main' }}
        >
          {t('dpi_terminal.remove')}
        </MenuItem>
      </Menu>
      <Dialog
        open={confirmRemove}
        onClose={() => {
          if (!removing) setConfirmRemove(false);
        }}
        aria-labelledby="dpi-remove-title"
      >
        <DialogTitle id="dpi-remove-title">
          {t('dpi_terminal.remove')}
        </DialogTitle>
        <DialogContent>
          {confirmRemove && (
            <Alert severity="warning">
              <Typography variant="body2">
                {t('dpi_terminal.remove_confirm')}
              </Typography>
              <FormControlLabel
                control={
                  <Checkbox
                    checked={deleteReports}
                    disabled={removing}
                    onChange={(_, value) => setDeleteReports(value)}
                  />
                }
                label={t('dpi_terminal.remove_reports')}
              />
              <Typography variant="body2">
                {t(
                  deleteReports
                    ? 'dpi_terminal.remove_with_reports'
                    : 'dpi_terminal.remove_keep_reports',
                )}
              </Typography>
              <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                <Button
                  autoFocus
                  disabled={removing}
                  onClick={() => {
                    setConfirmRemove(false);
                    setError('');
                  }}
                >
                  {t('common.cancel')}
                </Button>
                <Button
                  color="error"
                  variant="contained"
                  disabled={removing}
                  onClick={() => void remove()}
                >
                  {t(
                    removing ? 'dpi_terminal.removing' : 'dpi_terminal.remove',
                  )}
                </Button>
              </Stack>
            </Alert>
          )}
        </DialogContent>
      </Dialog>
    </Dialog>
  );
};

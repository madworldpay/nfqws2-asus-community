import { useEffect, useState } from 'react';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import DownloadIcon from '@mui/icons-material/Download';
import RefreshIcon from '@mui/icons-material/Refresh';
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  Link,
  MenuItem,
  Select,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';

import { getMtprotoAddresses } from '@/api/mtprotoAddresses';

import { MtprotoRouterInstall } from '@/components/MtprotoRouterInstall';
import { FrankShareButton } from '@/components/ShareDialog';

import { useTranslation } from '@/hooks/useTranslation';

import { copyText } from '@/utils/copyText';
import {
  buildMtprotoCompose,
  buildMtprotoInstall,
  createMtprotoSecret,
  MTPROTO_DOCKER_IMAGE,
  mtprotoDiagnostics,
  mtprotoLink,
  suggestMtprotoServer,
  validateMtproto,
  type MtprotoAddresses,
  type MtprotoMethod,
} from '@/utils/mtprotoInstall';

function CopyField({
  label,
  value,
  lines = 1,
}: {
  label: string;
  value: string;
  lines?: number;
}) {
  const { t } = useTranslation();
  const [result, setResult] = useState<'copied' | 'copy_failed' | ''>('');
  return (
    <Stack spacing={0.5}>
      <TextField
        label={label}
        value={value}
        multiline
        minRows={lines}
        maxRows={Math.max(lines, 5)}
        fullWidth
        slotProps={{
          input: {
            readOnly: true,
            sx: {
              fontFamily: 'monospace',
              fontSize: 12,
              overflowWrap: 'anywhere',
            },
          },
        }}
      />
      <Button
        size="small"
        aria-label={`${t('mtproto.copy')}: ${label}`}
        startIcon={<ContentCopyIcon />}
        sx={{ alignSelf: 'flex-start' }}
        onClick={() => {
          void copyText(value).then((ok) =>
            setResult(ok ? 'copied' : 'copy_failed'),
          );
        }}
      >
        {t('mtproto.copy')}
      </Button>
      {result && (
        <Typography
          role="status"
          variant="caption"
          color={result === 'copied' ? 'success.main' : 'error.main'}
        >
          {t(`mtproto.${result}`)}
        </Typography>
      )}
    </Stack>
  );
}

export function MtprotoInstallDialog({
  onClose,
  csrfToken,
  routerMode,
}: {
  onClose: VoidFunction;
  csrfToken?: string;
  routerMode?: 'install' | 'login';
}) {
  const { t, langcode } = useTranslation();
  const [action, setAction] = useState<'install' | 'update' | 'remove'>(
    'install',
  );
  const [withDocker, setWithDocker] = useState(false);
  const [dockerMode, setDockerMode] = useState<'portainer' | 'terminal'>(
    'portainer',
  );
  const [native, setNative] = useState<'entware' | 'linux'>('entware');
  const method: MtprotoMethod = withDocker ? 'docker' : native;
  const direct = action === 'install' && method === 'entware' && !!routerMode;
  const [addresses, setAddresses] = useState<MtprotoAddresses>({
    router: null,
    docker: null,
  });
  const [edited, setEdited] = useState<Partial<Record<MtprotoMethod, string>>>(
    {},
  );
  const suggested = suggestMtprotoServer(
    method,
    addresses,
    window.location.hostname,
  );
  const server = edited[method] ?? suggested;
  useEffect(() => {
    if (!csrfToken) return;
    let active = true;
    void getMtprotoAddresses(csrfToken)
      .then((value) => {
        if (active) setAddresses(value);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [csrfToken]);
  const [port, setPort] = useState('1443');
  const [key, setKey] = useState(() => {
    try {
      return createMtprotoSecret();
    } catch {
      return '';
    }
  });
  const values = { server, port, secret: key };
  const errors = validateMtproto(values);
  const lowPort =
    action === 'install' && method !== 'docker' && Number(port) < 1024;
  const ready =
    action === 'install'
      ? !Object.keys(errors).length && !lowPort
      : !errors.server;
  const script = ready
    ? buildMtprotoInstall(method, values, langcode, action)
    : '';
  const portainer = withDocker && dockerMode === 'portainer';
  const installText =
    ready && portainer && action === 'install'
      ? buildMtprotoCompose(values)
      : script;
  const link = ready && action === 'install' ? mtprotoLink(values) : '';
  const download = () => {
    const url = URL.createObjectURL(
      new Blob([installText], { type: 'text/plain;charset=utf-8' }),
    );
    const a = document.createElement('a');
    a.href = url;
    a.download =
      portainer && action === 'install'
        ? 'compose.yaml'
        : `nfqws-mtproto-${method}.sh`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return (
    <Dialog open maxWidth="sm" fullWidth onClose={onClose}>
      <DialogTitle>{t('mtproto.title')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <Typography variant="body2">{t('mtproto.intro')}</Typography>
          <ToggleButtonGroup
            exclusive
            fullWidth
            value={action}
            aria-label={t('mtproto.action')}
            onChange={(_, value: 'install' | 'update' | 'remove' | null) => {
              if (value) setAction(value);
            }}
          >
            <ToggleButton value="install">
              {t('mtproto.action_install')}
            </ToggleButton>
            <ToggleButton value="update">
              {t('mtproto.action_update')}
            </ToggleButton>
            <ToggleButton value="remove">
              {t('mtproto.action_remove')}
            </ToggleButton>
          </ToggleButtonGroup>
          {action !== 'install' && (
            <Alert severity="info">{t('mtproto.owned_only')}</Alert>
          )}
          <ToggleButtonGroup
            exclusive
            fullWidth
            value={withDocker ? 'docker' : 'native'}
            onChange={(_, value: string | null) => {
              if (value) setWithDocker(value === 'docker');
            }}
            aria-label={t('mtproto.method')}
          >
            <ToggleButton value="native">
              {t('mtproto.without_docker')}
            </ToggleButton>
            <ToggleButton value="docker">
              {t('mtproto.with_docker')}
            </ToggleButton>
          </ToggleButtonGroup>
          {withDocker && (
            <ToggleButtonGroup
              exclusive
              fullWidth
              value={dockerMode}
              aria-label={t('mtproto.docker_mode')}
              onChange={(_, value: 'portainer' | 'terminal' | null) => {
                if (value) setDockerMode(value);
              }}
            >
              <ToggleButton value="portainer">Portainer</ToggleButton>
              <ToggleButton value="terminal">
                {t('mtproto.terminal')}
              </ToggleButton>
            </ToggleButtonGroup>
          )}
          {!withDocker && (
            <FormControl fullWidth>
              <InputLabel id="mtproto-target-label">
                {t('mtproto.device')}
              </InputLabel>
              <Select
                labelId="mtproto-target-label"
                label={t('mtproto.device')}
                value={native}
                onChange={(e) =>
                  setNative(e.target.value as 'entware' | 'linux')
                }
              >
                <MenuItem value="entware">ASUS / Entware</MenuItem>
                <MenuItem value="linux">Linux / systemd</MenuItem>
              </Select>
            </FormControl>
          )}
          <Alert severity="info">{t(`mtproto.help_${method}`)}</Alert>
          <Typography variant="body2">
            {t(
              `mtproto.${portainer ? 'portainer_update_help' : 'update_help'}`,
            )}
          </Typography>
          {portainer && (
            <CopyField
              label={t('mtproto.image_for_update')}
              value={MTPROTO_DOCKER_IMAGE}
            />
          )}
          {action !== 'remove' && !(portainer && action === 'update') && (
            <>
              <TextField
                label={t(`mtproto.server_${method}`)}
                placeholder="proxy.example.org"
                value={server}
                onChange={(e) =>
                  setEdited((old) => ({ ...old, [method]: e.target.value }))
                }
                error={!!server && !!errors.server}
                helperText={
                  server && errors.server
                    ? t('mtproto.invalid_server')
                    : `${t(`mtproto.server_help_${method}`)} ${t('mtproto.server_remote_help')}`
                }
                fullWidth
                autoComplete="off"
              />
              {server && edited[method] === undefined && (
                <Typography variant="caption" color="text.secondary">
                  {t('mtproto.address_detected')}
                </Typography>
              )}
              {action === 'install' && (
                <TextField
                  label={t('mtproto.port')}
                  value={port}
                  onChange={(e) => setPort(e.target.value)}
                  error={!!errors.port || lowPort}
                  helperText={
                    lowPort ? t('mtproto.high_port') : t('mtproto.port_help')
                  }
                  fullWidth
                  slotProps={{ htmlInput: { inputMode: 'numeric' } }}
                />
              )}
              {!key && action === 'install' && (
                <Alert severity="error">{t('mtproto.random_failed')}</Alert>
              )}
              {ready && (
                <>
                  {action === 'install' && (
                    <>
                      <CopyField
                        key={key}
                        label={t('mtproto.secret')}
                        value={key}
                      />
                      <Button
                        size="small"
                        startIcon={<RefreshIcon />}
                        sx={{ alignSelf: 'flex-start' }}
                        onClick={() => {
                          try {
                            setKey(createMtprotoSecret());
                          } catch {
                            setKey('');
                          }
                        }}
                      >
                        {t('mtproto.new_key')}
                      </Button>
                    </>
                  )}
                  <Typography variant="subtitle2">
                    {t('mtproto.step_install')}
                  </Typography>
                  {direct && (
                    <MtprotoRouterInstall
                      csrf={routerMode === 'install' ? csrfToken : undefined}
                      values={values}
                    />
                  )}
                  <Box component={direct ? 'details' : 'div'}>
                    {direct && (
                      <Box component="summary" sx={{ cursor: 'pointer' }}>
                        {t('mtproto.router_manual')}
                      </Box>
                    )}
                    <Stack spacing={1.5} sx={{ pt: direct ? 1.5 : 0 }}>
                      <Typography variant="body2">
                        {t(`mtproto.run_${portainer ? 'portainer' : method}`)}
                      </Typography>
                      <CopyField
                        key={installText}
                        label={t(
                          `mtproto.${portainer ? 'compose' : 'command'}`,
                        )}
                        value={installText}
                        lines={4}
                      />
                      <Button
                        startIcon={<DownloadIcon />}
                        onClick={download}
                        sx={{ alignSelf: 'flex-start' }}
                      >
                        {t(
                          `mtproto.${portainer ? 'download_compose' : 'download'}`,
                        )}
                      </Button>
                      <FrankShareButton
                        disabled={!ready}
                        load={() => ({
                          blob: new Blob([installText], {
                            type: 'text/plain;charset=utf-8',
                          }),
                          filename:
                            portainer && action === 'install'
                              ? 'compose.yaml'
                              : `nfqws-mtproto-${method}.sh`,
                        })}
                      />
                      {action === 'install' && (
                        <>
                          <Typography variant="subtitle2">
                            {t('mtproto.step_connect')}
                          </Typography>
                          <Typography variant="body2">
                            {t('mtproto.connect_help')}
                          </Typography>
                          <CopyField
                            key={link}
                            label={t('mtproto.link')}
                            value={link}
                          />
                          <Link
                            href={link}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            {t('mtproto.open_telegram')}
                          </Link>
                        </>
                      )}
                      <CopyField
                        key={method}
                        label={t('mtproto.diagnostics')}
                        value={mtprotoDiagnostics(method)}
                        lines={2}
                      />
                      {action === 'install' && (
                        <Alert severity="warning">{t('mtproto.private')}</Alert>
                      )}
                    </Stack>
                  </Box>
                </>
              )}
            </>
          )}
          {action === 'remove' &&
            (portainer ? (
              <Alert severity="info">{t('mtproto.portainer_remove')}</Alert>
            ) : (
              <>
                <Typography variant="body2">
                  {t('mtproto.remove_help')}
                </Typography>
                <CopyField
                  label={t('mtproto.remove_command')}
                  value={buildMtprotoInstall(
                    method,
                    {
                      server: 'localhost',
                      port: '1443',
                      secret: 'dd' + '0'.repeat(32),
                    },
                    langcode,
                    'remove',
                  )}
                  lines={4}
                />
              </>
            ))}
          <Typography variant="caption" color="text.secondary">
            {t('mtproto.source')}{' '}
            <Link
              href="https://github.com/Flowseal/tg-ws-proxy"
              target="_blank"
              rel="noopener noreferrer"
            >
              Flowseal/tg-ws-proxy
            </Link>{' '}
            {withDocker && (
              <>
                ·{' '}
                <Link
                  href="https://github.com/LordArrin/tg-ws-proxy-docker"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  LordArrin Docker
                </Link>{' '}
              </>
            )}
            · MIT
          </Typography>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('mtproto.close')}</Button>
      </DialogActions>
    </Dialog>
  );
}

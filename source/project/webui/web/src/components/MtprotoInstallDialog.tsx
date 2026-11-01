import { useEffect, useState } from 'react';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import DownloadIcon from '@mui/icons-material/Download';
import RefreshIcon from '@mui/icons-material/Refresh';
import {
  Alert,
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

import { useTranslation } from '@/hooks/useTranslation';

import { copyText } from '@/utils/copyText';
import {
  buildMtprotoCompose,
  buildMtprotoInstall,
  createMtprotoSecret,
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
}: {
  onClose: VoidFunction;
  csrfToken?: string;
}) {
  const { t, langcode } = useTranslation();
  const [withDocker, setWithDocker] = useState(false);
  const [dockerMode, setDockerMode] = useState<'portainer' | 'terminal'>(
    'portainer',
  );
  const [native, setNative] = useState<'entware' | 'linux'>('entware');
  const method: MtprotoMethod = withDocker ? 'docker' : native;
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
  const lowPort = method !== 'docker' && Number(port) < 1024;
  const ready = !Object.keys(errors).length && !lowPort;
  const script = ready ? buildMtprotoInstall(method, values, langcode) : '';
  const portainer = withDocker && dockerMode === 'portainer';
  const installText = ready && portainer ? buildMtprotoCompose(values) : script;
  const link = ready ? mtprotoLink(values) : '';
  const download = () => {
    const url = URL.createObjectURL(
      new Blob([installText], { type: 'text/plain;charset=utf-8' }),
    );
    const a = document.createElement('a');
    a.href = url;
    a.download = portainer ? 'compose.yaml' : `nfqws-mtproto-${method}.sh`;
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
          {!key && <Alert severity="error">{t('mtproto.random_failed')}</Alert>}
          {ready && (
            <>
              <CopyField key={key} label={t('mtproto.secret')} value={key} />
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
              <Typography variant="subtitle2">
                {t('mtproto.step_install')}
              </Typography>
              <Typography variant="body2">
                {t(`mtproto.run_${portainer ? 'portainer' : method}`)}
              </Typography>
              <CopyField
                key={installText}
                label={t(`mtproto.${portainer ? 'compose' : 'command'}`)}
                value={installText}
                lines={4}
              />
              <Button
                startIcon={<DownloadIcon />}
                onClick={download}
                sx={{ alignSelf: 'flex-start' }}
              >
                {t(`mtproto.${portainer ? 'download_compose' : 'download'}`)}
              </Button>
              <Typography variant="subtitle2">
                {t('mtproto.step_connect')}
              </Typography>
              <Typography variant="body2">
                {t('mtproto.connect_help')}
              </Typography>
              <CopyField key={link} label={t('mtproto.link')} value={link} />
              <Link href={link} target="_blank" rel="noopener noreferrer">
                {t('mtproto.open_telegram')}
              </Link>
              <CopyField
                key={method}
                label={t('mtproto.diagnostics')}
                value={mtprotoDiagnostics(method)}
                lines={2}
              />
              <Alert severity="warning">{t('mtproto.private')}</Alert>
            </>
          )}
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

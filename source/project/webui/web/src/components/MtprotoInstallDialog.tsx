import { useState } from 'react';
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

import { useTranslation } from '@/hooks/useTranslation';

import { copyText } from '@/utils/copyText';
import {
  buildMtprotoInstall,
  createMtprotoSecret,
  mtprotoDiagnostics,
  mtprotoLink,
  validateMtproto,
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

export function MtprotoInstallDialog({ onClose }: { onClose: VoidFunction }) {
  const { t, langcode } = useTranslation();
  const [withDocker, setWithDocker] = useState(false);
  const [native, setNative] = useState<'entware' | 'linux'>('entware');
  const method: MtprotoMethod = withDocker ? 'docker' : native;
  const [server, setServer] = useState('');
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
  const link = ready ? mtprotoLink(values) : '';
  const download = () => {
    const url = URL.createObjectURL(
      new Blob([script], { type: 'text/plain;charset=utf-8' }),
    );
    const a = document.createElement('a');
    a.href = url;
    a.download = `nfqws-mtproto-${method}.sh`;
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
            label={t('mtproto.server')}
            placeholder="proxy.example.org"
            value={server}
            onChange={(e) => setServer(e.target.value)}
            error={!!server && !!errors.server}
            helperText={
              server && errors.server
                ? t('mtproto.invalid_server')
                : t('mtproto.server_help')
            }
            fullWidth
            autoComplete="off"
          />
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
                {t(`mtproto.run_${method}`)}
              </Typography>
              <CopyField
                key={script}
                label={t('mtproto.command')}
                value={script}
                lines={4}
              />
              <Button
                startIcon={<DownloadIcon />}
                onClick={download}
                sx={{ alignSelf: 'flex-start' }}
              >
                {t('mtproto.download')}
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

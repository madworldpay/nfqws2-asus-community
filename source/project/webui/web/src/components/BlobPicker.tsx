import { useId, useRef, useState, type ChangeEvent } from 'react';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import UploadFileIcon from '@mui/icons-material/UploadFile';
import {
  Alert,
  Box,
  Button,
  Stack,
  TextField,
  Typography,
} from '@mui/material';

import {
  loadBlobInventory,
  uploadBlob,
  type BlobFile,
  type BlobInventory,
} from '@/api/blobClient';
import { ShareError } from '@/api/shareClient';

import { useStatus } from '@/hooks/useStatus';
import { useTranslation } from '@/hooks/useTranslation';

import {
  parseBlobBindings,
  replaceBlobBinding,
  type BlobBinding,
} from '@/utils/blobBindings';

export function BlobPicker({
  value,
  getValue,
  onChange,
  disabled = false,
}: {
  value: string;
  getValue: () => string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  const { csrfToken } = useStatus();
  const { t, langcode } = useTranslation();
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const pending = useRef(false);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [inventory, setInventory] = useState<BlobInventory | null>(null);
  const [error, setError] = useState('');
  const [uploaded, setUploaded] = useState('');
  const parsed = parseBlobBindings(value);

  const format = (file: BlobFile) =>
    file.format === 'other'
      ? t('blobs.format_other')
      : file.format.toUpperCase();
  const describe = (file: BlobFile) => {
    const label = file.label?.[langcode];
    return `${label ? `${label} — ` : ''}${file.name} · ${format(file)}`;
  };
  const failure = (problem: unknown) => {
    const code = problem instanceof ShareError ? problem.code : '';
    if (['busy', 'restore_required', 'invalid_state'].includes(code))
      return t('blobs.error_busy');
    if (code === 'file_too_large') return t('blobs.error_large');
    if (code === 'empty_file') return t('blobs.error_empty');
    if (['invalid_name', 'invalid_request', 'invalid_blob'].includes(code))
      return t('blobs.error_file');
    if (['unauthorized', 'forbidden'].includes(code))
      return t('blobs.error_auth');
    if (code === 'insufficient_space') return t('blobs.error_space');
    return t('blobs.error_request');
  };

  const load = async () => {
    if (pending.current || disabled || !csrfToken) return;
    pending.current = true;
    setBusy(true);
    setError('');
    try {
      setInventory(await loadBlobInventory(csrfToken));
    } catch (problem) {
      setError(failure(problem));
    } finally {
      pending.current = false;
      setBusy(false);
    }
  };
  const toggle = () => {
    setOpen(!open);
    if (!open && !inventory) void load();
  };
  const select = (binding: BlobBinding, path: string) => {
    const file = inventory?.files.find((candidate) => candidate.path === path);
    if (!file || file.state !== 'available' || disabled || busy) return;
    try {
      const next = replaceBlobBinding(getValue(), binding, file.path);
      onChange(next);
      setError('');
    } catch {
      setError(t('blobs.error_changed'));
    }
  };
  const upload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file || pending.current || disabled || !csrfToken) return;
    pending.current = true;
    setBusy(true);
    setError('');
    setUploaded('');
    try {
      const stored = await uploadBlob(csrfToken, file);
      setInventory((old) => {
        const files = [
          stored,
          ...(old?.files ?? []).filter(
            (candidate) => candidate.name !== stored.name,
          ),
        ];
        return {
          files: files.slice(0, 128),
          skipped: old?.skipped ?? 0,
          scan_truncated: !old || old.scan_truncated || files.length > 128,
        };
      });
      setUploaded(stored.name);
    } catch (problem) {
      setError(failure(problem));
    } finally {
      pending.current = false;
      setBusy(false);
    }
  };

  return (
    <Box component="section" aria-label={t('blobs.title')} sx={{ mt: -2 }}>
      <Stack
        direction="row"
        alignItems="center"
        useFlexGap
        flexWrap="wrap"
        gap={1}
      >
        <Button
          type="button"
          size="small"
          onClick={toggle}
          aria-expanded={open}
          aria-controls={`${id}-files`}
          startIcon={
            <ExpandMoreIcon
              sx={{ transform: open ? 'rotate(180deg)' : undefined }}
            />
          }
        >
          {t('blobs.title')}
        </Button>
        {inventory && (
          <Typography variant="caption" color="text.secondary">
            {t(
              inventory.scan_truncated || inventory.skipped > 0
                ? 'blobs.shown_count'
                : 'blobs.count',
              { count: inventory.files.length },
            )}
          </Typography>
        )}
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
        {t('blobs.help')}
      </Typography>
      {parsed.bindings.length > 0 && (
        <Typography
          variant="caption"
          component="div"
          sx={{ mt: 0.5, overflowWrap: 'anywhere' }}
        >
          {t('blobs.current')}{' '}
          {parsed.bindings
            .map((binding) => {
              const file = inventory?.files.find(
                (candidate) => candidate.path === binding.path,
              );
              return file
                ? describe(file)
                : binding.path.slice(binding.path.lastIndexOf('/') + 1);
            })
            .join('; ')}
        </Typography>
      )}
      {open && (
        <Stack id={`${id}-files`} spacing={1.5} sx={{ mt: 1.5 }}>
          {busy && (
            <Typography role="status" variant="caption">
              {t('blobs.loading')}
            </Typography>
          )}
          {error && (
            <Alert severity="warning" role="alert">
              {error}
            </Alert>
          )}
          {!inventory && !busy && (
            <Button
              size="small"
              onClick={() => void load()}
              disabled={disabled || !csrfToken}
            >
              {t('blobs.retry')}
            </Button>
          )}
          {inventory &&
            parsed.bindings.map((binding, index) => (
              <TextField
                key={`${binding.alias}-${index}`}
                select
                fullWidth
                size="small"
                label={
                  parsed.bindings.length > 1
                    ? `${t('blobs.choice')} ${index + 1}`
                    : t('blobs.choice')
                }
                value={binding.path}
                disabled={disabled || busy}
                onChange={(event) => select(binding, event.target.value)}
                helperText={
                  parsed.bindings.length > 1
                    ? `${t('blobs.slot')}: ${binding.alias}`
                    : undefined
                }
                slotProps={{ select: { native: true } }}
              >
                {!inventory.files.some(
                  (file) => file.path === binding.path,
                ) && (
                  <option value={binding.path}>
                    {binding.path.slice(binding.path.lastIndexOf('/') + 1)} ·{' '}
                    {t('blobs.not_listed')}
                  </option>
                )}
                {inventory.files.map((file) => (
                  <option
                    key={file.path}
                    value={file.path}
                    disabled={file.state !== 'available'}
                  >
                    {describe(file)}
                    {file.state !== 'available'
                      ? ` · ${t(file.state === 'too_large' ? 'blobs.too_large' : 'blobs.unavailable')}`
                      : ''}
                  </option>
                ))}
              </TextField>
            ))}
          {parsed.bindings.length === 0 && (
            <Typography variant="body2" color="text.secondary">
              {t('blobs.no_binding')}
            </Typography>
          )}
          {parsed.unsupported > 0 && (
            <Alert severity="info">{t('blobs.unsupported')}</Alert>
          )}
          {inventory && (inventory.skipped > 0 || inventory.scan_truncated) && (
            <Typography variant="caption" color="text.secondary">
              {t('blobs.partial')}
            </Typography>
          )}
          <Stack
            direction="row"
            alignItems="center"
            useFlexGap
            flexWrap="wrap"
            gap={1}
          >
            <Button
              type="button"
              size="small"
              variant="outlined"
              startIcon={<UploadFileIcon />}
              onClick={() => input.current?.click()}
              disabled={disabled || busy || !csrfToken}
            >
              {t('blobs.upload')}
            </Button>
            <input
              ref={input}
              type="file"
              accept=".bin,application/octet-stream"
              hidden
              onChange={(event) => void upload(event)}
              aria-label={t('blobs.upload')}
            />
            <Typography variant="caption" color="text.secondary">
              {t('blobs.upload_hint')}
            </Typography>
          </Stack>
          {uploaded && (
            <Alert severity="success" role="status">
              {t('blobs.uploaded', { name: uploaded })}
            </Alert>
          )}
          <Typography variant="caption" color="text.secondary">
            {t('blobs.save_hint')}
          </Typography>
        </Stack>
      )}
    </Box>
  );
}

import { useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Checkbox,
  FormControlLabel,
  Stack,
  Typography,
} from '@mui/material';

import {
  deleteDpiResult,
  downloadDpiOriginal,
  installDpi,
} from '@/api/dpiClient';
import {
  deleteSaved,
  getShareState,
  readSaved,
  refreshSaved,
  type ShareSelection,
  type ShareState,
} from '@/api/shareClient';
import { newSupportSubmissionId } from '@/api/supportReport';

import { RouterTrafficHelp } from '@/components/RouterTrafficHelp';

import { useTranslation } from '@/hooks/useTranslation';

export const ShareDpiSection = ({
  csrfToken,
  state,
  selection,
  disabled,
  onChange,
  onState,
  onError,
}: {
  csrfToken: string;
  state: ShareState;
  selection?: ShareSelection['dpi'];
  disabled: boolean;
  onChange: (v: ShareSelection['dpi']) => void;
  onState: (v: ShareState) => void;
  onError: (e: unknown) => void;
}) => {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [view, setView] = useState<{ name: string; raw: string }>();
  useEffect(() => {
    if (state.dpi.active?.kind !== 'install') return;
    let active = true;
    const timer = setInterval(() => {
      void getShareState(csrfToken).then(
        (v) => {
          if (active) onState(v);
        },
        (e) => {
          if (active) onError(e);
        },
      );
    }, 1500);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [csrfToken, state.dpi.active?.kind, onState, onError]);
  const action = async (fn: () => Promise<void>) => {
    if (busy || disabled) return;
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      onError(e);
    } finally {
      setBusy(false);
    }
  };
  const refresh = async () => {
    const saved = await refreshSaved(csrfToken);
    onState({ ...state, saved });
    onChange(undefined);
    setView(undefined);
  };
  const rows = [
    ...state.saved.reports.map((r) => ({
      kind: 'saved' as const,
      id: r.id,
      name: r.filename,
    })),
    ...state.dpi.history
      .filter((j) => j.kind === 'run' && j.completed_tests.length > 0)
      .map((j) => ({
        kind: 'legacy' as const,
        id: j.id,
        name: `${t('share.legacy_result')} · ${new Date(j.started_at * 1000).toLocaleString()}`,
        native: j.native_available === true,
      })),
  ];
  const read = async (row: (typeof rows)[number]) => {
    if (row.kind === 'saved') {
      const f = await readSaved(csrfToken, row.id);
      return {
        name: f.filename,
        raw: f.raw,
        blob: new Blob([f.raw], { type: 'text/plain' }),
      };
    }
    const f = await downloadDpiOriginal(csrfToken, row.id, row.native);
    return { name: f.filename, raw: await f.blob.text(), blob: f.blob };
  };
  return (
    <Stack spacing={1.5}>
      <RouterTrafficHelp>
        <Typography variant="subtitle1">DPI Detector</Typography>
      </RouterTrafficHelp>
      <Typography variant="body2">{t('share.native_hint')}</Typography>
      <Typography
        component="code"
        sx={{ userSelect: 'all', overflowWrap: 'anywhere' }}
      >
        /opt/bin/nfqws2-dpi
      </Typography>
      {!state.dpi.installed.installed && !confirm && (
        <Button
          disabled={disabled || busy || !!state.dpi.active}
          onClick={() => setConfirm(true)}
        >
          {t('share.install_dpi')}
        </Button>
      )}
      {confirm && (
        <Alert
          severity="info"
          action={
            <Button
              disabled={disabled || busy}
              onClick={() =>
                void action(async () => {
                  await installDpi(csrfToken, newSupportSubmissionId());
                  setConfirm(false);
                  onState(await getShareState(csrfToken));
                })
              }
            >
              {t('share.agree_install')}
            </Button>
          }
        >
          {t('share.install_hint')}{' '}
          <Button onClick={() => setConfirm(false)} disabled={busy}>
            {t('common.cancel')}
          </Button>
        </Alert>
      )}
      {state.dpi.active && (
        <Alert severity="info">
          {t(
            state.dpi.active.kind === 'install'
              ? 'share.installing'
              : 'share.legacy_active',
          )}
        </Alert>
      )}
      <Button disabled={disabled || busy} onClick={() => void action(refresh)}>
        {t('share.refresh_results')}
      </Button>
      {state.saved.scan_truncated || state.saved.skipped > 0 ? (
        <Alert severity="info">{t('share.import_partial')}</Alert>
      ) : null}
      {!rows.length && (
        <Typography variant="body2">{t('share.no_results')}</Typography>
      )}
      {rows.map((row) => (
        <Stack key={`${row.kind}-${row.id}`} spacing={0.5}>
          <FormControlLabel
            control={
              <Checkbox
                checked={
                  selection?.id === row.id && selection.kind === row.kind
                }
                disabled={disabled || busy}
                onChange={(_, checked) =>
                  onChange(checked ? { kind: row.kind, id: row.id } : undefined)
                }
              />
            }
            label={
              <Typography sx={{ overflowWrap: 'anywhere' }}>
                {row.name}
              </Typography>
            }
          />
          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
            <Button
              disabled={disabled || busy}
              onClick={() =>
                void action(async () => {
                  const f = await read(row);
                  setView({ name: f.name, raw: f.raw });
                })
              }
            >
              {t('share.view')}
            </Button>
            <Button
              disabled={disabled || busy}
              onClick={() =>
                void action(async () => {
                  const f = await read(row);
                  const url = URL.createObjectURL(f.blob);
                  const a = document.createElement('a');
                  try {
                    a.href = url;
                    a.download = f.name;
                    document.body.append(a);
                    a.click();
                  } finally {
                    a.remove();
                    setTimeout(() => URL.revokeObjectURL(url), 1000);
                  }
                })
              }
            >
              {t('share.download_original')}
            </Button>
            <Button
              color="error"
              disabled={disabled || busy}
              onClick={() =>
                void action(async () => {
                  if (!window.confirm(t('share.delete_confirm'))) return;
                  if (row.kind === 'saved')
                    await deleteSaved(csrfToken, row.id);
                  else await deleteDpiResult(csrfToken, row.id);
                  if (selection?.id === row.id) onChange(undefined);
                  setView(undefined);
                  onState(await getShareState(csrfToken));
                })
              }
            >
              {t('share.delete')}
            </Button>
          </Stack>
        </Stack>
      ))}
      {view && (
        <Stack spacing={1}>
          <Typography variant="caption" sx={{ overflowWrap: 'anywhere' }}>
            {view.name}
          </Typography>
          <Typography
            component="pre"
            sx={{
              whiteSpace: 'pre-wrap',
              overflowWrap: 'anywhere',
              maxHeight: 400,
              overflow: 'auto',
              fontSize: 12,
            }}
          >
            {view.raw}
          </Typography>
          <Button onClick={() => setView(undefined)}>
            {t('common.close')}
          </Button>
        </Stack>
      )}
    </Stack>
  );
};

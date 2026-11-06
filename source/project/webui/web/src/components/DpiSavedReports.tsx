import { useEffect, useRef, useState } from 'react';
import DownloadIcon from '@mui/icons-material/Download';
import RefreshIcon from '@mui/icons-material/Refresh';
import {
  Alert,
  Button,
  LinearProgress,
  Stack,
  Typography,
} from '@mui/material';

import {
  refreshSaved,
  ShareError,
  type SavedReport,
  type SavedReports,
} from '@/api/shareClient';

import { useTranslation } from '@/hooks/useTranslation';

import { downloadDpiSavedReport } from '@/utils/dpiSavedDownload';

export const DpiSavedReports = ({
  csrfToken,
  disabled,
}: {
  csrfToken: string;
  disabled: boolean;
}) => {
  const { t } = useTranslation();
  const [saved, setSaved] = useState<SavedReports | null>(null);
  const [refreshIndex, setRefreshIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState('');
  const [error, setError] = useState('');
  const pending = useRef(false);
  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    void refreshSaved(csrfToken).then(
      (value) => {
        if (active) {
          setSaved(value);
          setLoading(false);
        }
      },
      (failure) => {
        if (active) {
          setError(
            failure instanceof ShareError ? failure.code : 'request_failed',
          );
          setLoading(false);
        }
      },
    );
    return () => {
      active = false;
    };
  }, [csrfToken, refreshIndex]);
  const download = async (report: SavedReport) => {
    if (pending.current || disabled || loading) return;
    pending.current = true;
    setDownloading(report.id);
    setError('');
    try {
      await downloadDpiSavedReport(csrfToken, report);
    } catch (failure) {
      if (mounted.current)
        setError(
          failure instanceof ShareError ? failure.code : 'request_failed',
        );
    } finally {
      pending.current = false;
      if (mounted.current) setDownloading('');
    }
  };
  const sessionError = [
    'unauthorized',
    'forbidden',
    'auth_required',
    'csrf_failed',
    'origin_rejected',
  ].includes(error);
  const busy = disabled || loading || !!downloading;
  return (
    <Stack
      component="section"
      spacing={1}
      aria-labelledby="dpi-saved-reports-title"
      sx={{ flexShrink: 0, borderTop: 1, borderColor: 'divider', pt: 1.5 }}
    >
      <Stack
        direction="row"
        useFlexGap
        flexWrap="wrap"
        alignItems="center"
        gap={1}
      >
        <Typography
          id="dpi-saved-reports-title"
          variant="subtitle2"
          sx={{ flex: 1 }}
        >
          {t('dpi_terminal.reports_title')}
        </Typography>
        <Button
          size="small"
          startIcon={<RefreshIcon />}
          disabled={busy}
          onClick={() => setRefreshIndex((value) => value + 1)}
        >
          {t('dpi_terminal.reports_refresh')}
        </Button>
      </Stack>
      <Typography variant="body2">{t('dpi_terminal.reports_hint')}</Typography>
      {loading && (
        <LinearProgress aria-label={t('dpi_terminal.reports_loading')} />
      )}
      {error && (
        <Alert severity="error">
          {t(
            sessionError
              ? 'dpi_terminal.session_error'
              : error === 'invalid_response'
                ? 'dpi_terminal.report_changed'
                : 'dpi_terminal.reports_failed',
          )}
        </Alert>
      )}
      {saved && (saved.scan_truncated || saved.skipped > 0) && (
        <Alert severity="info">{t('share.import_partial')}</Alert>
      )}
      {saved && !saved.reports.length && !loading && (
        <Typography variant="body2">
          {t('dpi_terminal.reports_empty')}
        </Typography>
      )}
      {!!saved?.reports.length && (
        <Stack
          component="ul"
          spacing={1}
          sx={{
            m: 0,
            p: 0,
            maxHeight: 240,
            overflowY: 'auto',
            listStyle: 'none',
          }}
        >
          {saved.reports.map((report) => (
            <Stack
              key={report.id}
              component="li"
              direction={{ xs: 'column', sm: 'row' }}
              gap={0.5}
              alignItems={{ xs: 'flex-start', sm: 'center' }}
            >
              <Stack sx={{ flex: 1, minWidth: 0 }}>
                <Typography variant="body2" sx={{ overflowWrap: 'anywhere' }}>
                  {report.filename}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {t('dpi_terminal.report_bytes', { bytes: report.bytes })}
                </Typography>
              </Stack>
              <Button
                size="small"
                startIcon={<DownloadIcon />}
                disabled={busy}
                aria-label={`${t('dpi_terminal.report_download')}: ${report.filename}`}
                onClick={() => void download(report)}
              >
                {t(
                  downloading === report.id
                    ? 'dpi_terminal.report_downloading'
                    : 'dpi_terminal.report_download',
                )}
              </Button>
            </Stack>
          ))}
        </Stack>
      )}
    </Stack>
  );
};

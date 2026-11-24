import { useRef, useState } from 'react';
import { Alert, Button, Stack } from '@mui/material';

import { API } from '@/api/client';

import { useAppStore } from '@/store/useAppStore';

import { useStatus } from '@/hooks/useStatus';
import { useTranslation } from '@/hooks/useTranslation';

/** An explicit service action beside a saved change. Never runs on mount/save. */
export const InlineNfqwsRestart = ({
  disabled = false,
  compact = false,
  onPendingChange,
  onApplied,
}: {
  disabled?: boolean;
  compact?: boolean;
  onPendingChange?: (pending: boolean) => void;
  onApplied: () => void;
}) => {
  const { t } = useTranslation();
  const { csrfToken, isReady, nfqws2, service, authenticated, anonym } =
    useStatus();
  const { auth, needSave } = useAppStore();
  const pending = useRef(false);
  const [working, setWorking] = useState(false);
  const [failed, setFailed] = useState(false);
  const canControl =
    !!auth &&
    isReady &&
    nfqws2 &&
    !!csrfToken &&
    (authenticated || anonym) &&
    typeof service === 'boolean';
  const run = async () => {
    if (pending.current || disabled || needSave || !canControl) return;
    pending.current = true;
    setWorking(true);
    setFailed(false);
    onPendingChange?.(true);
    let applied = false;
    try {
      const { data, error } = await API.action(service ? 'restart' : 'start');
      applied = !error && data?.status === 0;
    } catch {
      applied = false;
    } finally {
      try {
        await API.invalidateStatus();
      } catch {
        // The action response is authoritative even if the status refresh fails.
      } finally {
        pending.current = false;
        setWorking(false);
        onPendingChange?.(false);
      }
    }
    if (applied) onApplied();
    else setFailed(true);
  };
  return (
    <Stack spacing={1}>
      <Button
        variant={compact ? 'outlined' : 'contained'}
        disabled={disabled || needSave || working || !canControl}
        onClick={() => void run()}
        aria-busy={working}
      >
        {t(
          service
            ? compact
              ? 'import.preset.restart'
              : 'import.restart_service'
            : compact
              ? 'import.preset.start'
              : 'import.start_service',
        )}
      </Button>
      {failed && <Alert severity="error">{t('import.service_failed')}</Alert>}
    </Stack>
  );
};

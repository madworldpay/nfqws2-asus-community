import { useRef, useState } from 'react';
import { Alert, Button, Stack } from '@mui/material';

import { API } from '@/api/client';

import { useAppStore } from '@/store/useAppStore';

import { useStatus } from '@/hooks/useStatus';
import { useTranslation } from '@/hooks/useTranslation';

/** An explicit service action beside a saved change. Never runs on mount/save. */
export const InlineNfqwsRestart = ({
  disabled = false,
  onPendingChange,
}: {
  disabled?: boolean;
  onPendingChange?: (pending: boolean) => void;
}) => {
  const { t } = useTranslation();
  const { csrfToken, isReady, nfqws2, service, authenticated, anonym } =
    useStatus();
  const { auth, needSave } = useAppStore();
  const pending = useRef(false);
  const [working, setWorking] = useState(false);
  const [result, setResult] = useState<'done' | 'failed'>();
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
    setResult(undefined);
    onPendingChange?.(true);
    try {
      const { data, error } = await API.action(service ? 'restart' : 'start');
      setResult(!error && data?.status === 0 ? 'done' : 'failed');
    } catch {
      setResult('failed');
    } finally {
      try {
        await API.invalidateStatus();
      } catch {
        setResult('failed');
      } finally {
        pending.current = false;
        setWorking(false);
        onPendingChange?.(false);
      }
    }
  };
  return (
    <Stack spacing={1}>
      <Button
        variant="contained"
        disabled={disabled || needSave || working || !canControl}
        onClick={() => void run()}
        aria-busy={working}
      >
        {t(service ? 'import.restart_service' : 'import.start_service')}
      </Button>
      {result && (
        <Alert severity={result === 'done' ? 'success' : 'error'}>
          {t(
            result === 'done' ? 'import.service_done' : 'import.service_failed',
          )}
        </Alert>
      )}
    </Stack>
  );
};

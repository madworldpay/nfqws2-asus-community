import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  LinearProgress,
  Stack,
  Typography,
} from '@mui/material';

import type { usePackageUpdates } from '@/hooks/usePackageUpdates';
import { useTranslation } from '@/hooks/useTranslation';

import { formatPackageVersion } from '@/utils/packageVersion';

export function PackageUpdateDialog({
  open,
  onClose,
  updates,
  installed,
}: {
  open: boolean;
  onClose: () => void;
  updates: ReturnType<typeof usePackageUpdates>;
  installed?: string;
}) {
  const { t } = useTranslation();
  const check = updates.data?.check;
  const candidate = check?.state === 'available' ? check.candidate : null;
  const operation = updates.data?.operation;
  const completedVersion =
    operation?.state === 'succeeded'
      ? formatPackageVersion(
          operation.installed_version ?? operation.package_version,
        )
      : null;
  const working =
    operation?.state === 'preparing' || operation?.state === 'applying';
  const prepared =
    operation?.state === 'prepared' &&
    operation.revision === candidate?.revision;
  const failed =
    operation?.state === 'failed' || operation?.state === 'interrupted';
  const errorCode =
    updates.error ??
    (failed ? operation?.code : check?.state === 'failed' ? check.code : null);
  const knownErrors = [
    'pending_packages',
    'missing_dependencies',
    'dependency_change',
    'insufficient_space',
    'stale_revision',
    'busy',
    'dns_restore_required',
    'dns_restore_failed',
    'request_failed',
    'core_start_failed',
    'core_stop_failed',
    'settings_changed',
  ] as const;
  const knownError = knownErrors.find((code) => code === errorCode);
  const errorKey = knownError
    ? (`package_update.${knownError}` as const)
    : 'package_update.failed';
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{t('package_update.title')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <Typography variant="body2">
            {t('package_update.installed', {
              version: formatPackageVersion(installed) ?? '—',
            })}
          </Typography>
          {(updates.pending || working || check?.state === 'checking') && (
            <LinearProgress />
          )}
          {errorCode && <Alert severity="warning">{t(errorKey)}</Alert>}
          {check?.state === 'unconfigured' && (
            <Alert severity="info">{t('package_update.unconfigured')}</Alert>
          )}
          {check?.state === 'current' && !working && (
            <Alert severity="success">{t('package_update.current')}</Alert>
          )}
          {candidate && (
            <>
              <Typography variant="subtitle1">
                {t('package_update.available', {
                  version: formatPackageVersion(candidate.package_version),
                })}
              </Typography>
              {candidate.notes && (
                <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                  {candidate.notes}
                </Typography>
              )}
              <Alert severity="info">{t('package_update.preserve')}</Alert>
            </>
          )}
          {operation && operation.state !== 'succeeded' && (
            <Typography variant="body2">
              {t(`package_update.state_${operation.state}`)}
            </Typography>
          )}
          {completedVersion && (
            <Alert severity="success">
              {t('package_update.done', { version: completedVersion })}
            </Alert>
          )}
          {operation?.core_state === 'waiting_for_wan' && (
            <Alert severity="info">{t('package_update.waiting')}</Alert>
          )}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ flexWrap: 'wrap', gap: 1 }}>
        <Button
          disabled={updates.pending || working}
          onClick={() => void updates.refresh(true)}
        >
          {t('package_update.check')}
        </Button>
        {candidate && !working && !prepared && (
          <Button
            variant="outlined"
            disabled={updates.pending}
            onClick={() => void updates.prepare(candidate.revision)}
          >
            {t('package_update.prepare')}
          </Button>
        )}
        {prepared && operation && (
          <Button
            variant="contained"
            disabled={updates.pending}
            onClick={() => void updates.apply(operation)}
          >
            {t('package_update.install')}
          </Button>
        )}
        <Button onClick={onClose}>{t('package_update.close')}</Button>
      </DialogActions>
    </Dialog>
  );
}

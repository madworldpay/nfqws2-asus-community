import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  LinearProgress,
  Link,
  Stack,
  Typography,
} from '@mui/material';

import type { usePackageUpdates } from '@/hooks/usePackageUpdates';
import { useTranslation } from '@/hooks/useTranslation';

import { formatPackageVersion } from '@/utils/packageVersion';

function ReleaseNotes({ text }: { text: string }) {
  // Render only simple emphasis and links to this project's documentation.
  // Release bodies never enter an HTML/Markdown execution pipeline.
  const parts = text.split(
    /(\[[^\]\n]+\]\(https:\/\/[^\s()]+\)|\*\*[^*\n]+\*\*)/g,
  );
  return (
    <Typography
      variant="body2"
      sx={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}
    >
      {parts.map((part, index) => {
        if (part.startsWith('**') && part.endsWith('**'))
          return <strong key={index}>{part.slice(2, -2)}</strong>;
        const match = part.match(/^\[([^\]\n]+)\]\((https:\/\/[^\s()]+)\)$/);
        if (match) {
          let url: URL;
          try {
            url = new URL(match[2]);
          } catch {
            return part;
          }
          const repo = '/madworldpay/nfqws2-asus-community';
          if (
            url.origin === 'https://github.com' &&
            !url.username &&
            !url.password &&
            (url.pathname === repo || url.pathname.startsWith(repo + '/'))
          )
            return (
              <Link
                key={index}
                href={url.href}
                target="_blank"
                rel="noopener noreferrer"
              >
                {match[1]}
              </Link>
            );
        }
        return part;
      })}
    </Typography>
  );
}

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
              <Typography variant="subtitle2">
                {t('package_update.changes')}
              </Typography>
              {updates.notesLoading && (
                <Typography
                  variant="body2"
                  color="text.secondary"
                  role="status"
                >
                  {t('package_update.changes_loading')}
                </Typography>
              )}
              {updates.notes && (
                <Typography variant="body2" color="text.secondary">
                  {t('package_update.changes_range', {
                    from: updates.notes.from_build,
                    to: updates.notes.to_build,
                  })}
                </Typography>
              )}
              {updates.notes?.releases
                .filter(
                  (r) =>
                    r.notes || r.build !== candidate.build || !candidate.notes,
                )
                .map((release) => (
                  <Stack key={release.build} spacing={0.5}>
                    <Typography variant="subtitle2">
                      Build {release.build}
                    </Typography>
                    <ReleaseNotes
                      text={release.notes || t('package_update.changes_empty')}
                    />
                  </Stack>
                ))}
              {!updates.notesLoading && !updates.notes?.complete && (
                <Typography
                  variant="body2"
                  color="text.secondary"
                  role="status"
                >
                  {t('package_update.changes_partial')}
                </Typography>
              )}
              {!updates.notes?.releases.some(
                (r) => r.build === candidate.build && r.notes,
              ) &&
                candidate.notes && (
                  <Stack spacing={0.5}>
                    <Typography variant="subtitle2">
                      Build {candidate.build}
                    </Typography>
                    <ReleaseNotes text={candidate.notes} />
                  </Stack>
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

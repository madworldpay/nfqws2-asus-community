import { useState } from 'react';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
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

import { CommunityChatLink } from '@/components/CommunityChatLink';

import type { usePackageUpdates } from '@/hooks/usePackageUpdates';
import { useTranslation } from '@/hooks/useTranslation';

import { copyText } from '@/utils/copyText';
import {
  packageUpdateErrorText,
  packageUpdateProgress,
} from '@/utils/packageUpdateProgress';
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
  onCheck,
  onRecover,
  recovering = false,
  sessionError,
}: {
  open: boolean;
  onClose: () => void;
  updates: ReturnType<typeof usePackageUpdates>;
  installed?: string;
  onCheck?: VoidFunction;
  onRecover?: VoidFunction;
  recovering?: boolean;
  sessionError?: string;
}) {
  const { t } = useTranslation();
  const [copyResult, setCopyResult] = useState<{ text: string; ok: boolean }>();
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
  const showProgress =
    updates.pending ||
    working ||
    recovering ||
    updates.checking ||
    check?.state === 'checking';
  const prepared =
    operation?.state === 'prepared' &&
    operation.revision === candidate?.revision;
  const failed =
    operation?.state === 'failed' || operation?.state === 'interrupted';
  const localError = sessionError ?? updates.error;
  const errorCode =
    localError ??
    (check?.state === 'failed' ? check.code : failed ? operation?.code : null);
  const previousFailure = failed && check?.state !== 'failed' && !localError;
  const progress = packageUpdateProgress(operation);
  const stageLabel = t(`package_update.stage_${progress?.stage ?? 'unknown'}`);
  const needsSession =
    errorCode === 'auth_required' || errorCode === 'csrf_failed';
  const knownErrors = [
    'timed_out',
    'download_hash',
    'download_failed',
    'install_failed',
    'web_start_failed',
    'web_health_failed',
    'version_mismatch',
    'pending_packages',
    'recovery_required',
    'missing_dependencies',
    'dependency_change',
    'insufficient_space',
    'stale_revision',
    'busy',
    'dns_restore_required',
    'dns_restore_failed',
    'dns_resume_stop_failed',
    'request_failed',
    'core_start_failed',
    'core_stop_failed',
    'web_stop_failed',
    'settings_changed',
    'experimental_runtime_active',
    'rollback_unavailable',
    'update_rolled_back',
    'rollback_failed',
  ] as const;
  const knownError = knownErrors.find((code) => code === errorCode);
  const errorKey = needsSession
    ? errorCode === 'auth_required'
      ? 'package_update.session'
      : 'package_update.csrf'
    : knownError
      ? (`package_update.${knownError}` as const)
      : 'package_update.failed';
  const primaryKnownError = knownErrors.find(
    (code) => code === operation?.failure_code,
  );
  const primaryFailureText =
    failed && operation?.failure_code
      ? String(
          t('package_update.primary_failure', {
            code: operation.failure_code,
            reason: t(
              primaryKnownError
                ? `package_update.${primaryKnownError}`
                : 'package_update.failed',
            ),
          }),
        )
      : '';
  const errorText = packageUpdateErrorText({
    installed: installed ?? check?.installed_version ?? undefined,
    target: operation?.package_version ?? candidate?.package_version,
    operation,
    stage: stageLabel,
    state: operation
      ? t(`package_update.state_${operation.state}`)
      : t('package_update.operation_unconfirmed'),
    errorCode,
    errorMessage: errorCode ? t(errorKey) : '',
    template: primaryFailureText
      ? `${primaryFailureText}\n${t('package_update.error_report')}`
      : t('package_update.error_report'),
  });
  const showErrorDetails = !!errorCode || failed;
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
          <Stack spacing={0.5}>
            <Stack
              direction="row"
              spacing={1}
              alignItems="flex-start"
              justifyContent="space-between"
              sx={{
                minHeight: '2.86em',
                visibility: progress ? 'visible' : 'hidden',
              }}
            >
              <Typography variant="body2" role="status" aria-live="polite">
                {progress?.failed
                  ? t('package_update.failed_stage', { stage: stageLabel })
                  : stageLabel}
              </Typography>
              <Typography variant="body2" sx={{ whiteSpace: 'nowrap' }}>
                {progress?.percent === null || !progress
                  ? '—'
                  : `${progress.percent}%`}
              </Typography>
            </Stack>
            <LinearProgress
              variant={progress ? 'determinate' : 'indeterminate'}
              value={progress?.percent ?? 0}
              color={progress?.failed ? 'error' : 'primary'}
              aria-label={stageLabel}
              aria-valuetext={
                progress?.percent === null ? stageLabel : undefined
              }
              sx={{
                visibility: showProgress || progress ? 'visible' : 'hidden',
              }}
            />
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{
                minHeight: '2.86em',
                visibility: progress ? 'visible' : 'hidden',
              }}
            >
              {t('package_update.progress_hint')}
            </Typography>
          </Stack>
          {errorCode && (
            <Alert severity="warning">
              {previousFailure && `${t('package_update.previous_attempt')} `}
              {t(errorKey)}
            </Alert>
          )}
          {showErrorDetails && (
            <Stack spacing={0.5}>
              {failed && operation?.failure_code && (
                <Typography variant="body2" sx={{ overflowWrap: 'anywhere' }}>
                  {primaryFailureText}
                </Typography>
              )}
              {failed && operation?.code && (
                <Typography variant="body2" sx={{ overflowWrap: 'anywhere' }}>
                  {t('package_update.operation_error', {
                    code: operation.code,
                  })}
                </Typography>
              )}
              <Button
                size="small"
                startIcon={<ContentCopyIcon />}
                sx={{ alignSelf: 'flex-start' }}
                onClick={() => {
                  setCopyResult(undefined);
                  void copyText(errorText)
                    .then((ok) => setCopyResult({ text: errorText, ok }))
                    .catch(() => setCopyResult({ text: errorText, ok: false }));
                }}
              >
                {t('package_update.copy_error')}
              </Button>
              {copyResult?.text === errorText && (
                <Typography variant="caption" role="status" aria-live="polite">
                  {t(
                    copyResult.ok
                      ? 'package_update.error_copied'
                      : 'package_update.error_copy_failed',
                  )}
                </Typography>
              )}
            </Stack>
          )}
          {check?.state === 'unconfigured' && (
            <Alert severity="info">{t('package_update.unconfigured')}</Alert>
          )}
          {check?.state === 'current' && !working && (
            <Alert severity="success">{t('package_update.current')}</Alert>
          )}
          {candidate && (
            <>
              <Typography variant="subtitle1">
                {t(
                  candidate.action === 'configure'
                    ? 'package_update.recovery_available'
                    : 'package_update.available',
                  {
                    version: formatPackageVersion(candidate.package_version),
                  },
                )}
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
            <Stack spacing={0.5}>
              <Alert severity="success">
                {t('package_update.done', { version: completedVersion })}
              </Alert>
              <CommunityChatLink copyable />
            </Stack>
          )}
          {operation?.core_state === 'waiting_for_wan' && (
            <Alert severity="info">{t('package_update.waiting')}</Alert>
          )}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ flexWrap: 'wrap', gap: 1 }}>
        <Button
          disabled={updates.pending || working || recovering}
          onClick={onCheck ?? (() => void updates.refresh(true))}
        >
          {t('package_update.check')}
        </Button>
        {needsSession && onRecover && (
          <Button disabled={recovering || updates.pending} onClick={onRecover}>
            {t('package_update.recover')}
          </Button>
        )}
        {candidate && !working && !prepared && (
          <Button
            variant="outlined"
            disabled={
              updates.pending || updates.checking || recovering || needsSession
            }
            onClick={() => void updates.prepare(candidate.revision)}
          >
            {t('package_update.prepare')}
          </Button>
        )}
        {prepared && operation && (
          <Button
            variant="contained"
            disabled={
              updates.pending || updates.checking || recovering || needsSession
            }
            onClick={() => void updates.apply(operation)}
          >
            {t(
              candidate?.action === 'configure'
                ? 'package_update.configure'
                : 'package_update.install',
            )}
          </Button>
        )}
        <Button onClick={onClose}>{t('package_update.close')}</Button>
      </DialogActions>
    </Dialog>
  );
}

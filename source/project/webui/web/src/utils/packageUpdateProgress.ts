import type {
  PackageOperation,
  PackageOperationPhase,
} from '@/api/packageUpdates';

export type PackageUpdateStage = PackageOperationPhase | 'prepared' | 'unknown';

export type PackageUpdateProgress = {
  stage: PackageUpdateStage;
  percent: number | null;
  failed: boolean;
};

const stagePercent: Record<PackageOperationPhase, number> = {
  queued: 0,
  checking_settings: 0,
  downloading: 0,
  checking_package: 14,
  validating: 28,
  stopping: 42,
  backing_up: 57,
  installing: 71,
  verifying: 85,
  finished: 100,
};

/** Stage milestones, not transferred bytes or an estimate of remaining time. */
export function packageUpdateProgress(
  operation: PackageOperation | null | undefined,
): PackageUpdateProgress | null {
  if (!operation) return null;
  const failed =
    operation.state === 'failed' || operation.state === 'interrupted';
  if (operation.state === 'succeeded')
    return { stage: 'finished', percent: 100, failed: false };
  if (operation.state === 'prepared')
    return { stage: 'prepared', percent: 28, failed: false };
  const phase = failed
    ? (operation.failure_phase ?? operation.phase)
    : operation.phase;
  // Legacy failed receipts only recorded "finished", losing the failed step.
  // Completion is confirmed by succeeded, never by a terminal worker phase.
  if (phase && phase !== 'finished')
    return {
      stage: phase,
      percent:
        phase === 'queued' && operation.state === 'applying'
          ? 28
          : stagePercent[phase],
      failed,
    };
  if (operation.state === 'preparing' && !phase)
    return { stage: 'downloading', percent: 0, failed: false };
  return { stage: 'unknown', percent: null, failed };
}

const defaultReport = `NFQWS2 update
Installed version: {{installed}}
Target version: {{target}}
State: {{state}} ({{operation_state}})
Stage: {{stage}}
Primary failure code: {{failure_code}}
Operation code: {{operation_code}}
Current error code: {{error_code}}
Current error: {{error}}
Operation ID: {{operation_id}}`;

/** Select update diagnostics explicitly; never serialize router or session data. */
export function packageUpdateErrorText({
  installed,
  target,
  operation,
  stage,
  state,
  errorCode,
  errorMessage,
  template = defaultReport,
}: {
  installed?: string;
  target?: string;
  operation: PackageOperation | null | undefined;
  stage: string;
  state: string;
  errorCode: string | null | undefined;
  errorMessage: string;
  template?: string;
}): string {
  const fields: Record<string, string> = {
    installed: installed ?? '—',
    target: target ?? operation?.package_version ?? '—',
    state,
    operation_state: operation?.state ?? '—',
    stage,
    failure_code: operation?.failure_code ?? '—',
    operation_code: operation?.code ?? '—',
    error_code: errorCode ?? '—',
    error: errorMessage,
    operation_id: operation?.id ?? '—',
  };
  return template.replace(/{{(\w+)}}/g, (_, key: string) => fields[key] ?? '—');
}

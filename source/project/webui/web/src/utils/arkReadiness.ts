import type { AsusDiagnostics } from '../api/schema.ts';

const FLAG_KEYS = [
  'ark_qoe_enable',
  'ark_iam_enable',
  'ark_limiter_enable',
  'ark_log_enable',
  'ark_hyqos_enable',
  'ark_mals_enable',
  'ark_adblock_enable',
  'ark_tracker_enable',
  'ark_ids_enable',
] as const;

type FlagState = 'enabled' | 'disabled' | 'unknown';
export type ArkReadiness = {
  result:
    | 'absent'
    | 'ready'
    | 'reboot_required'
    | 'runtime_unknown'
    | 'flags_enabled'
    | 'flags_unknown'
    | 'unavailable';
  disabled: number;
  enabled: number;
  unknown: number;
  runtime: 'loaded' | 'unloaded' | 'unknown';
  flags: { key: (typeof FLAG_KEYS)[number]; state: FlagState }[];
};

const record = (value: unknown): Record<string, unknown> | undefined =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;

const flagState = (flag?: Record<string, unknown>): FlagState => {
  if (
    flag?.present !== true ||
    typeof flag.value !== 'string' ||
    !/^-?[0-9]{1,10}$/.test(flag.value) ||
    flag.value.trim() !== flag.value ||
    typeof flag.enabled !== 'boolean' ||
    !Number.isFinite(Number(flag.value))
  )
    return 'unknown';
  const enabled = Number(flag.value) !== 0;
  return enabled === flag.enabled
    ? enabled
      ? 'enabled'
      : 'disabled'
    : 'unknown';
};

const boundedInteger = (value: unknown, maximum: number): number | null =>
  typeof value === 'number' &&
  Number.isInteger(value) &&
  value >= 0 &&
  value <= maximum
    ? value
    : null;

export const normalizeArkDiagnostics = (
  data: unknown,
): AsusDiagnostics | undefined => {
  const diagnostics = record(data);
  if (!diagnostics) return undefined;
  const ark = record(diagnostics.ark);
  const queue = record(diagnostics.nfqueue);
  return {
    ark: {
      present:
        ark?.present === 'present' || ark?.present === 'absent'
          ? ark.present
          : 'unknown',
      loaded:
        ark?.loaded === 'loaded' || ark?.loaded === 'unloaded'
          ? ark.loaded
          : 'unknown',
    },
    nfqueue: {
      queue_number: boundedInteger(queue?.queue_number, 65535),
      state:
        queue?.state === 'bound' || queue?.state === 'unbound'
          ? queue.state
          : 'unknown',
      sequence: boundedInteger(queue?.sequence, 4294967295),
    },
    process_running:
      typeof diagnostics.process_running === 'boolean'
        ? diagnostics.process_running
        : null,
  };
};

export const classifyArkReadiness = (data: unknown): ArkReadiness => {
  const status = record(data);
  const rows = Array.isArray(status?.flags)
    ? status.flags.map(record)
    : undefined;
  const valid =
    status?.status === 0 &&
    status.error === undefined &&
    !!rows &&
    rows.every((row) => FLAG_KEYS.some((key) => key === row?.key));
  const flags = FLAG_KEYS.map((key) => {
    const matching = valid ? rows.filter((row) => row?.key === key) : [];
    return {
      key,
      state: matching.length === 1 ? flagState(matching[0]) : 'unknown',
    } as ArkReadiness['flags'][number];
  });
  const disabled = flags.filter((flag) => flag.state === 'disabled').length;
  const enabled = flags.filter((flag) => flag.state === 'enabled').length;
  const unknown = flags.filter((flag) => flag.state === 'unknown').length;
  let runtime: ArkReadiness['runtime'] = 'unknown';
  if (valid && typeof status.ark_loaded === 'boolean') {
    const expected = status.ark_loaded ? 'loaded' : 'unloaded';
    const diagnosticArk = record(record(status.diagnostics)?.ark);
    const consistentDiagnostics =
      diagnosticArk?.loaded === expected &&
      typeof diagnosticArk.present === 'string' &&
      ['present', 'absent', 'unknown'].includes(diagnosticArk.present) &&
      !(diagnosticArk.present === 'absent' && expected === 'loaded');
    if (status.diagnostics === undefined || consistentDiagnostics) {
      runtime = expected;
    }
  }
  return {
    result: !valid
      ? 'unavailable'
      : runtime === 'unloaded' &&
          record(record(status.diagnostics)?.ark)?.present === 'absent'
        ? 'absent'
        : enabled
          ? 'flags_enabled'
          : unknown
            ? 'flags_unknown'
            : runtime === 'unloaded'
              ? 'ready'
              : runtime === 'loaded'
                ? 'reboot_required'
                : 'runtime_unknown',
    disabled,
    enabled,
    unknown,
    runtime,
    flags,
  };
};

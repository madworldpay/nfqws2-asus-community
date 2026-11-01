export type RestartScheduleSettings = {
  enabled: boolean;
  interval_hours: number;
  watchdog_enabled: boolean;
};
export type RestartSchedule = RestartScheduleSettings & {
  scheduler_available: boolean;
  watchdog_state: 'disabled' | 'ready' | 'waiting' | 'locked';
  watchdog_attempts: number;
  watchdog_next_seconds: number | null;
};

export class RestartScheduleError extends Error {
  code: string;
  constructor(code: string) {
    super(code);
    this.code = code;
  }
}

export const validRestartHours = (value: string): boolean =>
  /^[0-9]+$/.test(value) && Number(value) >= 1 && Number(value) <= 168;

export async function restartScheduleRequest(
  csrf: string,
  signal: AbortSignal,
  schedule?: RestartScheduleSettings,
): Promise<RestartSchedule> {
  const params: Record<string, string> = schedule
    ? {
        cmd: 'restartschedulesave',
        csrf_token: csrf,
        enabled: schedule.enabled ? '1' : '0',
        interval_hours: String(schedule.interval_hours),
        watchdog_enabled: schedule.watchdog_enabled ? '1' : '0',
      }
    : { cmd: 'restartschedule', csrf_token: csrf };
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (signal.aborted) abort();
  else signal.addEventListener('abort', abort, { once: true });
  const timer = setTimeout(abort, 15000);
  try {
    const response = await fetch('/index.php', {
      method: 'POST',
      credentials: 'same-origin',
      redirect: 'error',
      cache: 'no-store',
      body: new URLSearchParams(params),
      signal: controller.signal,
    });
    if (response.status === 401 || response.status === 403)
      throw new RestartScheduleError('session');
    if (
      !/^application\/json(?:;|$)/i.test(
        response.headers.get('Content-Type') ?? '',
      )
    )
      throw new RestartScheduleError('invalid_response');
    const value: unknown = await response.json();
    if (!response.ok) {
      const error =
        value && typeof value === 'object' && 'error' in value
          ? value.error
          : null;
      throw new RestartScheduleError(
        typeof error === 'string' ? error : 'request_failed',
      );
    }
    if (
      !value ||
      typeof value !== 'object' ||
      !('enabled' in value) ||
      typeof value.enabled !== 'boolean' ||
      !('interval_hours' in value) ||
      typeof value.interval_hours !== 'number' ||
      !Number.isInteger(value.interval_hours) ||
      !validRestartHours(String(value.interval_hours)) ||
      !('watchdog_enabled' in value) ||
      typeof value.watchdog_enabled !== 'boolean' ||
      !('watchdog_state' in value) ||
      !['disabled', 'ready', 'waiting', 'locked'].includes(
        String(value.watchdog_state),
      ) ||
      !('watchdog_attempts' in value) ||
      typeof value.watchdog_attempts !== 'number' ||
      !Number.isInteger(value.watchdog_attempts) ||
      value.watchdog_attempts < 0 ||
      value.watchdog_attempts > 3 ||
      !('watchdog_next_seconds' in value) ||
      ('scheduler_available' in value &&
        typeof value.scheduler_available !== 'boolean') ||
      (value.watchdog_next_seconds !== null &&
        (typeof value.watchdog_next_seconds !== 'number' ||
          !Number.isSafeInteger(value.watchdog_next_seconds) ||
          value.watchdog_next_seconds < 0))
    )
      throw new RestartScheduleError('invalid_response');
    return {
      ...value,
      scheduler_available:
        'scheduler_available' in value ? value.scheduler_available : true,
    } as RestartSchedule;
  } catch (error) {
    if (error instanceof RestartScheduleError) throw error;
    throw new RestartScheduleError('request_failed');
  } finally {
    clearTimeout(timer);
    signal.removeEventListener('abort', abort);
  }
}

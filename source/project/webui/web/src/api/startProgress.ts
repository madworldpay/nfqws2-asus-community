import type { Checkup, ConfigView } from '@/api/smartDnsConfigClient';

export type StartState = 'done' | 'partial' | 'todo' | 'optional' | 'unknown';
export type StartStep =
  | 'install'
  | 'ark'
  | 'configure'
  | 'dns'
  | 'start'
  | 'verify';

export function startProgress(input: {
  checkup?: Checkup;
  hasStrategy?: boolean;
  dirty?: boolean;
  pendingRestart?: boolean;
  dns?: ConfigView;
}): { id: StartStep; state: StartState }[] {
  const facts = (id: string) =>
    input.checkup?.items.find((x) => x.id === id)?.facts;
  const platform = facts('platform');
  const loaded = facts('ark')?.loaded;
  const running = facts('process')?.running;
  const bound = facts('nfqueue')?.bound;
  const draft = input.dns?.draft;
  const hasDns = Boolean(
    draft && (draft.upstreams.length || draft.records.length),
  );
  return [
    {
      id: 'install',
      state:
        platform?.package_version &&
        (platform?.entware_abi || platform?.platform === 'openwrt')
          ? 'done'
          : 'unknown',
    },
    {
      id: 'ark',
      state: loaded === false ? 'done' : loaded === true ? 'todo' : 'unknown',
    },
    {
      id: 'configure',
      state:
        input.hasStrategy === undefined
          ? 'unknown'
          : !input.hasStrategy
            ? 'todo'
            : input.dirty || input.pendingRestart
              ? 'partial'
              : 'done',
    },
    {
      id: 'dns',
      state: !input.dns
        ? 'unknown'
        : input.dns.status.state === 'confirmed' &&
            input.dns.status.active_profile_hash &&
            facts('dns_runtime')?.managed_runtime === true
          ? 'done'
          : hasDns || input.dns.status.state !== 'idle'
            ? 'partial'
            : 'optional',
    },
    {
      id: 'start',
      state:
        running === true && bound === true
          ? 'done'
          : running === true
            ? 'partial'
            : running === false
              ? 'todo'
              : 'unknown',
    },
    // Neither a running process nor DNS answers verify a service on a client.
    { id: 'verify', state: 'todo' },
  ];
}

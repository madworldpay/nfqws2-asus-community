import { useCallback, useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { API } from '@/api/client';
import { getPackageUpdateNotes } from '@/api/packageUpdateNotes';
import {
  applyPackageUpdate,
  checkPackageUpdate,
  getPackageUpdateOverview,
  PackageUpdateError,
  packageUpdateRequestId,
  preparePackageUpdate,
  type PackageOperation,
  type PackageOverview,
} from '@/api/packageUpdates';

export function usePackageUpdates(
  csrf: string | undefined,
  allowed: boolean,
  open: boolean,
) {
  const client = useQueryClient();
  const enabled = allowed && !!csrf;
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<{
    code: string;
    source: 'check' | 'operation';
    snapshot?: number;
  }>();
  const generation = useRef(0);
  const refreshRequest = useRef<Promise<void> | null>(null);
  const mutating = useRef(false);
  const explicitRefresh = useRef(false);
  const checked = useRef(false);
  const prepareRequest = useRef<{
    revision: string;
    id: string;
    resolved: boolean;
  } | null>(null);
  const applyRequest = useRef<{ operation: string; id: string } | null>(null);
  const initiated = useRef<string | null>(null);
  useEffect(() => {
    const epoch = generation.current;
    setPending(false);
    setError(undefined);
    checked.current = false;
    prepareRequest.current = null;
    applyRequest.current = null;
    initiated.current = null;
    return () => {
      generation.current = epoch + 1;
      refreshRequest.current = null;
      mutating.current = false;
    };
  }, [csrf, enabled]);
  const query = useQuery({
    queryKey: ['package-update-overview', csrf],
    enabled,
    queryFn: () => getPackageUpdateOverview(csrf!),
    retry: (count, e) =>
      count < 2 && e instanceof PackageUpdateError && e.code === 'busy',
    retryDelay: 250,
    refetchInterval: (q) =>
      open ||
      ['preparing', 'applying'].includes(
        q.state.data?.operation?.state ?? '',
      ) ||
      q.state.data?.check.state === 'checking'
        ? 2000
        : false,
  });
  const candidate =
    query.data?.check.state === 'available' ? query.data.check.candidate : null;
  const installed = query.data?.check.installed_version;
  const notesEnabled = enabled && open && !!candidate && !!installed;
  const notesQuery = useQuery({
    queryKey: ['package-update-notes', installed, candidate?.revision],
    enabled: notesEnabled,
    queryFn: ({ signal }) =>
      getPackageUpdateNotes(installed!, candidate!.build, signal),
    staleTime: 300000,
    retry: false,
    refetchOnWindowFocus: false,
  });
  const refresh = useCallback(
    (force = false): Promise<void> => {
      const key = ['package-update-overview', csrf];
      const active = () =>
        ['preparing', 'applying'].includes(
          client.getQueryData<PackageOverview>(key)?.operation?.state ?? '',
        );
      if (!enabled || mutating.current || active()) return Promise.resolve();
      if (force) explicitRefresh.current = true;
      if (refreshRequest.current) return refreshRequest.current;
      explicitRefresh.current = force;
      checked.current = true;
      const epoch = generation.current;
      const snapshot = client.getQueryState(key)?.dataUpdateCount;
      const current = () => generation.current === epoch && !mutating.current;
      const unchanged = () =>
        client.getQueryState(key)?.dataUpdateCount === snapshot;
      const run = async () => {
        setPending(true);
        setError((old) => (old?.source === 'check' ? undefined : old));
        try {
          for (let attempt = 0; attempt < 3; attempt++) {
            if (!current() || active() || !unchanged()) return;
            try {
              const check = await checkPackageUpdate(csrf!, force);
              // A status poll may have already supplied a newer snapshot.
              if (!current() || !unchanged()) return;
              // An older status response must not undo this completed check.
              await client.cancelQueries({ queryKey: key, exact: true });
              if (!current() || !unchanged()) return;
              client.setQueryData<PackageOverview>(key, (old) => ({
                check,
                operation: old?.operation ?? null,
              }));
              return;
            } catch (e) {
              if (!current() || !unchanged()) return;
              const code =
                e instanceof PackageUpdateError ? e.code : 'request_failed';
              if (code === 'busy' && attempt < 2) {
                await new Promise((resolve) => setTimeout(resolve, 250));
                continue;
              }
              // Background lock contention is not an installation failure.
              // A manual check joining this request must still get its result.
              if (
                code === 'busy' &&
                !explicitRefresh.current &&
                client.getQueryData(key)
              )
                return;
              setError((old) =>
                old?.source === 'operation'
                  ? old
                  : { code, source: 'check', snapshot },
              );
              return;
            }
          }
        } finally {
          if (generation.current === epoch) {
            refreshRequest.current = null;
            if (!mutating.current) setPending(false);
          }
        }
      };
      refreshRequest.current = run();
      return refreshRequest.current;
    },
    [enabled, csrf, client],
  );
  useEffect(() => {
    if (!enabled) return;
    // Read the operation first so reopening a panel during installation only polls.
    if (query.isSuccess && !checked.current) {
      checked.current = true;
      void refresh();
    }
    const timer = setInterval(() => void refresh(), 300000);
    return () => clearInterval(timer);
  }, [enabled, query.isSuccess, refresh]);
  useEffect(() => {
    if (
      error?.source === 'check' &&
      query.isSuccess &&
      query.data.check.state !== 'checking' &&
      query.data.check.state !== 'failed' &&
      client.getQueryState(['package-update-overview', csrf])
        ?.dataUpdateCount !== error.snapshot
    )
      setError(undefined);
  }, [error, query.isSuccess, query.data, query.dataUpdatedAt, client, csrf]);
  const op = query.data?.operation;
  useEffect(() => {
    if (
      op &&
      prepareRequest.current?.revision === op.revision &&
      ['prepared', 'succeeded', 'failed', 'interrupted'].includes(op.state)
    )
      prepareRequest.current.resolved = true;
    if (op?.state === 'succeeded' && initiated.current === op.id) {
      initiated.current = null;
      void API.invalidateStatus().then(() => window.location.reload());
    }
  }, [op]);
  const perform = async (action: () => Promise<PackageOperation>) => {
    if (mutating.current) return;
    const epoch = generation.current;
    mutating.current = true;
    setPending(true);
    setError(undefined);
    try {
      const operation = await action();
      if (generation.current !== epoch) return;
      client.setQueryData<PackageOverview>(
        ['package-update-overview', csrf],
        (old) => ({
          check: old?.check ?? {
            state: 'failed',
            code: 'check_required',
            candidate: null,
            installed_version: null,
          },
          operation,
        }),
      );
    } catch (e) {
      if (generation.current === epoch)
        setError({
          code: e instanceof PackageUpdateError ? e.code : 'request_failed',
          source: 'operation',
        });
    } finally {
      if (generation.current === epoch) {
        mutating.current = false;
        setPending(!!refreshRequest.current);
        void query.refetch();
      }
    }
  };
  return {
    data: enabled ? query.data : undefined,
    pending,
    notes: candidate ? notesQuery.data : undefined,
    notesLoading: notesEnabled && notesQuery.isFetching,
    error:
      error?.code ??
      (query.error instanceof PackageUpdateError &&
      !(query.error.code === 'busy' && query.data)
        ? query.error.code
        : undefined),
    refresh,
    prepare: async (revision: string) => {
      if (!csrf || !enabled) return;
      if (
        prepareRequest.current?.revision !== revision ||
        prepareRequest.current.resolved
      )
        prepareRequest.current = {
          revision,
          id: packageUpdateRequestId(),
          resolved: false,
        };
      const request = prepareRequest.current;
      await perform(() => preparePackageUpdate(csrf, revision, request.id));
    },
    apply: async (operation: PackageOperation) => {
      if (!csrf || !enabled) return;
      if (applyRequest.current?.operation !== operation.id)
        applyRequest.current = {
          operation: operation.id,
          id: packageUpdateRequestId(),
        };
      const request = applyRequest.current;
      initiated.current = operation.id;
      await perform(() =>
        applyPackageUpdate(csrf, operation.id, operation.revision, request.id),
      );
    },
  };
}

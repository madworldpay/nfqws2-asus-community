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
  type PackageCheck,
  type PackageOperation,
  type PackageOverview,
} from '@/api/packageUpdates';

export function usePackageUpdates(
  csrf: string | undefined,
  allowed: boolean,
  open: boolean,
  deferCheck = false,
) {
  const client = useQueryClient();
  const enabled = allowed && !!csrf;
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<{
    code: string;
    source: 'check' | 'operation';
    snapshot?: number;
  }>();
  const [applyingGrace, setApplyingGrace] = useState<{
    csrf: string | undefined;
    id: string;
    expires: number;
  }>();
  const applyingWindow = useRef<typeof applyingGrace>(undefined);
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
  const settledCheck = useRef<
    { csrf: string | undefined; check: PackageCheck } | undefined
  >(undefined);
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
  if (settledCheck.current?.csrf !== csrf) settledCheck.current = undefined;
  const checking =
    query.data?.check.state === 'checking' ||
    (query.data?.check.state === 'failed' &&
      query.data.check.code === 'check_required');
  if (query.data && !checking)
    settledCheck.current = { csrf, check: query.data.check };
  // Checking is transient. Keep the last result, but never carry a candidate
  // across an observed package-version change (for example a manual IPK).
  const data =
    query.data &&
    checking &&
    settledCheck.current?.check.installed_version ===
      query.data.check.installed_version
      ? { ...query.data, check: settledCheck.current.check }
      : query.data;
  const candidate =
    data?.check.state === 'available' ? data.check.candidate : null;
  const installed = data?.check.installed_version;
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
        if (force)
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
    if (!enabled || deferCheck) return;
    // Read the operation first so reopening a panel during installation only polls.
    if (query.isSuccess && !checked.current) {
      checked.current = true;
      void refresh();
    }
    const timer = setInterval(() => void refresh(), 300000);
    return () => clearInterval(timer);
  }, [enabled, deferCheck, query.isSuccess, refresh]);
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
  const operationId = op?.id;
  const operationState = op?.state;
  useEffect(() => {
    if (
      !enabled ||
      !operationId ||
      applyingWindow.current?.csrf !== csrf ||
      applyingWindow.current?.id !== operationId
    )
      applyingWindow.current = undefined;
    if (!enabled || !operationId || operationState !== 'applying') {
      setApplyingGrace(undefined);
      return;
    }
    // The package worker stops this panel during replacement. Only a known
    // operation gets one bounded window; polling never extends the deadline.
    const window = applyingWindow.current ?? {
      csrf,
      id: operationId,
      expires: Date.now() + 120000,
    };
    applyingWindow.current = window;
    setApplyingGrace(window);
    const timer = setTimeout(
      () =>
        setApplyingGrace((current) =>
          current === window ? undefined : current,
        ),
      Math.max(0, window.expires - Date.now()),
    );
    return () => clearTimeout(timer);
  }, [enabled, csrf, operationId, operationState]);
  const overviewError =
    query.error instanceof PackageUpdateError ? query.error.code : undefined;
  const restartingPanel =
    enabled &&
    op?.state === 'applying' &&
    applyingGrace?.id === op.id &&
    applyingGrace.csrf === csrf &&
    Date.now() < applyingGrace.expires &&
    (overviewError === 'request_failed' ||
      overviewError === 'invalid_response');
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
  const { refetch: refetchOverview } = query;
  const recoverSession = useCallback(async () => {
    setError((old) =>
      old?.code === 'auth_required' || old?.code === 'csrf_failed'
        ? undefined
        : old,
    );
    await refetchOverview();
  }, [refetchOverview]);
  return {
    data: enabled ? data : undefined,
    checking: enabled && checking,
    pending,
    notes: candidate ? notesQuery.data : undefined,
    notesLoading: notesEnabled && notesQuery.isFetching,
    error:
      error?.code ??
      (overviewError &&
      !(overviewError === 'busy' && query.data) &&
      !restartingPanel
        ? overviewError
        : undefined),
    refresh,
    recoverSession,
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

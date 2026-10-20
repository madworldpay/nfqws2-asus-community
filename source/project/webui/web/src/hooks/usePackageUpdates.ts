import { useCallback, useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { API } from '@/api/client';
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
  const [error, setError] = useState<string>();
  const prepareRequest = useRef<{
    revision: string;
    id: string;
    resolved: boolean;
  } | null>(null);
  const applyRequest = useRef<{ operation: string; id: string } | null>(null);
  const initiated = useRef<string | null>(null);
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
  const refresh = useCallback(
    async (force = false) => {
      if (!enabled) return;
      setPending(true);
      setError(undefined);
      try {
        const check = await checkPackageUpdate(csrf!, force);
        client.setQueryData<PackageOverview>(
          ['package-update-overview', csrf],
          (old) => ({ check, operation: old?.operation ?? null }),
        );
      } catch (e) {
        setError(e instanceof PackageUpdateError ? e.code : 'request_failed');
      } finally {
        setPending(false);
      }
    },
    [enabled, csrf, client],
  );
  useEffect(() => {
    if (!enabled) return;
    void refresh();
    const timer = setInterval(() => void refresh(), 300000);
    return () => clearInterval(timer);
  }, [enabled, refresh]);
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
    setPending(true);
    setError(undefined);
    try {
      const operation = await action();
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
      setError(e instanceof PackageUpdateError ? e.code : 'request_failed');
    } finally {
      setPending(false);
      void query.refetch();
    }
  };
  return {
    data: enabled ? query.data : undefined,
    pending,
    error:
      error ??
      (query.error instanceof PackageUpdateError
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

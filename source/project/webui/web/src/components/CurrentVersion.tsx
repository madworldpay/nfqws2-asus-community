import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { Chip, Stack, Tooltip } from '@mui/material';
import type { SxProps } from '@mui/system/styleFunctionSx';
import { useQuery } from '@tanstack/react-query';

import { API } from '@/api/client';
import { getKeeneticPanelUpdate } from '@/api/packageUpdateNotes';
import { packageUpdateBadges } from '@/api/packageUpdates';

import { LoginDialog } from '@/components/LoginDialog';
import { PackageUpdateDialog } from '@/components/PackageUpdateDialog';
import {
  RabbitBuildBadge,
  type RabbitBuildState,
} from '@/components/RabbitBuildBadge';

import { useAppearanceStore } from '@/store/useAppearanceStore';
import { useAppStore } from '@/store/useAppStore';

import { usePackageUpdates } from '@/hooks/usePackageUpdates';
import { useStatus } from '@/hooks/useStatus';
import { useTranslation } from '@/hooks/useTranslation';

import { formatPackageVersion } from '@/utils/packageVersion';

export const CurrentVersion = ({ sx }: { sx?: SxProps }) => {
  const {
    platform,
    packageVersion,
    buildNumber,
    webVersion,
    csrfToken,
    anonym,
    authenticated,
    service,
    isReady,
  } = useStatus();
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const { refetch: refreshStatus } = API.status(true);
  const { auth } = useAppStore();
  const { appearance } = useAppearanceStore();
  const [refreshingSession, setRefreshingSession] = useState(false);
  const [sessionError, setSessionError] = useState<string>();
  const [loginOpen, setLoginOpen] = useState(false);
  const [intent, setIntent] = useState<{
    id: number;
    token: string;
    check: boolean;
  }>();
  const request = useRef(0);
  const started = useRef(0);
  const waitingForLogin = useRef(false);
  const keenetic = platform === 'keenetic-entware';
  const arch =
    typeof document === 'undefined'
      ? ''
      : (document.documentElement.dataset.entwareArch ?? '');
  const keeneticUpdate = useQuery({
    queryKey: ['keenetic-panel-release', packageVersion, arch],
    queryFn: ({ signal }) =>
      getKeeneticPanelUpdate(packageVersion ?? '', arch, signal),
    enabled: keenetic && isReady && !!packageVersion && !!arch,
    staleTime: 3_600_000,
    retry: false,
  });
  const updates = usePackageUpdates(
    csrfToken,
    platform !== 'keenetic-entware' && (anonym || authenticated),
    open,
    refreshingSession || !!intent,
  );
  const { recoverSession, refresh } = updates;
  const close = () => {
    request.current++;
    waitingForLogin.current = false;
    setIntent(undefined);
    setRefreshingSession(false);
    setLoginOpen(false);
    setOpen(false);
  };
  const confirmServiceOff = useCallback(async () => {
    const fresh = await refreshStatus();
    return (
      fresh.isSuccess &&
      fresh.data?.status === 0 &&
      fresh.data.service === false &&
      useAppStore.getState().auth === true
    );
  }, [refreshStatus]);
  useEffect(
    () => () => {
      request.current++;
    },
    [],
  );
  useEffect(() => {
    if (auth === false && open) {
      setLoginOpen(false);
      waitingForLogin.current = true;
    }
  }, [auth, open]);
  const refreshSession = useCallback(
    async (check = false) => {
      const id = ++request.current;
      setRefreshingSession(true);
      try {
        const fresh = await refreshStatus();
        if (request.current !== id) return;
        if (
          !fresh.isSuccess ||
          useAppStore.getState().auth === false ||
          !fresh.data ||
          fresh.data.status !== 0
        ) {
          waitingForLogin.current = useAppStore.getState().auth === false;
          setSessionError(
            waitingForLogin.current ? 'auth_required' : 'request_failed',
          );
          return;
        }
        if (
          !(fresh.data.authenticated ?? !fresh.data.anonym) &&
          !fresh.data.anonym
        ) {
          setSessionError('auth_required');
          setLoginOpen(true);
          return;
        }
        if (!fresh.data.csrf_token) {
          setSessionError('request_failed');
          return;
        }
        setLoginOpen(false);
        setSessionError(undefined);
        setIntent({ id, token: fresh.data.csrf_token, check });
      } catch {
        if (request.current === id) setSessionError('request_failed');
      } finally {
        if (request.current === id) setRefreshingSession(false);
      }
    },
    [refreshStatus],
  );
  useEffect(() => {
    if (waitingForLogin.current && auth === true) {
      waitingForLogin.current = false;
      // Login first updates the shared auth flag. Read status again rather
      // than accepting the cached pre-login token during that transition.
      void refreshSession();
    }
  }, [auth, refreshSession]);
  useEffect(() => {
    if (!intent || intent.token !== csrfToken || started.current === intent.id)
      return;
    started.current = intent.id;
    // Wait for the refreshed nonce to reach this hook. Recovery only reads;
    // preparing and applying always require another explicit button click.
    void (async () => {
      await recoverSession();
      if (request.current === intent.id && intent.check) await refresh(true);
      if (request.current === intent.id) setIntent(undefined);
    })();
  }, [intent, csrfToken, recoverSession, refresh]);
  const web = webVersion?.join('.') ?? '0.0.0';
  const badges = packageUpdateBadges(
    updates.data?.check,
    packageVersion,
    web,
    buildNumber,
  );
  const availableUpdate = keenetic
    ? !!keeneticUpdate.data
    : badges.core || badges.web || badges.build;
  const rabbitState: RabbitBuildState =
    !isReady || typeof service !== 'boolean'
      ? 'unknown'
      : !service
        ? 'off'
        : availableUpdate
          ? 'update'
          : 'idle';
  const badge = (label: ReactNode, available: boolean) => {
    const chip = keenetic ? (
      keeneticUpdate.data ? (
        <Chip
          component="a"
          href={keeneticUpdate.data}
          target="_blank"
          rel="noopener noreferrer"
          clickable
          label={label}
          size="small"
          variant="outlined"
          color="warning"
          title={t('package_update.badge_available')}
        />
      ) : (
        <Chip label={label} size="small" variant="outlined" />
      )
    ) : (
      <Tooltip
        key={String(label)}
        title={t(
          available ? 'package_update.badge_available' : 'package_update.check',
        )}
        enterTouchDelay={0}
      >
        <Chip
          label={label}
          size="small"
          variant="outlined"
          color={available ? 'warning' : 'primary'}
          onClick={() => setOpen(true)}
          sx={{ cursor: 'pointer' }}
        />
      </Tooltip>
    );
    return appearance === 'rabbit' ? (
      <RabbitBuildBadge
        key={String(label)}
        state={rabbitState}
        serviceOff={auth === true && isReady && service === false}
        confirmServiceOff={confirmServiceOff}
      >
        {chip}
      </RabbitBuildBadge>
    ) : (
      chip
    );
  };
  return (
    <>
      <Stack
        direction="row"
        spacing={0.7}
        useFlexGap
        flexWrap="wrap"
        sx={{ fontSize: 14, lineHeight: 1, ...sx }}
      >
        {packageVersion &&
          badge(
            keenetic
              ? packageVersion.replace(/\+b(\d+)-(\d+)$/, ' — Build $1-$2')
              : formatPackageVersion(packageVersion),
            badges.core || badges.web || badges.build,
          )}
      </Stack>
      <PackageUpdateDialog
        open={open && !loginOpen && auth !== false}
        onClose={close}
        onCheck={() => void refreshSession(true)}
        onRecover={() => void refreshSession()}
        recovering={refreshingSession || !!intent}
        sessionError={sessionError}
        updates={updates}
        installed={packageVersion}
      />
      {open && loginOpen && auth !== false && (
        <LoginDialog
          onSuccess={() => refreshSession()}
          onCancel={() => {
            request.current++;
            setLoginOpen(false);
          }}
        />
      )}
    </>
  );
};

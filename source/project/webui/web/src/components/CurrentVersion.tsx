import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { Chip, Stack, Tooltip } from '@mui/material';
import type { SxProps } from '@mui/system/styleFunctionSx';

import { API } from '@/api/client';
import { packageUpdateBadges } from '@/api/packageUpdates';

import { LoginDialog } from '@/components/LoginDialog';
import { PackageUpdateDialog } from '@/components/PackageUpdateDialog';

import { useAppStore } from '@/store/useAppStore';

import { usePackageUpdates } from '@/hooks/usePackageUpdates';
import { useStatus } from '@/hooks/useStatus';
import { useTranslation } from '@/hooks/useTranslation';

import { formatPackageVersion } from '@/utils/packageVersion';

export const CurrentVersion = ({ sx }: { sx?: SxProps }) => {
  const {
    packageVersion,
    buildNumber,
    webVersion,
    csrfToken,
    anonym,
    authenticated,
  } = useStatus();
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const { refetch: refreshStatus } = API.status();
  const { auth } = useAppStore();
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
  const updates = usePackageUpdates(
    csrfToken,
    anonym || authenticated,
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
  const badge = (label: ReactNode, available: boolean) => (
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
            formatPackageVersion(packageVersion),
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

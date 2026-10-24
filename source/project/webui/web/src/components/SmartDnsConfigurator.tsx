import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Button, Divider, Stack, Typography } from '@mui/material';

import { DpiError } from '@/api/dpiClient';
import {
  applySmartDnsPreview,
  confirmSmartDns,
  getSmartDnsConfigStatus,
  getSmartDnsPreview,
  rollbackSmartDns,
  saveSmartDnsDraft,
  validateSmartDnsDraft,
  type ConfigStatus,
} from '@/api/smartDnsConfigClient';
import {
  acceptPreview,
  editProfile,
  emptyProfile,
  remainingSeconds,
  type EditorState,
  type Profile,
} from '@/api/smartDnsProfile';
import { newSupportSubmissionId } from '@/api/supportReport';

import { InlineHelp } from '@/components/InlineHelp';
import { SmartDnsPreview } from '@/components/SmartDnsPreview';
import { SmartDnsProfileForm } from '@/components/SmartDnsProfileForm';

import { useTranslation } from '@/hooks/useTranslation';

export const SmartDnsConfigurator = ({
  csrf,
  external,
}: {
  csrf: string;
  external: boolean;
}) => {
  const { t } = useTranslation();
  const [editor, setEditor] = useState<EditorState>({
    profile: emptyProfile(),
    revision: 0,
    preview: null,
  });
  const current = useRef(editor);
  current.current = editor;
  const [status, setStatus] = useState<ConfigStatus>();
  const [savedProfile, setSavedProfile] = useState<Profile | null>(null);
  const [resumeInfo, setResumeInfo] = useState<string | null>(null);
  const [routing, setRouting] = useState('unknown');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [clock, setClock] = useState({
    server: null as number | null,
    received: 0,
  });
  const [, setTick] = useState(0);
  const alive = useRef(true),
    initialized = useRef(false),
    inFlight = useRef(false),
    dirty = useRef(false);
  const reply = useRef(0),
    validatedRevision = useRef(0);
  const updateStatus = useCallback((s: ConfigStatus) => {
    setStatus(s);
    setClock({ server: s.deadline_remaining_s, received: performance.now() });
  }, []);
  const load = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    const seq = ++reply.current;
    try {
      const data = await getSmartDnsConfigStatus(csrf);
      if (!alive.current || seq !== reply.current) return;
      updateStatus(data.status);
      setSavedProfile(data.confirmed_profile || null);
      setResumeInfo(data.resume_code || null);
      setRouting(data.routing || 'unknown');
      if (!initialized.current) {
        initialized.current = true;
        const initial = {
          profile: data.draft || data.active_profile || emptyProfile(),
          revision: 0,
          preview: null,
        };
        current.current = initial;
        setEditor(initial);
      }
      const revision = current.current.revision;
      if (
        data.status.state === 'preview_ready' &&
        data.status.preview_id &&
        !dirty.current &&
        validatedRevision.current === revision
      ) {
        const preview = await getSmartDnsPreview(csrf, data.status.preview_id);
        if (alive.current && seq === reply.current)
          setEditor((s) => acceptPreview(s, revision, preview));
      }
    } catch (e) {
      if (alive.current && seq === reply.current)
        setError(e instanceof DpiError ? e.code : 'request_failed');
    } finally {
      inFlight.current = false;
    }
  }, [csrf, updateStatus]);
  useEffect(() => {
    const tracker = reply;
    alive.current = true;
    void load();
    const timer = setInterval(() => void load(), 2000);
    return () => {
      alive.current = false;
      tracker.current++;
      clearInterval(timer);
    };
  }, [load]);
  useEffect(() => {
    if (status?.state !== 'awaiting_confirmation') return;
    const timer = setInterval(() => setTick((v) => v + 1), 1000);
    return () => clearInterval(timer);
  }, [status?.state]);
  const left = remainingSeconds(
    clock.server,
    clock.received,
    performance.now(),
  );
  const change = (profile: Profile) => {
    dirty.current = true;
    setErrors({});
    setError('');
    setEditor((s) => editProfile(s, profile));
  };
  const perform = async (action: () => Promise<ConfigStatus>) => {
    if (busy) return;
    setBusy(true);
    setError('');
    setErrors({});
    reply.current++;
    try {
      const s = await action();
      if (alive.current) updateStatus(s);
    } catch (e) {
      if (alive.current) {
        setError(e instanceof DpiError ? e.code : 'request_failed');
        if (e instanceof DpiError && e.field)
          setErrors({ [e.field]: t('smartdns.form.invalid') });
      }
    } finally {
      if (alive.current) {
        setBusy(false);
        await load();
      }
    }
  };
  const validate = () =>
    void perform(async () => {
      const snapshot = current.current;
      const hash = await saveSmartDnsDraft(csrf, snapshot.profile);
      if (current.current.revision !== snapshot.revision)
        throw new DpiError('stale_draft');
      dirty.current = false;
      validatedRevision.current = snapshot.revision;
      return validateSmartDnsDraft(
        csrf,
        newSupportSubmissionId().replace(/-/g, ''),
        hash,
      );
    });
  const reloadDraft = () =>
    void perform(async () => {
      const data = await getSmartDnsConfigStatus(csrf);
      change(data.draft || data.active_profile || emptyProfile());
      return data.status;
    });
  const explanation = (code: string) => {
    if (code === 'hook_permissions')
      return t('smartdns.errors.hook_permissions');
    if (
      [
        'native_fallback_unavailable',
        'primary_dns_unverified',
        'baseline_unavailable',
      ].includes(code)
    )
      return t('smartdns.errors.native');
    if (
      [
        'hook_conflict',
        'existing_dns_rules',
        'invalid_state',
        'recovery_unavailable',
      ].includes(code)
    )
      return t('smartdns.errors.conflict');
    if (
      [
        'stale_draft',
        'stale_preview',
        'stale_baseline',
        'stale_state',
      ].includes(code)
    )
      return t('smartdns.errors.stale');
    if (
      [
        'dns_validation_failed',
        'invalid_configuration',
        'validation_failed',
      ].includes(code)
    )
      return t('smartdns.errors.validation');
    if (code === 'dns_restart_failed') return t('smartdns.errors.restart');
    if (code === 'insufficient_memory') return t('smartdns.errors.memory');
    if (code === 'invalid_profile') return t('smartdns.form.invalid');
    if (code === 'restore_required') return t('smartdns.restore_first');
    if (code === 'busy') return t('smartdns.errors.busy');
    if (code === 'timed_out') return t('smartdns.errors.timed_out');
    return t('smartdns.request_error');
  };
  const pending = [
    'validating',
    'applying',
    'awaiting_confirmation',
    'rolling_back',
  ].includes(status?.state || '');
  const connected = status?.state === 'confirmed';
  const canRestore = [
    'applying',
    'awaiting_confirmation',
    'confirmed',
    'rolling_back',
    'conflict',
  ].includes(status?.state || '');
  return (
    <Stack spacing={2}>
      <Divider />
      <Typography component="h2" variant="h6">
        {t('smartdns.configure')}
      </Typography>
      <Stack
        direction="row"
        spacing={1}
        alignItems="center"
        useFlexGap
        flexWrap="wrap"
      >
        <Typography variant="body2">{t('smartdns.short_sequence')}</Typography>
        <InlineHelp title={t('smartdns.guide')}>
          <Stack spacing={2}>
            <Typography>{t('smartdns.sequence')}</Typography>
            <Typography>{t('smartdns.browser_close')}</Typography>
            <Typography component="code">
              nfqws2-smartdns-control status
              <br />
              nfqws2-smartdns-control rollback
            </Typography>
          </Stack>
        </InlineHelp>
        <Button
          size="small"
          disabled={busy || pending || connected}
          onClick={reloadDraft}
        >
          {t('smartdns.reload_draft')}
        </Button>
      </Stack>
      {external && <Alert severity="info">{t('smartdns.external')}</Alert>}
      {resumeInfo && (
        <Alert severity="warning">
          <Stack spacing={1}>
            <Typography variant="body2">
              {t(
                resumeInfo === 'routing_lost'
                  ? 'smartdns.routing_lost'
                  : resumeInfo === 'routing_unknown'
                    ? 'smartdns.routing_unknown'
                    : 'smartdns.resume_info',
              )}
            </Typography>
            {savedProfile && !connected && (
              <Button
                disabled={busy || pending || connected}
                onClick={() => change(savedProfile)}
              >
                {t('smartdns.use_saved')}
              </Button>
            )}
          </Stack>
        </Alert>
      )}
      {connected && routing === 'managed' && (
        <Alert severity="success">{t('smartdns.confirmed')}</Alert>
      )}
      {status?.state === 'rolled_back' && (
        <Alert severity="info">{t('smartdns.rolled_back')}</Alert>
      )}
      {status?.state === 'validating' && (
        <Alert severity="info">{t('smartdns.validating')}</Alert>
      )}
      {['applying', 'rolling_back'].includes(status?.state || '') && (
        <Alert severity="info">{t('smartdns.switching')}</Alert>
      )}
      {status?.state === 'awaiting_confirmation' && (
        <Alert severity="info" role="status">
          <Stack spacing={1}>
            <Typography variant="body2">
              {t('smartdns.confirm_hint')}
            </Typography>
            <Typography variant="h6">
              {left ?? '…'} {t('smartdns.seconds')}
            </Typography>
            <Button
              autoFocus
              variant="contained"
              disabled={busy || left === 0}
              onClick={() =>
                void perform(() => confirmSmartDns(csrf, status.request_id!))
              }
            >
              {t('smartdns.confirm')}
            </Button>
          </Stack>
        </Alert>
      )}
      {(error || status?.code) && (
        <Alert severity="info">{explanation(error || status!.code!)}</Alert>
      )}
      {canRestore && (
        <Button
          color="warning"
          variant="outlined"
          disabled={busy || status?.state === 'rolling_back'}
          onClick={() =>
            void perform(async () => {
              const s = await rollbackSmartDns(csrf, status!.request_id!);
              if (s.state === 'rolled_back')
                setEditor((v) => ({ ...v, preview: null }));
              return s;
            })
          }
        >
          {t('smartdns.restore')}
        </Button>
      )}
      {connected && (
        <Typography variant="body2">{t('smartdns.restore_first')}</Typography>
      )}
      <SmartDnsProfileForm
        value={editor.profile}
        onChange={change}
        disabled={
          busy ||
          ['applying', 'awaiting_confirmation', 'rolling_back'].includes(
            status?.state || '',
          )
        }
        errors={errors}
      />
      <Button
        variant="outlined"
        disabled={
          busy ||
          pending ||
          connected ||
          !initialized.current ||
          editor.profile.upstreams.length === 0
        }
        onClick={validate}
      >
        {t('smartdns.validate')}
      </Button>
      {dirty.current && (
        <Typography variant="caption">{t('smartdns.edited')}</Typography>
      )}
      {editor.preview &&
        !dirty.current &&
        status?.state === 'preview_ready' && (
          <SmartDnsPreview
            profile={editor.profile}
            preview={editor.preview}
            disabled={busy || external}
            onApply={() =>
              void perform(async () => {
                const preview = current.current.preview;
                if (!preview) throw new DpiError('stale_preview');
                return applySmartDnsPreview(
                  csrf,
                  newSupportSubmissionId().replace(/-/g, ''),
                  preview,
                );
              })
            }
          />
        )}
    </Stack>
  );
};

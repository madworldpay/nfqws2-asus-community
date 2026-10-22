import { useCallback, useEffect, useRef, useState } from 'react';
import type { TranslationSchema } from '@/context/TranslationProvider';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';
import {
  Alert,
  Button,
  Checkbox,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControlLabel,
  IconButton,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material';

import { readBulkResources, selectAllDns } from '@/api/bulkSelection';
import { API } from '@/api/client';
import {
  autoLocation,
  connectShareChannel,
  getShareState,
  getStrategyDraft,
  prepareShare,
  saveShare,
  sendShare,
  ShareError,
  strategyContext,
  type PreparedShare,
  type ShareLocation,
  type ShareSelection,
  type ShareState,
} from '@/api/shareClient';
import {
  analyzeShare,
  getShareDnsSources,
  getShareInventory,
  readShareResource,
  type DnsSelection,
} from '@/api/shareResourcesClient';
import {
  canChooseReportLocation,
  downloadSupportReport,
  newSupportSubmissionId,
  SupportReportError,
  type SupportMailResult,
  type SupportReportFile,
} from '@/api/supportReport';

import { InlineHelp } from '@/components/InlineHelp';
import { ShareContextSection } from '@/components/ShareContextSection';
import { ShareDnsSection } from '@/components/ShareDnsSection';
import { ShareDpiSection } from '@/components/ShareDpiSection';
import {
  ShareFilesSection,
  type ShareFilesForm,
} from '@/components/ShareFilesSection';
import { SharePreview } from '@/components/SharePreview';
import {
  ShareStrategySection,
  type ShareStrategyForm,
} from '@/components/ShareStrategySection';

import { useAppStore } from '@/store/useAppStore';

import { useStatus } from '@/hooks/useStatus';
import { useTranslation } from '@/hooks/useTranslation';

import { shareMailUnavailableReason } from '@/utils/shareAvailability';

type ShareErrorCode = keyof TranslationSchema['share']['errors'];
const emptyStrategyForm = (): ShareStrategyForm => ({
  selected: [],
  full: false,
  context: {
    purpose: '',
    operator: '',
    comment: '',
    region: '',
    share_location: false,
  },
  locationEdited: false,
});
export const ShareMailNotice = ({ mail }: { mail?: ShareState['mail'] }) => {
  const { t } = useTranslation();
  const reason = shareMailUnavailableReason(mail);
  return reason && reason !== 'loading' ? (
    <Alert severity="info">{t(`share.mail_availability.${reason}`)}</Alert>
  ) : null;
};

export const ShareConnectButton = ({
  mail,
  busy,
  onConnect,
}: {
  mail?: ShareState['mail'];
  busy: boolean;
  onConnect: VoidFunction;
}) => {
  const { t } = useTranslation();
  return mail?.public_setup_available === true &&
    mail.configured === false &&
    mail.code === 'not_configured' ? (
    <Button disabled={busy} onClick={onConnect}>
      {t('share.connect_channel')}
    </Button>
  ) : null;
};

export const ShareDeliveryButtons = ({
  mail,
  snapshot,
  busy,
  disabled,
  retry,
  onSave,
  onSend,
}: {
  mail?: ShareState['mail'];
  snapshot?: PreparedShare;
  busy: boolean;
  disabled: boolean;
  retry: boolean;
  onSave: VoidFunction;
  onSend: VoidFunction;
}) => {
  const { t } = useTranslation();
  const mailAvailable = shareMailUnavailableReason(mail) === null;
  return (
    <>
      <Button disabled={busy || !snapshot} onClick={onSave}>
        {t(
          canChooseReportLocation() ? 'report.choose_file' : 'report.download',
        )}
      </Button>
      <Button
        variant="contained"
        disabled={disabled || !snapshot || !mailAvailable}
        onClick={onSend}
      >
        {t(retry ? 'report.send_again' : 'report.send')}
      </Button>
    </>
  );
};

export const ShareDialog = ({
  onClose,
  onSent,
}: {
  onClose: () => void;
  onSent: () => void;
}) => {
  const { t } = useTranslation();
  const { csrfToken } = useStatus();
  const [token, setToken] = useState(csrfToken ?? '');
  const [state, setState] = useState<ShareState>();
  const [reportSelected, setReportSelected] = useState(false);
  const [strategySelected, setStrategySelected] = useState(false);
  const [report, setReport] = useState<SupportReportFile>();
  const [dpi, setDpi] = useState<ShareSelection['dpi']>();
  const [form, setForm] = useState<ShareStrategyForm>(emptyStrategyForm);
  const [files, setFiles] = useState<ShareFilesForm>({
    selected: [],
    copies: {},
  });
  const [dns, setDns] = useState<DnsSelection[]>([]);
  const [link, setLink] = useState(false);
  const [snapshot, setSnapshot] = useState<PreparedShare>();
  const [result, setResult] = useState<SupportMailResult>();
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState('');
  const [error, setError] = useState<ShareErrorCode | ''>('');
  const [help, setHelp] = useState(false);
  const [saved, setSaved] = useState<'native' | 'browser'>();
  const revision = useRef({ value: 0 });
  const pending = useRef(false);
  const mounted = useRef(true);
  const invalidate = useCallback(() => {
    revision.current.value++;
    setSnapshot(undefined);
    setResult(undefined);
    setSaved(undefined);
    setError('');
  }, []);
  const fail = useCallback((e: unknown) => {
    const code =
      e instanceof ShareError || e instanceof SupportReportError
        ? e.code
        : 'unavailable';
    if (code === 'unauthorized') useAppStore.getState().setAuth(false);
    setError(
      [
        'unsafe_strategy',
        'invalid_strategy',
        'unsupported_config',
        'strategy_unavailable',
        'unsupported_report',
        'source_changed',
        'insufficient_space',
        'invalid_proof',
        'busy',
        'forbidden',
        'unauthorized',
        'output_limit',
        'identity_unavailable',
        'incomplete_reason_required',
        'invalid_resource',
        'invalid_dns_resource',
        'private_dns_url',
        'file_too_large',
      ].includes(code)
        ? (code as ShareErrorCode)
        : 'unavailable',
    );
  }, []);
  const updateForm = useCallback(
    (update: (old: ShareStrategyForm) => ShareStrategyForm) => {
      invalidate();
      setForm(update);
    },
    [invalidate],
  );
  const updateFiles = useCallback(
    (update: (old: ShareFilesForm) => ShareFilesForm) => {
      invalidate();
      setFiles(update);
    },
    [invalidate],
  );
  const updateDns = useCallback(
    (value: DnsSelection[]) => {
      invalidate();
      setDns(value);
    },
    [invalidate],
  );
  const location = useCallback(
    (value: ShareLocation) => {
      updateForm((old) => ({
        ...old,
        context: {
          ...old.context,
          region: autoLocation(old.context.region, old.locationEdited, value),
        },
      }));
    },
    [updateForm],
  );
  const changeDpi = useCallback(
    (value: ShareSelection['dpi']) => {
      invalidate();
      setDpi(value);
    },
    [invalidate],
  );
  useEffect(() => {
    mounted.current = true;
    const version = revision.current;
    return () => {
      mounted.current = false;
      version.value++;
    };
  }, []);
  useEffect(() => {
    let active = true;
    void (async () => {
      let csrf = csrfToken;
      if (!csrf) {
        const { data } = await API.login('', '');
        csrf = data?.csrf_token;
      }
      if (!csrf) throw new ShareError('unauthorized');
      if (active) setToken(csrf);
      const status = await getShareState(csrf);
      if (active) setState(status);
    })().catch((e) => {
      if (active) fail(e);
    });
    return () => {
      active = false;
    };
  }, [csrfToken, fail]);
  const terminal = result?.state === 'accepted' || result?.state === 'unknown';
  const disabled = busy || terminal;
  const perform = async (name: string, fn: () => Promise<void>) => {
    if (pending.current || terminal) return;
    pending.current = true;
    setBusy(true);
    setPhase(name);
    setError('');
    try {
      await fn();
    } catch (e) {
      if (mounted.current) fail(e);
    } finally {
      pending.current = false;
      if (mounted.current) {
        setBusy(false);
        setPhase('');
      }
    }
  };
  const selectEverything = () =>
    perform('collect', async () => {
      invalidate();
      const draft = form.draft ?? (await getStrategyDraft(token));
      const inventory = await getShareInventory(token);
      const sources = await getShareDnsSources(token);
      const picked = await readBulkResources(
        inventory.files,
        files.copies,
        (meta) => readShareResource(token, meta),
      );
      const diagnostic = report?.proof
        ? report
        : await downloadSupportReport(token, () =>
            useAppStore.getState().setAuth(false),
          );
      const latest = state?.saved.reports[0];
      const legacy = state?.dpi.history.find(
        (r) => r.kind === 'run' && r.completed_tests.length > 0,
      );
      if (!mounted.current) return;
      invalidate();
      setReport(diagnostic);
      setReportSelected(true);
      setStrategySelected(true);
      setForm((old) => ({ ...old, draft, full: true }));
      setFiles({ inventory, selected: picked.selected, copies: picked.copies });
      setDns(selectAllDns(sources.sources, dns));
      setDpi(
        dpi ??
          (latest
            ? { kind: 'saved', id: latest.id }
            : legacy
              ? { kind: 'legacy', id: legacy.id }
              : undefined),
      );
    });
  const clearEverything = () => {
    invalidate();
    setReportSelected(false);
    setStrategySelected(false);
    setDpi(undefined);
    setFiles((old) => ({ ...old, selected: [] }));
    setDns([]);
  };
  const collect = () =>
    perform('collect', async () => {
      invalidate();
      const file = await downloadSupportReport(token, () =>
        useAppStore.getState().setAuth(false),
      );
      if (mounted.current) setReport(file);
    });
  const validStrategy =
    !strategySelected ||
    !!(
      form.draft &&
      form.context.purpose.trim() &&
      form.context.operator.trim() &&
      (form.full || form.selected.length)
    );
  const hasContributions =
    strategySelected || files.selected.length > 0 || dns.length > 0;
  const mailAvailable = shareMailUnavailableReason(state?.mail) === null;
  const canPrepare =
    !!token &&
    (reportSelected || !!dpi || hasContributions) &&
    (!hasContributions ||
      !!(form.context.purpose.trim() && form.context.operator.trim())) &&
    files.selected.every((id) => !!files.copies[id]) &&
    (!reportSelected || !!report?.proof) &&
    validStrategy;
  const prepare = () =>
    perform('prepare', async () => {
      invalidate();
      const seq = revision.current.value;
      const selection: ShareSelection = {
        version: 4,
        link_installation: link,
      };
      if (reportSelected && report?.proof)
        selection.report = {
          raw: await report.blob.text(),
          filename: report.filename,
          proof: report.proof,
        };
      if (dpi) selection.dpi = dpi;
      if (strategySelected && form.draft) {
        const context = strategyContext(form.context);
        selection.strategy = form.full
          ? { mode: 'config', config: form.draft.config, context }
          : {
              mode: 'blocks',
              draft: {
                blocks: form.draft.blocks.filter((b) =>
                  form.selected.includes(b.key),
                ),
              },
              context,
            };
      }
      if (hasContributions) {
        selection.context = strategyContext(form.context);
        selection.resources = {
          files: files.selected.map((id) => {
            const copy = files.copies[id];
            return {
              id,
              source_sha256: copy.sha256,
              ...(copy.encoding === 'utf8' ? { text: copy.text ?? '' } : {}),
            };
          }),
          missing_reason: '',
        };
        if (dns.length) selection.dns = dns;
        if (selection.strategy) {
          const checked = await analyzeShare(
            token,
            selection.strategy,
            files.selected,
          );
          if (!mounted.current || seq !== revision.current.value) return;
          selection.analysis_config_sha256 = checked.config_sha256;
        }
      }
      const prepared = await prepareShare(selection, token);
      if (mounted.current && seq === revision.current.value)
        setSnapshot(prepared);
    });
  const send = () =>
    perform('send', async () => {
      if (!snapshot || !mailAvailable) return;
      const value = await sendShare(snapshot, token, newSupportSubmissionId());
      if (mounted.current) {
        setResult(value);
        if (value.state === 'accepted') onSent();
      }
    });
  const connectChannel = () =>
    perform('connect', async () => {
      await connectShareChannel(token);
      const status = await getShareState(token);
      if (mounted.current) setState(status);
    });
  // Invoke the picker synchronously from this click before awaiting other work.
  const save = () => {
    if (!snapshot || pending.current) return;
    pending.current = true;
    setBusy(true);
    setError('');
    void saveShare(snapshot)
      .then(
        (value) => {
          if (mounted.current) setSaved(value);
        },
        (e) => {
          if (
            mounted.current &&
            !(e instanceof DOMException && e.name === 'AbortError')
          )
            fail(e);
        },
      )
      .finally(() => {
        pending.current = false;
        if (mounted.current) setBusy(false);
      });
  };
  return (
    <Dialog
      open
      fullWidth
      maxWidth="md"
      onClose={() => !pending.current && onClose()}
    >
      <DialogTitle>{t('share.title')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2}>
          <Typography variant="body2">{t('share.intro')}</Typography>
          <ShareMailNotice mail={state?.mail} />
          <ShareConnectButton
            mail={state?.mail}
            busy={disabled || !token}
            onConnect={() => void connectChannel()}
          />
          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
            <Button
              disabled={disabled || !token || !state}
              onClick={() => void selectEverything()}
            >
              {t('share.select_all')}
            </Button>
            <Button disabled={disabled} onClick={clearEverything}>
              {t('share.clear_selection')}
            </Button>
          </Stack>
          <FormControlLabel
            control={
              <Checkbox
                checked={reportSelected}
                disabled={disabled}
                onChange={(_, checked) => {
                  invalidate();
                  setReportSelected(checked);
                }}
              />
            }
            label={t('share.kinds.report')}
          />
          <Stack direction="row" alignItems="center" useFlexGap flexWrap="wrap">
            <Button
              disabled={disabled || !token}
              onClick={() => void collect()}
            >
              {t('report.collect')}
            </Button>
            <Tooltip title={t('report.help_title')}>
              <IconButton
                aria-label={t('report.help_title')}
                onClick={() => setHelp(!help)}
              >
                <HelpOutlineIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Stack>
          {help && (
            <Alert severity="info">
              <Stack spacing={1}>
                <Typography>{t('report.help_purpose')}</Typography>
                <Typography>{t('report.help_safety')}</Typography>
                <Typography>{t('report.help_privacy')}</Typography>
              </Stack>
            </Alert>
          )}
          {report && (
            <Typography variant="caption" sx={{ overflowWrap: 'anywhere' }}>
              {report.filename}
            </Typography>
          )}
          <Divider />
          {state ? (
            <ShareDpiSection
              csrfToken={token}
              state={state}
              selection={dpi}
              disabled={disabled}
              onChange={changeDpi}
              onState={setState}
              onError={fail}
            />
          ) : (
            <Typography variant="body2">{t('share.loading')}</Typography>
          )}
          <Divider />
          <FormControlLabel
            control={
              <Checkbox
                checked={strategySelected}
                disabled={disabled}
                onChange={(_, checked) => {
                  invalidate();
                  setStrategySelected(checked);
                }}
              />
            }
            label={t('share.kinds.strategy')}
          />
          {strategySelected && token && (
            <ShareStrategySection
              csrfToken={token}
              blocksOnly
              value={form}
              disabled={disabled}
              onChange={updateForm}
              onLocation={location}
              onError={fail}
            />
          )}
          <Divider />
          {token && (
            <ShareFilesSection
              csrfToken={token}
              value={files}
              disabled={disabled}
              onChange={updateFiles}
              onError={fail}
            />
          )}
          <Divider />
          {token && (
            <ShareDnsSection
              csrfToken={token}
              value={dns}
              disabled={disabled}
              onChange={updateDns}
              onError={fail}
            />
          )}
          {hasContributions && token && (
            <>
              <Divider />
              <ShareContextSection
                csrfToken={token}
                value={form}
                disabled={disabled}
                onChange={updateForm}
                onLocation={location}
              />
            </>
          )}
          <Divider />
          <FormControlLabel
            control={
              <Checkbox
                checked={link}
                disabled={disabled}
                onChange={(_, checked) => {
                  invalidate();
                  setLink(checked);
                }}
              />
            }
            label={t('share.link_installation')}
          />
          <Typography variant="caption">{t('share.link_help')}</Typography>
          {error && (
            <Alert severity="error">{t(`share.errors.${error}`)}</Alert>
          )}
          {snapshot && <SharePreview snapshot={snapshot} />}
          {snapshot && (
            <Typography variant="body2">
              {t(
                canChooseReportLocation()
                  ? 'report.choose_hint'
                  : 'report.browser_hint',
              )}
            </Typography>
          )}
          {saved && (
            <Alert severity="success">{t(`report.saved_${saved}`)}</Alert>
          )}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ flexWrap: 'wrap', gap: 0.5 }}>
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{ width: '100%', px: 1, pb: 0.5 }}
        >
          {t('share.preview_steps')}
        </Typography>
        {busy && (
          <Stack
            direction="row"
            spacing={1}
            alignItems="center"
            sx={{ width: '100%', p: 1 }}
          >
            <CircularProgress size={20} />
            <Typography variant="body2">
              {t(phase === 'collect' ? 'report.collecting' : 'share.working')}
            </Typography>
          </Stack>
        )}
        {result && (
          <Alert
            sx={{ width: '100%' }}
            severity={
              result.state === 'accepted'
                ? 'success'
                : result.state === 'failed_safe'
                  ? 'error'
                  : 'warning'
            }
          >
            {t(`report.mail_states.${result.state}`)}
          </Alert>
        )}
        <Button disabled={busy} onClick={onClose}>
          {t('common.close')}
        </Button>
        <Button
          disabled={disabled || !canPrepare}
          onClick={() => void prepare()}
        >
          {t('share.preview')}
        </Button>
        <InlineHelp title={t('share.preview')}>
          <Typography>{t('share.preview_help')}</Typography>
        </InlineHelp>
        <ShareDeliveryButtons
          mail={state?.mail}
          snapshot={snapshot}
          busy={busy}
          disabled={disabled}
          retry={result?.state === 'failed_safe'}
          onSave={save}
          onSend={() => void send()}
        />
      </DialogActions>
    </Dialog>
  );
};

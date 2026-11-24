import { useCallback, useEffect, useId, useRef, useState } from 'react';
import type { TranslationSchema } from '@/context/TranslationProvider';
import en from '@/translations/en.json';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import FileDownloadOutlinedIcon from '@mui/icons-material/FileDownloadOutlined';
import {
  Alert,
  Box,
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
  Tab,
  Tabs,
  Typography,
} from '@mui/material';

import { selectAllImport } from '@/api/bulkSelection';
import { API } from '@/api/client';
import type { ImportAddonSelection } from '@/api/importAddonClient';
import {
  applyImport,
  convertKeeneticImport,
  emptyImportSelection,
  importOutcomeUnknown,
  importStatus,
  inspectImport,
  newImportRequestId,
  prepareImport,
  readImportFiles,
  readLocalPreset,
  readMeasuredImport,
  selectImportDependencies,
  undoImport,
  type ImportDocument,
  type ImportPlan,
  type ImportSelection,
  type ImportStatus,
  type MeasuredImport,
} from '@/api/importClient';
import {
  loadCatalogDocument,
  type CatalogProfile,
} from '@/api/profileCatalogClient';
import { ShareError } from '@/api/shareClient';

import { Editor } from '@/components/Editor';
import { ImportAddons } from '@/components/ImportAddons';
import { ImportPreview } from '@/components/ImportPreview';
import { ImportSelectionView } from '@/components/ImportSelection';
import { ImportStrategies } from '@/components/ImportStrategies';
import { InlineHelp } from '@/components/InlineHelp';
import { InlineNfqwsRestart } from '@/components/InlineNfqwsRestart';

import { useAppStore } from '@/store/useAppStore';

import { useStatus } from '@/hooks/useStatus';
import { useTranslation } from '@/hooks/useTranslation';

export const ImportDialog = ({
  onClose,
  measured,
}: {
  onClose: VoidFunction;
  measured?: MeasuredImport;
}) => {
  const { t } = useTranslation();
  const { csrfToken } = useStatus();
  const { needSave, importRestartPending, setImportRestartPending } =
    useAppStore();
  const [documents, setDocuments] = useState<string[]>([]);
  const [doc, setDoc] = useState<ImportDocument>();
  const [catalogChoice, setCatalogChoice] = useState<CatalogProfile>();
  const [localPresetTitle, setLocalPresetTitle] = useState<string>();
  const [sourceGeneration, setSourceGeneration] = useState(0);
  const [selection, setSelection] =
    useState<ImportSelection>(emptyImportSelection);
  const [plan, setPlan] = useState<ImportPlan>();
  const [status, setStatus] = useState<ImportStatus>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<
    keyof TranslationSchema['import']['errors'] | ''
  >('');
  const [saved, setSaved] = useState(false);
  const [servicePending, setServicePending] = useState(false);
  const [serviceApplied, setServiceApplied] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [showStrategies, setShowStrategies] = useState(false);
  const [showKeenetic, setShowKeenetic] = useState(false);
  const [keeneticText, setKeeneticText] = useState('');
  const [showDetails, setShowDetails] = useState(false);
  const [detailsTab, setDetailsTab] = useState<
    'contents' | 'changes' | 'addons'
  >('contents');
  const keeneticId = useId();
  const titleId = useId();
  const stepsId = useId();
  const tabsId = useId();
  const presetTitle = localPresetTitle ?? catalogChoice?.title;
  const detailed = !presetTitle || showDetails;
  const previewRef = useRef<HTMLDivElement>(null);
  const showingPreview = Boolean(plan) && !presetTitle;
  const source = useRef<'keenetic' | 'other' | null>(null);
  const mounted = useRef(false);
  const pending = useRef(false);
  const requestId = useRef('');
  const pendingUndo = useRef<{ id: string; configChanged: boolean } | null>(
    null,
  );
  const chosenFiles = useRef<File[]>([]);
  const loadedMeasurement = useRef<MeasuredImport | undefined>(undefined);
  const revision = useRef(0);
  const fail = useCallback((e: unknown) => {
    if (mounted.current) {
      const code = e instanceof ShareError ? e.code : 'unavailable';
      setError(
        Object.prototype.hasOwnProperty.call(en.import.errors, code)
          ? (code as keyof TranslationSchema['import']['errors'])
          : 'unavailable',
      );
    }
  }, []);
  useEffect(() => {
    mounted.current = true;
    if (csrfToken)
      void importStatus(csrfToken).then((s) => {
        if (mounted.current) setStatus(s);
      }, fail);
    return () => {
      mounted.current = false;
    };
  }, [csrfToken, fail]);
  useEffect(() => {
    if (showingPreview) previewRef.current?.scrollIntoView({ block: 'start' });
  }, [showingPreview]);
  const reload = async () => {
    await Promise.all([
      API.invalidateFileContent('nfqws2.conf'),
      API.invalidateListFiles(),
    ]);
  };
  const edit = useCallback(
    (
      value: ImportSelection | ((current: ImportSelection) => ImportSelection),
    ) => {
      revision.current++;
      setSelection((current) => ({
        ...(typeof value === 'function' ? value(current) : value),
        trusted_lua: false,
      }));
      setPlan(undefined);
      requestId.current = '';
      setSaved(false);
      setError('');
    },
    [],
  );
  const editAddons = useCallback(
    (addons: ImportAddonSelection[]) => {
      edit((current) => {
        const next = { ...current };
        if (addons.length) next.addons = addons;
        else delete next.addons;
        return next;
      });
    },
    [edit],
  );
  const run = useCallback(
    async (fn: () => Promise<void>) => {
      if (pending.current || !csrfToken) return;
      pending.current = true;
      setBusy(true);
      setError('');
      try {
        await fn();
      } catch (e) {
        fail(e);
      } finally {
        pending.current = false;
        if (mounted.current) setBusy(false);
      }
    },
    [csrfToken, fail],
  );
  const resetDocuments = useCallback(() => {
    source.current = null;
    chosenFiles.current = [];
    setSourceGeneration((value) => value + 1);
    revision.current++;
    setDoc(undefined);
    setCatalogChoice(undefined);
    setLocalPresetTitle(undefined);
    setDocuments([]);
    setPlan(undefined);
    setSelection(emptyImportSelection());
    setShowDetails(false);
    setDetailsTab('contents');
    requestId.current = '';
    setSaved(false);
    setUncertain(false);
  }, []);
  const loadDocuments = useCallback(
    (
      read: () => Promise<string[]>,
      {
        files = [],
        keenetic = false,
        catalogProfile,
        presetTitle,
      }: {
        files?: File[];
        keenetic?: boolean;
        catalogProfile?: CatalogProfile;
        presetTitle?: string;
      } = {},
    ) => {
      if (pending.current || !csrfToken) return;
      resetDocuments();
      source.current = keenetic ? 'keenetic' : 'other';
      chosenFiles.current = files;
      const rev = revision.current;
      void run(async () => {
        const raw = await read();
        const parsed = await inspectImport(csrfToken!, raw);
        const selected = selectAllImport(parsed, {
          ...emptyImportSelection(),
          allow_shared_impact: true,
          allow_incomplete: true,
        });
        if (!mounted.current || rev !== revision.current) return;
        setDocuments(raw);
        setDoc(parsed);
        setCatalogChoice(catalogProfile);
        setSelection(selected);
        if (presetTitle) setLocalPresetTitle(presetTitle);
        if (keenetic || presetTitle || catalogProfile) {
          const prepared = await prepareImport(csrfToken!, raw, selected);
          if (mounted.current && rev === revision.current) {
            setPlan(prepared);
            requestId.current = newImportRequestId();
          }
        }
      });
    },
    [csrfToken, resetDocuments, run],
  );
  useEffect(() => {
    if (
      !measured ||
      !csrfToken ||
      needSave ||
      loadedMeasurement.current === measured
    )
      return;
    loadedMeasurement.current = measured;
    loadDocuments(async () => [await readMeasuredImport(csrfToken, measured)]);
  }, [csrfToken, loadDocuments, measured, needSave]);
  const editKeenetic = (value: string) => {
    if (pending.current || uncertain || needSave) return;
    setKeeneticText(value);
    setError('');
    if (source.current === 'keenetic') {
      resetDocuments();
    }
  };
  const backToPresets = () => {
    setError('');
    resetDocuments();
  };
  const load = (files: File[]) =>
    loadDocuments(() => readImportFiles(files), { files });
  const review = (trustedLua?: boolean) =>
    void run(async () => {
      const next = { ...selection, trusted_lua: trustedLua ?? false };
      requestId.current = '';
      if (trustedLua === undefined) setPlan(undefined);
      setSelection(next);
      const rev = revision.current;
      try {
        const p = await prepareImport(csrfToken!, documents, next);
        if (mounted.current && rev === revision.current) {
          setPlan(p);
          requestId.current = newImportRequestId();
        }
      } catch (e) {
        if (mounted.current && rev === revision.current) {
          setPlan(undefined);
          setSelection({ ...next, trusted_lua: false });
        }
        throw e;
      }
    });
  const markRestartPending = (configChanged: boolean) => {
    if (!configChanged) return;
    setServiceApplied(false);
    setImportRestartPending(true);
  };
  const refresh = () =>
    void run(async () => {
      const s = await importStatus(csrfToken!);
      if (!mounted.current) return;
      setStatus(s);
      if (pendingUndo.current) {
        if (s.id === pendingUndo.current.id && s.state === 'undone') {
          markRestartPending(pendingUndo.current.configChanged);
          pendingUndo.current = null;
          setSaved(false);
          setUncertain(false);
          setPlan(undefined);
          await reload();
        }
        return;
      }
      if (s.id === requestId.current && s.state === 'committed') {
        setSaved(true);
        markRestartPending(s.config_saved);
        setUncertain(false);
        if (!presetTitle) setPlan(undefined);
        await reload();
      } else if (
        s.id === requestId.current &&
        ['rolled_back', 'undone'].includes(s.state)
      ) {
        setUncertain(false);
        setPlan(undefined);
      }
    });
  const apply = () =>
    void run(async () => {
      if (needSave || saved) return;
      let prepared = plan;
      if (!prepared && presetTitle && !uncertain) {
        const rev = revision.current;
        prepared = await prepareImport(csrfToken!, documents, selection);
        if (!mounted.current || rev !== revision.current) return;
        setPlan(prepared);
        requestId.current = newImportRequestId();
      }
      if (!prepared?.ready || !prepared.proof || !requestId.current) return;
      let result: ImportStatus;
      try {
        result = await applyImport(
          csrfToken!,
          documents,
          selection,
          prepared.proof,
          requestId.current,
        );
      } catch (e) {
        if (mounted.current) {
          const unknown = importOutcomeUnknown(e);
          setUncertain(unknown);
          if (!unknown) setPlan(undefined);
        }
        throw e;
      }
      if (!mounted.current) return;
      setStatus(result);
      setUncertain(false);
      setSaved(result.state === 'committed');
      markRestartPending(result.state === 'committed' && result.config_saved);
      if (!presetTitle || result.state !== 'committed') setPlan(undefined);
      await reload();
      const fresh = await importStatus(csrfToken!);
      if (mounted.current) setStatus(fresh);
    });
  const undo = () =>
    void run(async () => {
      if (needSave || !status?.id || !status.undo_proof) return;
      pendingUndo.current = {
        id: status.id,
        configChanged: status.config_saved,
      };
      setUncertain(true);
      setPlan(undefined);
      const s = await undoImport(csrfToken!, status.id, status.undo_proof);
      if (s.id !== pendingUndo.current.id || s.state !== 'undone')
        throw new Error('unconfirmed_undo');
      if (mounted.current) {
        markRestartPending(pendingUndo.current.configChanged);
        pendingUndo.current = null;
        setStatus(s);
        setSaved(false);
        setPlan(undefined);
        setUncertain(false);
      }
      await reload();
    });
  const disabled = busy || uncertain || servicePending;
  const restartReady =
    importRestartPending &&
    !uncertain &&
    !pendingUndo.current &&
    status &&
    ['committed', 'undone'].includes(status.state);
  const onServiceApplied = () => {
    setImportRestartPending(false);
    setServiceApplied(true);
  };
  const luaTrust = localPresetTitle
    ? undefined
    : {
        checked: selection.trusted_lua,
        disabled: disabled || needSave || saved,
        onChange: review,
      };
  const panelProps = (tab: typeof detailsTab) =>
    presetTitle
      ? {
          role: 'tabpanel',
          id: `${tabsId}-panel-${tab}`,
          'aria-labelledby': `${tabsId}-tab-${tab}`,
          hidden: detailsTab !== tab,
        }
      : {};
  return (
    <Dialog
      open
      fullWidth
      maxWidth="md"
      scroll="paper"
      aria-labelledby={titleId}
      onClose={() => {
        if (!busy && !servicePending) onClose();
      }}
    >
      <DialogTitle
        id={titleId}
        sx={{ display: 'flex', gap: 1, alignItems: 'center' }}
      >
        {presetTitle ? (
          <IconButton
            aria-label={t('import.preset.back')}
            disabled={disabled}
            onClick={backToPresets}
          >
            <ArrowBackIcon />
          </IconButton>
        ) : (
          <FileDownloadOutlinedIcon color="primary" />
        )}
        {t('import.title')}
      </DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2} sx={{ minWidth: 0 }}>
          {!presetTitle && (
            <Box
              component="section"
              aria-labelledby={stepsId}
              sx={{
                p: 2,
                border: '1px solid',
                borderColor: 'primary.main',
                borderRadius: 1,
              }}
            >
              <Typography
                id={stepsId}
                component="h3"
                variant="subtitle1"
                fontWeight={600}
              >
                {t('import.steps.title')}
              </Typography>
              <Box
                component="ol"
                sx={{ pl: 2.5, my: 1, '& li + li': { mt: 0.75 } }}
              >
                <Typography component="li" variant="body2">
                  {t('import.steps.choose')}
                </Typography>
                <Typography component="li" variant="body2">
                  {t('import.steps.preview')}
                </Typography>
                <Typography component="li" variant="body2">
                  {t('import.steps.save')}
                </Typography>
                <Typography component="li" variant="body2">
                  {t('import.steps.start')}
                </Typography>
              </Box>
              <Typography variant="body2" color="text.secondary">
                {t('import.steps.safety')}
              </Typography>
            </Box>
          )}
          {needSave && <Alert severity="info">{t('import.save_first')}</Alert>}
          {!!error && (
            <Alert severity="info">
              {t(`import.errors.${error}`) || t('import.error')}
            </Alert>
          )}
          {uncertain && (
            <Alert
              severity="info"
              action={
                presetTitle && (
                  <Button
                    color="inherit"
                    disabled={busy || !csrfToken}
                    onClick={refresh}
                  >
                    {t('import.check_status')}
                  </Button>
                )
              }
            >
              {t(
                pendingUndo.current
                  ? 'import.uncertain_undo'
                  : 'import.uncertain',
              )}
            </Alert>
          )}
          {saved && <Alert severity="success">{t('import.saved')}</Alert>}
          {serviceApplied && (
            <Alert severity="success">{t('import.service_done')}</Alert>
          )}
          {!presetTitle && restartReady && (
            <Stack spacing={1}>
              {!saved && (
                <Alert severity="info">{t('import.restart_pending')}</Alert>
              )}
              <InlineNfqwsRestart
                disabled={busy}
                onPendingChange={setServicePending}
                onApplied={onServiceApplied}
              />
            </Stack>
          )}
          {status?.state === 'undone' && (
            <Alert severity="success">{t('import.undone')}</Alert>
          )}
          {status?.state === 'restore_required' && (
            <Alert severity="warning">{t('import.restore_required')}</Alert>
          )}
          {status &&
            ['prepared', 'committing', 'undoing'].includes(status.state) && (
              <Alert severity="info">{t('import.pending')}</Alert>
            )}
          {!presetTitle && (
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
              <Button
                variant="contained"
                component="label"
                disabled={!csrfToken || disabled || needSave}
              >
                {t('import.choose')}
                <input
                  type="file"
                  hidden
                  accept=".json,application/json"
                  multiple
                  disabled={!csrfToken || disabled || needSave}
                  onChange={(e) => {
                    const files = Array.from(e.target.files ?? []);
                    e.target.value = '';
                    if (files.length) load(files);
                  }}
                />
              </Button>
              <Button
                variant={showStrategies ? 'contained' : 'outlined'}
                disabled={disabled || needSave || !csrfToken}
                aria-expanded={showStrategies}
                onClick={() => {
                  setShowStrategies((value) => !value);
                  setShowKeenetic(false);
                }}
              >
                {t('import.strategies.choose')}
              </Button>
              <Button
                variant={showKeenetic ? 'contained' : 'outlined'}
                disabled={!csrfToken || disabled || needSave}
                aria-expanded={showKeenetic}
                aria-controls={keeneticId}
                onClick={() => {
                  setShowKeenetic((value) => !value);
                  setShowStrategies(false);
                }}
              >
                {t('import.keenetic.choose')}
              </Button>
              {!!chosenFiles.current.length && !doc && (
                <Button
                  disabled={busy || !csrfToken}
                  onClick={() => load(chosenFiles.current)}
                >
                  {t('import.retry')}
                </Button>
              )}
              <Button disabled={busy || !csrfToken} onClick={refresh}>
                {t('import.check_status')}
              </Button>
              {status?.can_undo && (
                <Button
                  color="warning"
                  disabled={disabled || needSave || !status.undo_proof}
                  onClick={undo}
                >
                  {t('import.undo')}
                </Button>
              )}
            </Stack>
          )}
          {showStrategies && csrfToken && (
            <Box hidden={Boolean(presetTitle)}>
              <ImportStrategies
                key={csrfToken}
                csrf={csrfToken}
                disabled={disabled || needSave}
                onSelectLocal={(id, presetTitle) =>
                  loadDocuments(() => readLocalPreset(csrfToken, id), {
                    presetTitle,
                  })
                }
                onSelectProfile={(profile) =>
                  loadDocuments(
                    async () => [
                      await loadCatalogDocument(
                        csrfToken,
                        profile.id,
                        profile.sha256,
                        'package',
                      ),
                    ],
                    { catalogProfile: profile },
                  )
                }
              />
            </Box>
          )}
          {!presetTitle && showKeenetic && (
            <Stack
              component="section"
              id={keeneticId}
              aria-label={t('import.keenetic.choose')}
              spacing={1}
            >
              <Typography variant="body2">
                {t('import.keenetic.hint')}
              </Typography>
              <Editor
                type="arg"
                value={keeneticText}
                onChange={editKeenetic}
                readonly={disabled || needSave}
                minHeight="9em"
                maxHeight="24em"
              />
              <Button
                variant="outlined"
                disabled={
                  !csrfToken || disabled || needSave || !keeneticText.trim()
                }
                onClick={() =>
                  loadDocuments(
                    async () => [
                      await convertKeeneticImport(csrfToken!, keeneticText),
                    ],
                    { keenetic: true },
                  )
                }
              >
                {t('import.keenetic.convert')}
              </Button>
            </Stack>
          )}
          {busy && (
            <Stack direction="row" spacing={1} alignItems="center">
              <CircularProgress size={18} />
              <Typography variant="body2">{t('import.working')}</Typography>
            </Stack>
          )}
          {presetTitle && (
            <Typography variant="subtitle1" sx={{ overflowWrap: 'anywhere' }}>
              {presetTitle}
            </Typography>
          )}
          {presetTitle && showDetails && (
            <Tabs
              id={tabsId}
              value={detailsTab}
              variant="scrollable"
              scrollButtons="auto"
              onChange={(_, tab: typeof detailsTab) => {
                setDetailsTab(tab);
                if (
                  tab === 'changes' &&
                  !plan &&
                  !disabled &&
                  !needSave &&
                  !saved
                )
                  review();
              }}
              aria-label={t('import.preset.details')}
            >
              {(['contents', 'changes', 'addons'] as const).map((tab) => (
                <Tab
                  key={tab}
                  value={tab}
                  label={t(
                    tab === 'addons'
                      ? 'import.addons.title'
                      : `import.preset.${tab}`,
                  )}
                  id={`${tabsId}-tab-${tab}`}
                  aria-controls={`${tabsId}-panel-${tab}`}
                />
              ))}
            </Tabs>
          )}
          {doc && detailed && (
            <Box {...panelProps('contents')}>
              <ImportSelectionView
                key={doc.input_sha256}
                document={doc}
                value={selection}
                csrfToken={csrfToken ?? ''}
                disabled={disabled || Boolean(presetTitle && saved)}
                onChange={edit}
                onError={fail}
              />
            </Box>
          )}
          {doc && detailed && csrfToken && (
            <Box {...panelProps('addons')}>
              <ImportAddons
                key={`${csrfToken}:${sourceGeneration}`}
                csrfToken={csrfToken}
                disabled={disabled || needSave || Boolean(presetTitle && saved)}
                value={selection.addons ?? []}
                onChange={editAddons}
              >
                {catalogChoice?.category === 'global' && (
                  <Stack spacing={0.5}>
                    <FormControlLabel
                      control={
                        <Checkbox
                          checked={Boolean(selection.torrent_sites)}
                          disabled={disabled || needSave || saved}
                          onChange={(_, checked) => {
                            const next = { ...selection };
                            if (checked)
                              next.torrent_sites = {
                                catalog_id: catalogChoice.id,
                                sha256: catalogChoice.sha256,
                              };
                            else delete next.torrent_sites;
                            edit(next);
                          }}
                        />
                      }
                      label={t('import.torrent_sites.label')}
                    />
                    <Typography variant="body2" color="text.secondary">
                      {t('import.torrent_sites.help')}
                    </Typography>
                  </Stack>
                )}
              </ImportAddons>
            </Box>
          )}
          {presetTitle &&
            plan &&
            (!showDetails || detailsTab !== 'changes') && (
              <ImportPreview plan={plan} compact luaTrust={luaTrust} />
            )}
          {detailed && (plan || presetTitle) && (
            <Box ref={previewRef} {...panelProps('changes')}>
              {!presetTitle && <Divider />}
              {!plan && !saved && (
                <Button
                  disabled={disabled || needSave}
                  onClick={() => review()}
                >
                  {t('import.preset.refresh_preview')}
                </Button>
              )}
              {plan &&
                !!(
                  plan.required.files.length || plan.required.shared.length
                ) && (
                  <Button
                    disabled={disabled}
                    onClick={() =>
                      doc &&
                      edit(
                        selectImportDependencies(selection, doc, plan.required),
                      )
                    }
                  >
                    {t('import.dependencies')}
                  </Button>
                )}
              {plan && <ImportPreview plan={plan} luaTrust={luaTrust} />}
            </Box>
          )}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ flexWrap: 'wrap', gap: 0.5 }}>
        {presetTitle ? (
          <Button
            aria-expanded={showDetails}
            aria-controls={showDetails ? tabsId : undefined}
            disabled={busy || servicePending}
            onClick={() => setShowDetails((value) => !value)}
            sx={{ mr: 'auto' }}
          >
            {t('import.preset.details')}
          </Button>
        ) : (
          <>
            <Button disabled={busy || servicePending} onClick={onClose}>
              {t('common.close')}
            </Button>
            <Button
              disabled={!doc || disabled || needSave || !csrfToken}
              onClick={() => review()}
            >
              {t('import.preview')}
            </Button>
            <InlineHelp title={t('import.preview')}>
              <Typography>{t('import.preview_help')}</Typography>
            </InlineHelp>
          </>
        )}
        <Button
          variant="contained"
          disabled={
            busy ||
            servicePending ||
            needSave ||
            saved ||
            (plan ? !plan.ready || !plan.proof : !presetTitle || uncertain) ||
            !csrfToken
          }
          onClick={apply}
        >
          {t(
            uncertain
              ? 'import.retry_apply'
              : presetTitle
                ? 'import.preset.apply'
                : 'import.apply',
          )}
        </Button>
        {presetTitle && (
          <InlineNfqwsRestart
            compact
            disabled={disabled || !saved || !restartReady}
            onPendingChange={setServicePending}
            onApplied={onServiceApplied}
          />
        )}
      </DialogActions>
    </Dialog>
  );
};

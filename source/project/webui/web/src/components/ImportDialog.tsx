import { useCallback, useEffect, useId, useRef, useState } from 'react';
import type { TranslationSchema } from '@/context/TranslationProvider';
import en from '@/translations/en.json';
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
  Stack,
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
import { ImportCatalog } from '@/components/ImportCatalog';
import { ImportLocalPack, readLocalPreset } from '@/components/ImportLocalPack';
import { ImportPreview } from '@/components/ImportPreview';
import { ImportSelectionView } from '@/components/ImportSelection';
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
  const [showCatalog, setShowCatalog] = useState(false);
  const [showLocalPack, setShowLocalPack] = useState(false);
  const [showKeenetic, setShowKeenetic] = useState(false);
  const [keeneticText, setKeeneticText] = useState('');
  const keeneticId = useId();
  const titleId = useId();
  const stepsId = useId();
  const previewRef = useRef<HTMLDivElement>(null);
  const showingPreview = Boolean(plan);
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
  const loadDocuments = useCallback(
    (
      read: () => Promise<string[]>,
      files: File[] = [],
      autoPreview = false,
      catalogProfile?: CatalogProfile,
    ) => {
      if (pending.current || !csrfToken) return;
      source.current = autoPreview ? 'keenetic' : 'other';
      chosenFiles.current = files;
      setSourceGeneration((value) => value + 1);
      revision.current++;
      setDoc(undefined);
      setCatalogChoice(undefined);
      setDocuments([]);
      setPlan(undefined);
      // The explicit before/after preview and Save action approve the selected scope.
      // Arbitrary Lua remains untrusted; packaged helpers are verified by the server.
      setSelection({
        ...emptyImportSelection(),
        allow_shared_impact: true,
        allow_incomplete: true,
      });
      requestId.current = '';
      setSaved(false);
      setUncertain(false);
      const rev = revision.current;
      void run(async () => {
        const raw = await read();
        const parsed = await inspectImport(csrfToken!, raw);
        const selected = selectAllImport(parsed, {
          ...emptyImportSelection(),
          allow_shared_impact: true,
          allow_incomplete: true,
        });
        if (mounted.current && rev === revision.current) {
          setDocuments(raw);
          setDoc(parsed);
          setCatalogChoice(catalogProfile);
          setSelection(selected);
        }
        if (autoPreview && mounted.current && rev === revision.current) {
          const prepared = await prepareImport(csrfToken!, raw, selected);
          if (mounted.current && rev === revision.current) {
            setPlan(prepared);
            requestId.current = newImportRequestId();
          }
        }
      });
    },
    [csrfToken, run],
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
      setSourceGeneration((value) => value + 1);
      revision.current++;
      source.current = null;
      setDocuments([]);
      setDoc(undefined);
      setCatalogChoice(undefined);
      setPlan(undefined);
      setSelection(emptyImportSelection());
      requestId.current = '';
      setSaved(false);
    }
  };
  const load = (files: File[]) =>
    loadDocuments(() => readImportFiles(files), files);
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
        setPlan(undefined);
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
      if (needSave || !plan?.ready || !plan.proof || !requestId.current) return;
      let result: ImportStatus;
      try {
        result = await applyImport(
          csrfToken!,
          documents,
          selection,
          plan.proof,
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
      setPlan(undefined);
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
        <FileDownloadOutlinedIcon color="primary" />
        {t('import.title')}
      </DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2} sx={{ minWidth: 0 }}>
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
          {needSave && <Alert severity="info">{t('import.save_first')}</Alert>}
          {!!error && (
            <Alert severity="info">
              {t(`import.errors.${error}`) || t('import.error')}
            </Alert>
          )}
          {uncertain && (
            <Alert severity="info">
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
          {importRestartPending &&
            !uncertain &&
            !pendingUndo.current &&
            status &&
            ['committed', 'undone'].includes(status.state) && (
              <Stack spacing={1}>
                {!saved && (
                  <Alert severity="info">{t('import.restart_pending')}</Alert>
                )}
                <InlineNfqwsRestart
                  disabled={busy}
                  onPendingChange={setServicePending}
                  onApplied={() => {
                    setImportRestartPending(false);
                    setServiceApplied(true);
                  }}
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
              variant={showCatalog ? 'contained' : 'outlined'}
              disabled={!csrfToken || disabled || needSave}
              onClick={() => {
                setShowCatalog((value) => !value);
                setShowLocalPack(false);
              }}
            >
              {t('import.catalog.choose')}
            </Button>
            <Button
              variant={showLocalPack ? 'contained' : 'outlined'}
              disabled={disabled || needSave || !csrfToken}
              aria-expanded={showLocalPack}
              onClick={() => {
                setShowLocalPack((value) => !value);
                setShowCatalog(false);
                setShowKeenetic(false);
              }}
            >
              {t('import.local.choose')}
            </Button>
            <Button
              variant={showKeenetic ? 'contained' : 'outlined'}
              disabled={!csrfToken || disabled || needSave}
              aria-expanded={showKeenetic}
              aria-controls={keeneticId}
              onClick={() => {
                setShowKeenetic((value) => !value);
                setShowLocalPack(false);
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
          {showLocalPack && csrfToken && (
            <ImportLocalPack
              csrf={csrfToken}
              disabled={disabled || needSave}
              onSelect={(id) =>
                loadDocuments(() => readLocalPreset(csrfToken, id))
              }
            />
          )}
          {showKeenetic && (
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
                    [],
                    true,
                  )
                }
              >
                {t('import.keenetic.convert')}
              </Button>
            </Stack>
          )}
          {showCatalog && csrfToken && (
            <ImportCatalog
              key={csrfToken}
              csrfToken={csrfToken}
              disabled={disabled || needSave}
              onSelect={(profile) =>
                loadDocuments(
                  async () => [
                    await loadCatalogDocument(
                      csrfToken,
                      profile.id,
                      profile.sha256,
                    ),
                  ],
                  [],
                  false,
                  profile,
                )
              }
            />
          )}
          {busy && (
            <Stack direction="row" spacing={1} alignItems="center">
              <CircularProgress size={18} />
              <Typography variant="body2">{t('import.working')}</Typography>
            </Stack>
          )}
          {doc && (
            <ImportSelectionView
              key={doc.input_sha256}
              document={doc}
              value={selection}
              csrfToken={csrfToken ?? ''}
              disabled={disabled}
              onChange={edit}
              onError={fail}
            />
          )}
          {doc && csrfToken && (
            <ImportAddons
              key={`${csrfToken}:${sourceGeneration}`}
              csrfToken={csrfToken}
              disabled={disabled || needSave}
              value={selection.addons ?? []}
              onChange={editAddons}
            >
              {catalogChoice?.category === 'global' && (
                <Stack spacing={0.5}>
                  <FormControlLabel
                    control={
                      <Checkbox
                        checked={Boolean(selection.torrent_sites)}
                        disabled={disabled || needSave}
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
          )}
          {plan && (
            <Box ref={previewRef}>
              <Divider />
              {!!(
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
              <ImportPreview
                plan={plan}
                luaTrust={{
                  checked: selection.trusted_lua,
                  disabled: disabled || needSave,
                  onChange: review,
                }}
              />
            </Box>
          )}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ flexWrap: 'wrap', gap: 0.5 }}>
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
        <Button
          variant="contained"
          disabled={
            busy ||
            servicePending ||
            needSave ||
            !plan?.ready ||
            !plan.proof ||
            !csrfToken
          }
          onClick={apply}
        >
          {t(uncertain ? 'import.retry_apply' : 'import.apply')}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

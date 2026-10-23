import { useCallback, useEffect, useRef, useState } from 'react';
import type { TranslationSchema } from '@/context/TranslationProvider';
import en from '@/translations/en.json';
import {
  Alert,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Stack,
  Typography,
} from '@mui/material';

import { selectAllImport } from '@/api/bulkSelection';
import { API } from '@/api/client';
import {
  applyImport,
  emptyImportSelection,
  importOutcomeUnknown,
  importStatus,
  inspectImport,
  newImportRequestId,
  prepareImport,
  readImportFiles,
  selectImportDependencies,
  undoImport,
  type ImportDocument,
  type ImportPlan,
  type ImportSelection,
  type ImportStatus,
} from '@/api/importClient';
import { loadCatalogDocument } from '@/api/profileCatalogClient';
import { ShareError } from '@/api/shareClient';

import { ImportCatalog } from '@/components/ImportCatalog';
import { ImportPreview } from '@/components/ImportPreview';
import { ImportSelectionView } from '@/components/ImportSelection';
import { InlineHelp } from '@/components/InlineHelp';

import { useAppStore } from '@/store/useAppStore';

import { useStatus } from '@/hooks/useStatus';
import { useTranslation } from '@/hooks/useTranslation';

export const ImportDialog = ({ onClose }: { onClose: VoidFunction }) => {
  const { t } = useTranslation();
  const { csrfToken } = useStatus();
  const { needSave } = useAppStore();
  const [documents, setDocuments] = useState<string[]>([]);
  const [doc, setDoc] = useState<ImportDocument>();
  const [selection, setSelection] =
    useState<ImportSelection>(emptyImportSelection);
  const [plan, setPlan] = useState<ImportPlan>();
  const [status, setStatus] = useState<ImportStatus>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<
    keyof TranslationSchema['import']['errors'] | ''
  >('');
  const [saved, setSaved] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [showCatalog, setShowCatalog] = useState(false);
  const mounted = useRef(false);
  const pending = useRef(false);
  const requestId = useRef('');
  const chosenFiles = useRef<File[]>([]);
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
  const reload = async () => {
    await Promise.all([
      API.invalidateFileContent('nfqws2.conf'),
      API.invalidateListFiles(),
    ]);
  };
  const edit = (value: ImportSelection) => {
    revision.current++;
    setSelection(value);
    setPlan(undefined);
    requestId.current = '';
    setSaved(false);
    setError('');
  };
  const run = async (fn: () => Promise<void>) => {
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
  };
  const loadDocuments = (read: () => Promise<string[]>, files: File[] = []) => {
    if (pending.current) return;
    chosenFiles.current = files;
    revision.current++;
    setDoc(undefined);
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
    void run(async () => {
      const raw = await read();
      const parsed = await inspectImport(csrfToken!, raw);
      if (mounted.current) {
        setDocuments(raw);
        setDoc(parsed);
        setSelection(
          selectAllImport(parsed, {
            ...emptyImportSelection(),
            allow_shared_impact: true,
            allow_incomplete: true,
          }),
        );
      }
    });
  };
  const load = (files: File[]) =>
    loadDocuments(() => readImportFiles(files), files);
  const review = () =>
    void run(async () => {
      setPlan(undefined);
      const rev = revision.current;
      const p = await prepareImport(csrfToken!, documents, selection);
      if (mounted.current && rev === revision.current) {
        setPlan(p);
        requestId.current = newImportRequestId();
      }
    });
  const refresh = () =>
    void run(async () => {
      const s = await importStatus(csrfToken!);
      if (!mounted.current) return;
      setStatus(s);
      if (s.id === requestId.current && s.state === 'committed') {
        setSaved(true);
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
      setPlan(undefined);
      await reload();
      const fresh = await importStatus(csrfToken!);
      if (mounted.current) setStatus(fresh);
    });
  const undo = () =>
    void run(async () => {
      if (needSave || !status?.id || !status.undo_proof) return;
      const s = await undoImport(csrfToken!, status.id, status.undo_proof);
      if (mounted.current) {
        setStatus(s);
        setSaved(false);
        setPlan(undefined);
        setUncertain(false);
      }
      await reload();
    });
  const disabled = busy || uncertain;
  return (
    <Dialog
      open
      fullWidth
      maxWidth="md"
      scroll="paper"
      onClose={() => {
        if (!busy) onClose();
      }}
    >
      <DialogTitle>{t('import.title')}</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2} sx={{ minWidth: 0 }}>
          <Typography variant="body2">{t('import.hint')}</Typography>
          {needSave && <Alert severity="info">{t('import.save_first')}</Alert>}
          {!!error && (
            <Alert severity="info">
              {t(`import.errors.${error}`) || t('import.error')}
            </Alert>
          )}
          {uncertain && <Alert severity="info">{t('import.uncertain')}</Alert>}
          {saved && <Alert severity="success">{t('import.saved')}</Alert>}
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
              variant="outlined"
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
              onClick={() => setShowCatalog((value) => !value)}
            >
              {t('import.catalog.choose')}
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
          {showCatalog && csrfToken && (
            <ImportCatalog
              key={csrfToken}
              csrfToken={csrfToken}
              disabled={disabled || needSave}
              onSelect={(profile) =>
                loadDocuments(async () => [
                  await loadCatalogDocument(
                    csrfToken,
                    profile.id,
                    profile.sha256,
                  ),
                ])
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
          {plan && (
            <>
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
              <ImportPreview plan={plan} />
            </>
          )}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ flexWrap: 'wrap', gap: 0.5 }}>
        <Button disabled={busy} onClick={onClose}>
          {t('common.close')}
        </Button>
        <Button
          disabled={!doc || disabled || needSave || !csrfToken}
          onClick={review}
        >
          {t('import.preview')}
        </Button>
        <InlineHelp title={t('import.preview')}>
          <Typography>{t('import.preview_help')}</Typography>
        </InlineHelp>
        <Button
          variant="contained"
          disabled={
            busy || needSave || !plan?.ready || !plan.proof || !csrfToken
          }
          onClick={apply}
        >
          {t(uncertain ? 'import.retry_apply' : 'import.apply')}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

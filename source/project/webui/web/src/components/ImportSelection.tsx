import { useState } from 'react';
import type { TranslationKey } from '@/context/TranslationProvider';
import en from '@/translations/en.json';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Button,
  Checkbox,
  FormControlLabel,
  Stack,
  TextField,
  Typography,
} from '@mui/material';

import { selectAllImport, selectImportFiles } from '@/api/bulkSelection';
import {
  PORT_IMPORT_KEYS,
  SHARED_IMPORT_KEYS,
  type ImportDocument,
  type ImportSelection,
} from '@/api/importClient';
import {
  displayImportValue,
  encodeImportValue,
  unresolvedImportAliases,
} from '@/api/importPaths';
import { STRATEGY_KEYS } from '@/api/shareClient';
import { resourceBytes } from '@/api/shareResourcesClient';

import { FormEditor } from '@/components/FormEditor';
import { ShareDnsSection } from '@/components/ShareDnsSection';

import { useTranslation } from '@/hooks/useTranslation';

export const ImportSelectionView = ({
  document,
  value,
  disabled,
  csrfToken,
  onChange,
  onError,
}: {
  document: ImportDocument;
  value: ImportSelection;
  disabled: boolean;
  csrfToken: string;
  onChange: (value: ImportSelection) => void;
  onError: (e: unknown) => void;
}) => {
  const { t } = useTranslation();
  const [showStrategies, setShowStrategies] = useState(false);
  const [showFiles, setShowFiles] = useState(false);
  const label = (key: string) =>
    Object.prototype.hasOwnProperty.call(en.form, key)
      ? t(`form.${key}` as TranslationKey)
      : key;
  const group = (
    kind: 'blocks' | 'shared' | 'ports',
    keys: readonly string[],
    source: Record<string, string>,
  ) => (
    <Stack spacing={1}>
      <Typography variant="subtitle1">{t(`import.${kind}`)}</Typography>
      {keys
        .filter((key) => typeof source[key] === 'string')
        .map((key) => {
          const pick = value[kind].find((v) => v.key === key);
          return (
            <Stack key={key} spacing={1}>
              <FormControlLabel
                control={
                  <Checkbox
                    checked={!!pick}
                    disabled={disabled}
                    onChange={(_, checked) =>
                      onChange({
                        ...value,
                        [kind]: checked
                          ? [...value[kind], { key, value: source[key] }]
                          : value[kind].filter((v) => v.key !== key),
                      })
                    }
                  />
                }
                label={label(key)}
              />
              {pick &&
                (kind !== 'blocks' || showStrategies) &&
                (kind === 'ports' ? (
                  <TextField
                    fullWidth
                    size="small"
                    label={label(key)}
                    value={pick.value}
                    disabled={disabled}
                    onChange={(e) =>
                      onChange({
                        ...value,
                        [kind]: value[kind].map((v) =>
                          v.key === key ? { ...v, value: e.target.value } : v,
                        ),
                      })
                    }
                  />
                ) : (
                  <FormEditor
                    label={label(key)}
                    value={displayImportValue(pick.value, document.resources)}
                    description={
                      unresolvedImportAliases(pick.value, document.resources)
                        .length
                        ? t('import.paths_missing')
                        : undefined
                    }
                    readonly={disabled}
                    onChange={(text) =>
                      onChange({
                        ...value,
                        [kind]: value[kind].map((v) =>
                          v.key === key
                            ? {
                                ...v,
                                value: encodeImportValue(
                                  text,
                                  document.resources,
                                ),
                              }
                            : v,
                        ),
                      })
                    }
                  />
                ))}
            </Stack>
          );
        })}
    </Stack>
  );
  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
        <Button
          disabled={disabled}
          onClick={() => onChange(selectAllImport(document, value))}
        >
          {t('share.select_all')}
        </Button>
        <Button
          disabled={disabled}
          onClick={() =>
            onChange({
              ...value,
              blocks: [],
              shared: [],
              ports: [],
              files: [],
              dns: [],
            })
          }
        >
          {t('share.clear_selection')}
        </Button>
      </Stack>
      {!!document.ignored.length && (
        <Alert severity="info">
          {t('import.ignored')}: {document.ignored.join(', ')}
        </Alert>
      )}
      {document.context && (
        <Stack spacing={0.5}>
          {(['purpose', 'operator', 'region'] as const).map((key) =>
            typeof document.context?.[key] === 'string' &&
            document.context[key] ? (
              <Typography
                variant="body2"
                key={key}
                sx={{ overflowWrap: 'anywhere' }}
              >
                <strong>{t(`import.context.${key}`)}:</strong>{' '}
                {String(document.context[key])}
              </Typography>
            ) : null,
          )}
        </Stack>
      )}
      {(document.context || document.source) && (
        <Accordion>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            {t('import.source')}
          </AccordionSummary>
          <AccordionDetails>
            <Typography
              component="pre"
              sx={{
                whiteSpace: 'pre-wrap',
                overflowWrap: 'anywhere',
                fontSize: 12,
              }}
            >
              {JSON.stringify(
                { context: document.context, source: document.source },
                null,
                2,
              )}
            </Typography>
          </AccordionDetails>
        </Accordion>
      )}
      {STRATEGY_KEYS.some((k) => k in document.values) && (
        <>
          <Button
            size="small"
            aria-expanded={showStrategies}
            onClick={() => setShowStrategies((v) => !v)}
          >
            {t(
              showStrategies
                ? 'import.hide_strategies'
                : 'import.show_strategies',
            )}
          </Button>
          {group('blocks', STRATEGY_KEYS, document.values)}
        </>
      )}
      {SHARED_IMPORT_KEYS.some((k) => k in document.values) && (
        <Accordion>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            {t('import.shared')} · {value.shared.length}
          </AccordionSummary>
          <AccordionDetails>
            {group('shared', SHARED_IMPORT_KEYS, document.values)}
          </AccordionDetails>
        </Accordion>
      )}
      {PORT_IMPORT_KEYS.some((k) => k in document.ports) && (
        <Accordion>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            {t('import.ports')} · {value.ports.length}
          </AccordionSummary>
          <AccordionDetails>
            {group('ports', PORT_IMPORT_KEYS, document.ports)}
          </AccordionDetails>
        </Accordion>
      )}
      {document.resources.some((f) => f.kind !== 'lua') && (
        <Stack spacing={1}>
          <Typography variant="subtitle1">{t('import.files')}</Typography>
          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
            <Button
              disabled={disabled}
              onClick={() =>
                onChange(selectImportFiles(document, value, 'blobs', true))
              }
            >
              {t('share.select_blobs')}
            </Button>
            <Button
              disabled={disabled}
              onClick={() =>
                onChange(selectImportFiles(document, value, 'blobs', false))
              }
            >
              {t('share.clear_blobs')}
            </Button>
          </Stack>
          <Accordion>
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              {t('import.files')} · {value.files.length}/
              {document.resources.filter((f) => f.kind !== 'lua').length}
            </AccordionSummary>
            <AccordionDetails>
              <Stack spacing={1}>
                <Button
                  size="small"
                  aria-expanded={showFiles}
                  onClick={() => setShowFiles((v) => !v)}
                >
                  {t(showFiles ? 'import.hide_files' : 'import.show_files')}
                </Button>
                {document.resources
                  .filter((f) => f.kind !== 'lua')
                  .map((file) => {
                    const pick = value.files.find((v) => v.id === file.id);
                    return (
                      <Stack key={file.id} spacing={1}>
                        <FormControlLabel
                          control={
                            <Checkbox
                              checked={!!pick}
                              disabled={disabled}
                              onChange={(_, checked) =>
                                onChange({
                                  ...value,
                                  files: checked
                                    ? [...value.files, { id: file.id }]
                                    : value.files.filter(
                                        (f) => f.id !== file.id,
                                      ),
                                })
                              }
                            />
                          }
                          label={
                            <Typography sx={{ overflowWrap: 'anywhere' }}>
                              {file.kind}/{file.name} · {file.byte_length} B
                            </Typography>
                          }
                        />
                        {pick && showFiles && file.encoding === 'utf8' && (
                          <TextField
                            multiline
                            fullWidth
                            minRows={3}
                            maxRows={12}
                            label={file.name}
                            disabled={disabled}
                            value={
                              pick.text ??
                              new TextDecoder('utf-8', { fatal: true }).decode(
                                resourceBytes(file),
                              )
                            }
                            onChange={(e) =>
                              onChange({
                                ...value,
                                files: value.files.map((f) =>
                                  f.id === file.id
                                    ? { ...f, text: e.target.value }
                                    : f,
                                ),
                              })
                            }
                            slotProps={{
                              input: {
                                sx: { fontFamily: 'monospace', fontSize: 13 },
                              },
                            }}
                          />
                        )}
                        {pick && showFiles && file.encoding === 'base64' && (
                          <Typography variant="caption">
                            {t('import.binary')} · SHA256 {file.sha256}
                          </Typography>
                        )}
                      </Stack>
                    );
                  })}
              </Stack>
            </AccordionDetails>
          </Accordion>
        </Stack>
      )}
      {!!document.dns_sources.length && (
        <ShareDnsSection
          csrfToken={csrfToken}
          providedSources={document.dns_sources}
          value={value.dns}
          disabled={disabled}
          onChange={(dns) => onChange({ ...value, dns })}
          onError={onError}
        />
      )}
    </Stack>
  );
};

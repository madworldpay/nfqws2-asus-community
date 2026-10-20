import { useEffect, useRef, useState } from 'react';
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

import { readBulkResources } from '@/api/bulkSelection';
import {
  downloadContribution,
  getShareInventory,
  readShareResource,
  resourceBytes,
  resourceZip,
  type ResourceCopy,
  type ResourceInventory,
  type ResourceMeta,
} from '@/api/shareResourcesClient';

import { InlineHelp } from '@/components/InlineHelp';

import { useTranslation } from '@/hooks/useTranslation';

export type ShareFilesForm = {
  inventory?: ResourceInventory;
  selected: string[];
  copies: Record<string, ResourceCopy>;
};
export const ShareFilesSection = ({
  csrfToken,
  value,
  disabled,
  onChange,
  onError,
}: {
  csrfToken: string;
  value: ShareFilesForm;
  disabled: boolean;
  onChange: (update: (old: ShareFilesForm) => ShareFilesForm) => void;
  onError: (e: unknown) => void;
}) => {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const alive = useRef(false);
  useEffect(() => {
    alive.current = true;
    let active = true;
    void getShareInventory(csrfToken).then(
      (inventory) => {
        if (active) onChange((old) => ({ ...old, inventory }));
      },
      (e) => {
        if (active) onError(e);
      },
    );
    return () => {
      active = false;
      alive.current = false;
    };
  }, [csrfToken, onChange, onError]);
  const select = async (meta: ResourceMeta, checked: boolean) => {
    if (!checked) {
      onChange((old) => ({
        ...old,
        selected: old.selected.filter((id) => id !== meta.id),
      }));
      return;
    }
    if (loading || disabled) return;
    onChange((old) => {
      const copies = { ...old.copies };
      delete copies[meta.id];
      return {
        ...old,
        selected: [...new Set([...old.selected, meta.id])],
        copies,
      };
    });
    setLoading(true);
    try {
      const copy = await readShareResource(csrfToken, meta);
      if (alive.current)
        onChange((old) => ({
          ...old,
          selected: [...new Set([...old.selected, meta.id])],
          copies: { ...old.copies, [meta.id]: copy },
        }));
    } catch (e) {
      if (alive.current) {
        onChange((old) => ({
          ...old,
          selected: old.selected.filter((id) => id !== meta.id),
        }));
        onError(e);
      }
    } finally {
      if (alive.current) setLoading(false);
    }
  };
  const selectGroup = async (kind: 'lists' | 'blobs', checked: boolean) => {
    if (loading || disabled) return;
    const metas = value.inventory?.files ?? [];
    const ids = metas
      .filter((m) => m.kind === kind && m.state === 'available')
      .map((m) => m.id);
    if (!checked) {
      onChange((old) => ({
        ...old,
        selected: old.selected.filter((id) => !ids.includes(id)),
      }));
      return;
    }
    const previous = value.selected;
    onChange((old) => ({
      ...old,
      selected: [...new Set([...old.selected, ...ids])],
    }));
    setLoading(true);
    try {
      const result = await readBulkResources(
        metas,
        value.copies,
        (meta) => readShareResource(csrfToken, meta),
        kind,
      );
      if (alive.current)
        onChange((old) => ({
          ...old,
          selected: [...new Set([...old.selected, ...result.selected])],
          copies: { ...old.copies, ...result.copies },
        }));
    } catch (e) {
      if (alive.current) {
        onChange((old) => ({ ...old, selected: previous }));
        onError(e);
      }
    } finally {
      if (alive.current) setLoading(false);
    }
  };
  const refresh = async () => {
    if (loading || disabled) return;
    setLoading(true);
    onChange(() => ({ selected: [], copies: {} }));
    try {
      const inventory = await getShareInventory(csrfToken);
      if (alive.current) onChange((old) => ({ ...old, inventory }));
    } catch (e) {
      if (alive.current) onError(e);
    } finally {
      if (alive.current) setLoading(false);
    }
  };
  return (
    <Stack spacing={1.5}>
      <Typography>{t('share.resources_title')}</Typography>
      <Stack direction="row" alignItems="center">
        <Typography variant="body2">{t('share.resources_hint')}</Typography>
        <InlineHelp title={t('share.resources_title')}>
          <Typography>{t('share.resources_help')}</Typography>
        </InlineHelp>
      </Stack>
      <Stack direction="row" useFlexGap flexWrap="wrap" spacing={1}>
        <Button disabled={disabled || loading} onClick={() => void refresh()}>
          {t('share.refresh_files')}
        </Button>
        <Button
          disabled={disabled || loading || !value.selected.length}
          onClick={() => {
            try {
              downloadContribution(
                resourceZip(value.selected.map((id) => value.copies[id])),
                'NFQWS2_SELECTED_FILES.zip',
              );
            } catch (e) {
              onError(e);
            }
          }}
        >
          {t('share.download_zip')}
        </Button>
      </Stack>
      {loading && (
        <Typography variant="caption">{t('share.loading')}</Typography>
      )}
      {value.inventory &&
        (value.inventory.scan_truncated || value.inventory.skipped > 0) && (
          <Alert severity="info">{t('share.inventory_partial')}</Alert>
        )}
      {(['lists', 'blobs'] as const).map((kind) => (
        <Accordion key={kind}>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            {t(`share.resource_kinds.${kind}`)} ·{' '}
            {value.inventory?.files.filter((f) => f.kind === kind).length ?? 0}
          </AccordionSummary>
          <AccordionDetails>
            <Stack spacing={1.5}>
              <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                <Button
                  disabled={disabled || loading}
                  onClick={() => void selectGroup(kind, true)}
                >
                  {t(
                    kind === 'blobs'
                      ? 'share.select_blobs'
                      : 'share.select_all',
                  )}
                </Button>
                <Button
                  disabled={disabled || loading}
                  onClick={() => void selectGroup(kind, false)}
                >
                  {t(
                    kind === 'blobs'
                      ? 'share.clear_blobs'
                      : 'share.clear_selection',
                  )}
                </Button>
              </Stack>
              {value.inventory?.files
                .filter((f) => f.kind === kind)
                .map((meta) => {
                  const copy = value.copies[meta.id];
                  const chosen = value.selected.includes(meta.id);
                  return (
                    <Stack key={meta.id} spacing={1}>
                      <FormControlLabel
                        control={
                          <Checkbox
                            checked={chosen}
                            disabled={
                              disabled || loading || meta.state !== 'available'
                            }
                            onChange={(_, checked) =>
                              void select(meta, checked)
                            }
                          />
                        }
                        label={
                          <Typography sx={{ overflowWrap: 'anywhere' }}>
                            {meta.name} · {meta.byte_length} B
                          </Typography>
                        }
                      />
                      {meta.state !== 'available' && (
                        <Typography variant="caption">
                          {t('share.file_unavailable')}
                        </Typography>
                      )}
                      {chosen && copy && (
                        <>
                          <Typography
                            variant="caption"
                            sx={{ overflowWrap: 'anywhere' }}
                          >
                            {t('share.source_hash')}: {copy.sha256}
                          </Typography>
                          {copy.encoding === 'utf8' ? (
                            <TextField
                              label={t('share.file_copy')}
                              multiline
                              minRows={3}
                              maxRows={9}
                              disabled={disabled || loading}
                              value={copy.text ?? ''}
                              onChange={(e) =>
                                onChange((old) => ({
                                  ...old,
                                  copies: {
                                    ...old.copies,
                                    [meta.id]: {
                                      ...copy,
                                      text: e.target.value,
                                    },
                                  },
                                }))
                              }
                            />
                          ) : (
                            <Typography variant="body2">
                              {t('share.blob_exact')}
                            </Typography>
                          )}
                          <Button
                            disabled={disabled || loading}
                            onClick={() => {
                              try {
                                downloadContribution(
                                  new Blob([resourceBytes(copy)], {
                                    type:
                                      copy.encoding === 'utf8'
                                        ? 'text/plain;charset=utf-8'
                                        : 'application/octet-stream',
                                  }),
                                  copy.name,
                                );
                              } catch (e) {
                                onError(e);
                              }
                            }}
                          >
                            {t('share.download_copy')}
                          </Button>
                        </>
                      )}
                    </Stack>
                  );
                })}
            </Stack>
          </AccordionDetails>
        </Accordion>
      ))}
    </Stack>
  );
};

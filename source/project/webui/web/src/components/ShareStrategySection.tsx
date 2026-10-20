import { useEffect, useRef, useState } from 'react';
import {
  Alert,
  Button,
  Checkbox,
  FormControlLabel,
  Stack,
  Typography,
} from '@mui/material';

import {
  getStrategyDraft,
  type ShareLocation,
  type StrategyContext,
  type StrategyDraft,
  type StrategyKey,
} from '@/api/shareClient';

import { FormEditor } from '@/components/FormEditor';
import { ShareContextSection } from '@/components/ShareContextSection';

import { useTranslation } from '@/hooks/useTranslation';

export type ShareStrategyForm = {
  draft?: StrategyDraft;
  selected: StrategyKey[];
  full: boolean;
  context: StrategyContext;
  locationEdited: boolean;
};
export const ShareStrategySection = ({
  csrfToken,
  value,
  disabled,
  onChange,
  onLocation,
  onError,
  blocksOnly = false,
}: {
  blocksOnly?: boolean;
  csrfToken: string;
  value: ShareStrategyForm;
  disabled: boolean;
  onChange: (update: (old: ShareStrategyForm) => ShareStrategyForm) => void;
  onLocation: (v: ShareLocation) => void;
  onError: (e: unknown) => void;
}) => {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const generation = useRef({ value: 0 });
  useEffect(() => {
    if (value.draft) return;
    let active = true;
    const seq = ++generation.current.value;
    void getStrategyDraft(csrfToken).then(
      (draft) => {
        if (active && seq === generation.current.value)
          onChange((old) => ({
            ...old,
            draft,
            selected: old.selected.filter((k) =>
              draft.blocks.some((b) => b.key === k),
            ),
          }));
      },
      (e) => {
        if (active) onError(e);
      },
    );
    const generationState = generation.current;
    return () => {
      active = false;
      generationState.value++;
    };
  }, [csrfToken, onChange, onError, onLocation, value.draft]);
  const refresh = async () => {
    if (loading || disabled) return;
    setLoading(true);
    const seq = ++generation.current.value;
    onChange((old) => ({ ...old }));
    try {
      const draft = await getStrategyDraft(csrfToken);
      if (seq !== generation.current.value) return;
      onChange((old) => ({
        ...old,
        draft,
        selected: old.selected.filter((k) =>
          draft.blocks.some((b) => b.key === k),
        ),
      }));
    } catch (e) {
      if (seq === generation.current.value) onError(e);
    } finally {
      if (seq === generation.current.value) setLoading(false);
    }
  };
  return (
    <Stack spacing={1.5}>
      <Typography variant="body2">{t('share.strategy_hint')}</Typography>
      {!blocksOnly && (
        <ShareContextSection
          csrfToken={csrfToken}
          value={value}
          disabled={disabled}
          onChange={onChange}
          onLocation={onLocation}
        />
      )}
      <FormControlLabel
        control={
          <Checkbox
            checked={value.full}
            disabled={disabled}
            onChange={(_, full) => onChange((old) => ({ ...old, full }))}
          />
        }
        label={t('share.full_config')}
      />
      {value.full ? (
        <FormEditor
          type="conf"
          readonly={disabled}
          label={t('share.config_copy')}
          value={value.draft?.config ?? ''}
          onChange={(text) =>
            onChange((old) => ({
              ...old,
              draft: {
                blocks: old.draft?.blocks ?? [],
                config: text,
              },
            }))
          }
        />
      ) : (
        value.draft?.blocks.map((block) => (
          <Stack key={block.key} spacing={1}>
            <FormControlLabel
              control={
                <Checkbox
                  checked={value.selected.includes(block.key)}
                  disabled={disabled}
                  onChange={(_, checked) =>
                    onChange((old) => ({
                      ...old,
                      selected: checked
                        ? [...old.selected, block.key]
                        : old.selected.filter((k) => k !== block.key),
                    }))
                  }
                />
              }
              label={`${block.key} · ${t(`share.blocks.${block.key}`)}`}
            />
            {value.selected.includes(block.key) && (
              <FormEditor
                readonly={disabled}
                label={block.key}
                value={block.value}
                onChange={(text) =>
                  onChange((old) => ({
                    ...old,
                    draft: old.draft
                      ? {
                          ...old.draft,
                          blocks: old.draft.blocks.map((b) =>
                            b.key === block.key ? { ...b, value: text } : b,
                          ),
                        }
                      : undefined,
                  }))
                }
              />
            )}
          </Stack>
        ))
      )}
      {!value.draft && (
        <Typography variant="body2">{t('share.reading_config')}</Typography>
      )}
      {value.draft && !value.full && !value.draft.blocks.length && (
        <Alert severity="info">{t('share.no_blocks')}</Alert>
      )}
      <Button onClick={() => void refresh()} disabled={disabled || loading}>
        {t('share.refresh_config')}
      </Button>
    </Stack>
  );
};

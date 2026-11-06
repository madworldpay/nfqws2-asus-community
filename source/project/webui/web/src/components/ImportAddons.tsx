import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import {
  Alert,
  Button,
  Checkbox,
  CircularProgress,
  FormControlLabel,
  Stack,
  Typography,
} from '@mui/material';

import {
  loadImportAddonCatalog,
  type ImportAddonCatalog,
  type ImportAddonSelection,
} from '@/api/importAddonClient';

import { useTranslation } from '@/hooks/useTranslation';

const selectedSources = (
  catalog: ImportAddonCatalog,
  selected: ImportAddonSelection[],
) =>
  JSON.stringify([
    catalog.revision,
    selected.map((entry) =>
      catalog.addons.find((addon) => addon.id === entry.id),
    ),
  ]);

export const ImportAddons = ({
  csrfToken,
  disabled,
  value,
  onChange,
  children,
}: {
  csrfToken: string;
  disabled: boolean;
  value: ImportAddonSelection[];
  onChange: (value: ImportAddonSelection[]) => void;
  children?: ReactNode;
}) => {
  const { t, langcode } = useTranslation();
  const [catalog, setCatalog] = useState<ImportAddonCatalog>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const [changed, setChanged] = useState<'selection' | 'preview'>();
  const previousCatalog = useRef<ImportAddonCatalog | undefined>(undefined);
  const generation = useRef(0);
  const pending = useRef(false);
  const refresh = useCallback(
    async (selected: ImportAddonSelection[]) => {
      if (pending.current) return;
      const epoch = generation.current;
      pending.current = true;
      setBusy(true);
      setError(false);
      try {
        const result = await loadImportAddonCatalog(csrfToken);
        if (generation.current !== epoch) return;
        const sourceChanged =
          selected.length > 0 &&
          previousCatalog.current !== undefined &&
          selectedSources(previousCatalog.current, selected) !==
            selectedSources(result, selected);
        previousCatalog.current = result;
        setCatalog(result);
        const retained = selected.filter((entry) =>
          result.addons.some(
            (addon) =>
              addon.id === entry.id &&
              addon.sha256 === entry.sha256 &&
              addon.min_build <= result.build,
          ),
        );
        if (retained.length !== selected.length) {
          setChanged('selection');
          onChange(retained);
        } else if (sourceChanged) {
          setChanged('preview');
          onChange(retained);
        }
      } catch {
        // A failed refresh must leave an explicit prior choice intact.
        if (generation.current === epoch) setError(true);
      } finally {
        if (generation.current === epoch) {
          pending.current = false;
          setBusy(false);
        }
      }
    },
    [csrfToken, onChange],
  );
  useEffect(() => {
    generation.current += 1;
    pending.current = false;
    previousCatalog.current = undefined;
    void refresh([]);
    return () => {
      generation.current += 1;
      pending.current = false;
    };
  }, [refresh]);
  return (
    <Stack
      component="section"
      role="region"
      aria-label={t('import.addons.title')}
      spacing={1}
    >
      <Stack
        direction="row"
        alignItems="center"
        spacing={1}
        useFlexGap
        flexWrap="wrap"
      >
        <Typography variant="subtitle1">{t('import.addons.title')}</Typography>
        <Button
          size="small"
          disabled={disabled || busy}
          onClick={() => void refresh(value)}
        >
          {t('import.addons.refresh')}
        </Button>
        {busy && <CircularProgress size={18} />}
      </Stack>
      <Typography variant="body2">{t('import.addons.hint')}</Typography>
      <Typography variant="body2" color="text.secondary">
        {t('import.addons.scope_help')}
      </Typography>
      {error && <Alert severity="info">{t('import.addons.offline')}</Alert>}
      {changed && (
        <Alert severity="info">
          {t(
            changed === 'selection'
              ? 'import.addons.changed'
              : 'import.addons.preview_changed',
          )}
        </Alert>
      )}
      {catalog?.addons.length === 0 && (
        <Typography variant="body2">{t('import.addons.empty')}</Typography>
      )}
      {catalog?.addons.map((addon) => {
        const checked = value.some(
          (entry) => entry.id === addon.id && entry.sha256 === addon.sha256,
        );
        const needsUpdate = addon.min_build > catalog.build;
        return (
          <Stack key={addon.id} spacing={0.5} sx={{ overflowWrap: 'anywhere' }}>
            <FormControlLabel
              control={
                <Checkbox
                  checked={checked}
                  disabled={
                    disabled ||
                    busy ||
                    needsUpdate ||
                    (!checked && value.length >= 8)
                  }
                  onChange={(_, selected) => {
                    setChanged(undefined);
                    onChange(
                      selected
                        ? [...value, { id: addon.id, sha256: addon.sha256 }]
                        : value.filter((entry) => entry.id !== addon.id),
                    );
                  }}
                />
              }
              label={addon.title}
            />
            <Typography variant="body2">{addon.description}</Typography>
            <Typography
              component="time"
              dateTime={addon.updated_at}
              variant="caption"
              color="text.secondary"
            >
              {t('import.catalog.updated')}:{' '}
              {new Date(addon.updated_at).toLocaleDateString(
                langcode === 'en' ? 'en-GB' : 'ru-RU',
                {
                  day: '2-digit',
                  month: '2-digit',
                  year: 'numeric',
                  timeZone: 'UTC',
                },
              )}
            </Typography>
            {addon.attribution && (
              <Typography variant="caption" color="text.secondary">
                {addon.attribution}
              </Typography>
            )}
            {needsUpdate && (
              <Typography variant="caption">
                {t('import.catalog.update')}
              </Typography>
            )}
          </Stack>
        );
      })}
      {value.length >= 8 && (
        <Typography variant="caption">{t('import.addons.limit')}</Typography>
      )}
      {children}
    </Stack>
  );
};

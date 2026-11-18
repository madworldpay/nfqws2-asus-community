import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import en from '@/translations/en.json';
import {
  Alert,
  Button,
  CircularProgress,
  List,
  ListItemButton,
  ListItemText,
  Stack,
  TextField,
  Typography,
} from '@mui/material';

import {
  loadProfileCatalog,
  type CatalogProfile,
  type ProfileCatalog,
} from '@/api/profileCatalogClient';
import { ShareError } from '@/api/shareClient';

import {
  catalogDescription,
  CatalogEntryDetails,
} from '@/components/CatalogEntryDetails';
import { InlineHelp } from '@/components/InlineHelp';
import { StrategyNoteRow } from '@/components/StrategyNoteRow';

import {
  matchesStrategy,
  strategyNumber,
  useStrategyNotes,
} from '@/hooks/useStrategyNotes';
import { useTranslation } from '@/hooks/useTranslation';

const catalogErrorCodes = Object.keys(
  en.import.catalog.errors,
) as (keyof typeof en.import.catalog.errors)[];

export const ImportCatalog = ({
  csrfToken,
  disabled,
  onSelect,
}: {
  csrfToken: string;
  disabled: boolean;
  onSelect: (profile: CatalogProfile) => void;
}) => {
  const { t } = useTranslation();
  const [catalog, setCatalog] = useState<ProfileCatalog>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [query, setQuery] = useState('');
  const [editing, setEditing] = useState<string | null>(null);
  const { notes, write, failed: notesFailed } = useStrategyNotes();
  const numbered = useMemo(
    () =>
      catalog?.profiles.map((profile) => ({
        profile,
        number: strategyNumber('cloud', profile.id),
      })) ?? [],
    [catalog],
  );
  const words = query.trim().toLocaleLowerCase().split(/\s+/);
  const visible = numbered.filter(
    ({ profile, number }) =>
      number === editing ||
      matchesStrategy(words, [
        profile.title,
        profile.provider,
        profile.region,
        profile.attribution,
        catalogDescription(profile.description),
        notes[number],
      ]),
  );
  const generation = useRef(0);
  const pending = useRef(false);
  const refresh = useCallback(async () => {
    if (pending.current) return;
    const epoch = generation.current;
    pending.current = true;
    setBusy(true);
    setError(undefined);
    try {
      const result = await loadProfileCatalog(csrfToken);
      if (generation.current === epoch) setCatalog(result);
    } catch (e) {
      if (generation.current === epoch) {
        setCatalog(undefined);
        setError(e instanceof ShareError ? e.code : 'catalog_unavailable');
      }
    } finally {
      if (generation.current === epoch) {
        pending.current = false;
        setBusy(false);
      }
    }
  }, [csrfToken]);
  useEffect(() => {
    generation.current += 1;
    pending.current = false;
    setCatalog(undefined);
    void refresh();
    return () => {
      generation.current += 1;
      pending.current = false;
    };
  }, [refresh]);
  const knownError = catalogErrorCodes.find((code) => code === error);
  return (
    <Stack spacing={1}>
      <Stack direction="row" alignItems="center" spacing={1}>
        <Typography variant="subtitle1">{t('import.catalog.title')}</Typography>
        <InlineHelp title={t('import.catalog.help_title')}>
          {t('import.catalog.help')}
        </InlineHelp>
        <Button
          size="small"
          disabled={disabled || busy}
          onClick={() => void refresh()}
        >
          {t('import.catalog.refresh')}
        </Button>
        {busy && <CircularProgress size={18} />}
      </Stack>
      {error !== undefined && (
        <Alert severity="info">
          {t(
            knownError
              ? `import.catalog.errors.${knownError}`
              : 'import.catalog.offline',
          )}
        </Alert>
      )}
      {catalog?.profiles.length === 0 && (
        <Typography variant="body2">{t('import.catalog.empty')}</Typography>
      )}
      {numbered.length > 0 && (
        <>
          <TextField
            size="small"
            type="search"
            fullWidth
            label={t('import.catalog.search')}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <Typography variant="caption">{t('import.notes.local')}</Typography>
          {notesFailed && (
            <Alert severity="warning">{t('import.notes.unavailable')}</Alert>
          )}
          {!visible.length && (
            <Typography variant="body2" role="status">
              {t('import.notes.no_matches')}
            </Typography>
          )}
        </>
      )}
      {(['provider', 'global'] as const).map((category) => {
        const profiles = visible.filter(
          ({ profile }) => profile.category === category,
        );
        return (
          profiles.length > 0 && (
            <Stack key={category} spacing={0.5}>
              <Typography variant="subtitle2">
                {t(`import.catalog.${category}`)}
              </Typography>
              <List disablePadding>
                {profiles.map(({ profile, number }) => {
                  const needsUpdate = profile.min_build > (catalog?.build ?? 0);
                  return (
                    <StrategyNoteRow
                      key={profile.id}
                      number={number}
                      title={profile.title}
                      value={notes[number] ?? ''}
                      onChange={write}
                      onEdit={setEditing}
                    >
                      <ListItemButton
                        component="button"
                        disabled={disabled || busy || needsUpdate}
                        onClick={() => onSelect(profile)}
                        sx={{ width: '100%', textAlign: 'left' }}
                      >
                        <ListItemText
                          primary={profile.title}
                          secondary={
                            <>
                              {[profile.provider, profile.region]
                                .filter(Boolean)
                                .join(' · ')}
                              <CatalogEntryDetails
                                description={profile.description}
                                date={profile.updated_at}
                                attribution={profile.attribution}
                                note={
                                  needsUpdate
                                    ? t('import.catalog.update')
                                    : undefined
                                }
                              />
                            </>
                          }
                        />
                      </ListItemButton>
                    </StrategyNoteRow>
                  );
                })}
              </List>
            </Stack>
          )
        );
      })}
    </Stack>
  );
};

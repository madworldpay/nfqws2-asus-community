import { useCallback, useEffect, useRef, useState } from 'react';
import en from '@/translations/en.json';
import {
  Alert,
  Button,
  CircularProgress,
  List,
  ListItemButton,
  ListItemText,
  Stack,
  Typography,
} from '@mui/material';

import {
  loadProfileCatalog,
  type CatalogProfile,
  type ProfileCatalog,
} from '@/api/profileCatalogClient';
import { ShareError } from '@/api/shareClient';

import { InlineHelp } from '@/components/InlineHelp';

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
  const { t, langcode } = useTranslation();
  const [catalog, setCatalog] = useState<ProfileCatalog>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
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
      {(['provider', 'global'] as const).map((category) => {
        const profiles =
          catalog?.profiles.filter((p) => p.category === category) ?? [];
        return (
          profiles.length > 0 && (
            <Stack key={category} spacing={0.5}>
              <Typography variant="subtitle2">
                {t(`import.catalog.${category}`)}
              </Typography>
              <List disablePadding>
                {profiles.map((profile) => {
                  const needsUpdate = profile.min_build > (catalog?.build ?? 0);
                  return (
                    <ListItemButton
                      key={profile.id}
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
                            <Typography
                              component="span"
                              display="block"
                              variant="body2"
                            >
                              {profile.description}
                            </Typography>
                            <Typography
                              component="time"
                              dateTime={profile.updated_at}
                              display="block"
                              variant="caption"
                            >
                              {t('import.catalog.updated')}:{' '}
                              {new Date(profile.updated_at).toLocaleDateString(
                                langcode === 'en' ? 'en-GB' : 'ru-RU',
                                {
                                  day: '2-digit',
                                  month: '2-digit',
                                  year: 'numeric',
                                  timeZone: 'UTC',
                                },
                              )}
                            </Typography>
                            {needsUpdate && (
                              <Typography
                                component="span"
                                display="block"
                                variant="caption"
                              >
                                {t('import.catalog.update')}
                              </Typography>
                            )}
                            {profile.attribution && (
                              <Typography
                                component="span"
                                display="block"
                                variant="caption"
                              >
                                {profile.attribution}
                              </Typography>
                            )}
                          </>
                        }
                      />
                    </ListItemButton>
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

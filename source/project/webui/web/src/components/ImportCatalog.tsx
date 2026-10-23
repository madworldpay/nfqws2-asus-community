import { useCallback, useEffect, useRef, useState } from 'react';
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

import { InlineHelp } from '@/components/InlineHelp';

import { useTranslation } from '@/hooks/useTranslation';

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
  const [error, setError] = useState(false);
  const mounted = useRef(false);
  const pending = useRef(false);
  const refresh = useCallback(async () => {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setError(false);
    try {
      const result = await loadProfileCatalog(csrfToken);
      if (mounted.current) setCatalog(result);
    } catch {
      if (mounted.current) {
        setCatalog(undefined);
        setError(true);
      }
    } finally {
      pending.current = false;
      if (mounted.current) setBusy(false);
    }
  }, [csrfToken]);
  useEffect(() => {
    mounted.current = true;
    void refresh();
    return () => {
      mounted.current = false;
    };
  }, [refresh]);
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
      {error && <Alert severity="info">{t('import.catalog.offline')}</Alert>}
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

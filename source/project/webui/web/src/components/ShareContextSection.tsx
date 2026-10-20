import { useEffect, useState } from 'react';
import {
  Checkbox,
  FormControlLabel,
  Link,
  Stack,
  TextField,
  Typography,
} from '@mui/material';

import { getShareLocation, type ShareLocation } from '@/api/shareClient';

import type { ShareStrategyForm } from '@/components/ShareStrategySection';

import { useTranslation } from '@/hooks/useTranslation';

export const ShareContextSection = ({
  csrfToken,
  value,
  disabled,
  onChange,
  onLocation,
}: {
  csrfToken: string;
  value: ShareStrategyForm;
  disabled: boolean;
  onChange: (fn: (old: ShareStrategyForm) => ShareStrategyForm) => void;
  onLocation: (v: ShareLocation) => void;
}) => {
  const { t } = useTranslation();
  const [geoUnavailable, setGeoUnavailable] = useState(false);
  useEffect(() => {
    let active = true;
    void getShareLocation(csrfToken).then(
      (v) => {
        if (active) {
          setGeoUnavailable(!v.available);
          onLocation(v);
        }
      },
      () => {
        if (active) setGeoUnavailable(true);
      },
    );
    return () => {
      active = false;
    };
  }, [csrfToken, onLocation]);
  return (
    <Stack spacing={1.5}>
      <TextField
        size="small"
        required
        disabled={disabled}
        label={t('share.purpose')}
        value={value.context.purpose}
        slotProps={{ htmlInput: { maxLength: 120 } }}
        onChange={(e) =>
          onChange((old) => ({
            ...old,
            context: { ...old.context, purpose: e.target.value },
          }))
        }
      />
      <TextField
        size="small"
        required
        disabled={disabled}
        label={t('share.operator')}
        value={value.context.operator}
        helperText={t('share.operator_required')}
        slotProps={{ htmlInput: { maxLength: 120 } }}
        onChange={(e) =>
          onChange((old) => ({
            ...old,
            context: { ...old.context, operator: e.target.value },
          }))
        }
      />
      <TextField
        size="small"
        disabled={disabled}
        label={t('share.region')}
        value={value.context.region}
        slotProps={{ htmlInput: { maxLength: 120 } }}
        onChange={(e) =>
          onChange((old) => ({
            ...old,
            locationEdited: true,
            context: { ...old.context, region: e.target.value },
          }))
        }
      />
      <FormControlLabel
        control={
          <Checkbox
            checked={value.context.share_location}
            disabled={disabled}
            onChange={(_, share_location) =>
              onChange((old) => ({
                ...old,
                context: { ...old.context, share_location },
              }))
            }
          />
        }
        label={t('share.include_location')}
      />
      <Typography variant="caption">
        {t('share.location_hint')}{' '}
        <Link href="https://db-ip.com" target="_blank" rel="noreferrer">
          IP Geolocation by DB-IP
        </Link>
      </Typography>
      {geoUnavailable && (
        <Typography variant="caption">
          {t('share.location_unavailable')}
        </Typography>
      )}
      <TextField
        multiline
        minRows={2}
        maxRows={6}
        disabled={disabled}
        label={t('share.comment')}
        value={value.context.comment}
        slotProps={{ htmlInput: { maxLength: 2000 } }}
        onChange={(e) =>
          onChange((old) => ({
            ...old,
            context: { ...old.context, comment: e.target.value },
          }))
        }
      />
    </Stack>
  );
};

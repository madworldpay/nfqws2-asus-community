import { useEffect, useRef } from 'react';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Button,
  Stack,
  TextField,
  Typography,
} from '@mui/material';

import type { DnsPreview, Profile } from '@/api/smartDnsProfile';

import { InlineHelp } from '@/components/InlineHelp';

import { useTranslation } from '@/hooks/useTranslation';

export const SmartDnsPreview = ({
  preview,
  profile,
  onApply,
  disabled,
}: {
  preview: DnsPreview;
  profile: Profile;
  onApply: VoidFunction;
  disabled: boolean;
}) => {
  const { t } = useTranslation();
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus();
  }, [preview.id]);
  return (
    <Stack spacing={2}>
      <Typography component="h3" variant="h6" ref={heading} tabIndex={-1}>
        {t('smartdns.preview.title')}
      </Typography>
      <Stack direction="row" alignItems="center">
        <Typography variant="body2">{t('smartdns.preview.checked')}</Typography>
        <InlineHelp title={t('smartdns.preview.details')}>
          <Stack spacing={2}>
            <Typography>{t('smartdns.preview.scope')}</Typography>
            <Typography>{t('smartdns.preview.change')}</Typography>
          </Stack>
        </InlineHelp>
      </Stack>
      <Typography variant="body2">
        {t('smartdns.form.default')}:{' '}
        {profile.upstreams
          .filter((s) => s.default)
          .map((s) => s.label || s.address)
          .join(', ')}
      </Typography>
      {preview.groups.map((g, i) => (
        <Typography variant="body2" key={i} sx={{ overflowWrap: 'anywhere' }}>
          {g.domain}
          {g.include_subdomains ? ' + *' : ''} →{' '}
          {g.servers
            .map((id) => {
              const s = profile.upstreams.find((s) => s.id === id);
              return s?.label || s?.address || id;
            })
            .join(', ')}
        </Typography>
      ))}
      {preview.overlaps.length > 0 && (
        <Alert severity="info">
          {t('smartdns.preview.overlap')}{' '}
          {preview.overlaps
            .map((v) => `${v.record} → ${v.dns_domain}`)
            .join('; ')}
        </Alert>
      )}
      <Accordion disableGutters>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          {t('smartdns.preview.config')}
        </AccordionSummary>
        <AccordionDetails>
          <TextField
            fullWidth
            multiline
            minRows={8}
            maxRows={18}
            value={preview.config}
            slotProps={{
              input: { readOnly: true },
              htmlInput: { 'aria-label': t('smartdns.preview.config') },
            }}
            sx={{ '& textarea': { fontFamily: 'monospace', fontSize: 12 } }}
          />
        </AccordionDetails>
      </Accordion>
      <Button variant="contained" disabled={disabled} onClick={onApply}>
        {t('smartdns.connect')}
      </Button>
    </Stack>
  );
};

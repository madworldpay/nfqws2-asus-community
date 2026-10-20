import { useState } from 'react';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Checkbox,
  FormControlLabel,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';

import {
  applyDnsPreset,
  DNS_PRESETS,
  selectedDnsPreset,
} from '@/api/smartDnsPresets';
import {
  newUpstream,
  withDomain,
  type DnsUpstream,
  type Profile,
} from '@/api/smartDnsProfile';
import { newSupportSubmissionId } from '@/api/supportReport';

import { FieldHelp } from '@/components/FieldHelp';
import { InlineHelp } from '@/components/InlineHelp';

import { useTranslation } from '@/hooks/useTranslation';

const AddressListField = ({
  value,
  onChange,
  label,
  helperText,
  error,
  disabled,
}: {
  value: string[];
  onChange: (v: string[]) => void;
  label: string;
  helperText?: string;
  error?: boolean;
  disabled?: boolean;
}) => {
  const [input, setInput] = useState({
    text: value.join(', '),
    signature: value.join('|'),
  });
  const text =
    input.signature === value.join('|') ? input.text : value.join(', ');
  return (
    <TextField
      disabled={disabled}
      label={label}
      value={text}
      helperText={helperText}
      error={error}
      onChange={(e) => {
        const values = e.target.value.split(/[\s,]+/).filter(Boolean);
        setInput({ text: e.target.value, signature: values.join('|') });
        onChange(values);
      }}
    />
  );
};

export const SmartDnsProfileForm = ({
  value,
  onChange,
  disabled,
  errors = {},
}: {
  value: Profile;
  onChange: (p: Profile) => void;
  disabled: boolean;
  errors?: Record<string, string>;
}) => {
  const { t } = useTranslation();
  const [manual, setManual] = useState<Record<string, boolean>>({});
  const update = (i: number, patch: Partial<DnsUpstream>) =>
    onChange({
      ...value,
      upstreams: value.upstreams.map((s, n) =>
        n === i ? { ...s, ...patch } : s,
      ),
    });
  const field = (path: string) => {
    const message =
      errors[path] ||
      Object.entries(errors).find(([key]) => key.startsWith(path + '.'))?.[1];
    return { error: Boolean(message), helperText: message };
  };
  return (
    <Box
      component="fieldset"
      disabled={disabled}
      sx={{ border: 0, p: 0, m: 0, minWidth: 0 }}
    >
      <Stack spacing={2}>
        <Stack direction="row" alignItems="center">
          <Typography variant="body2">
            {t('smartdns.form.short_intro')}
          </Typography>
          <InlineHelp title={t('smartdns.configure')}>
            <Stack spacing={2}>
              <Typography>{t('smartdns.form.intro')}</Typography>
              <Typography>{t('smartdns.form.default_hint')}</Typography>
              <Typography>{t('smartdns.form.preset_hint')}</Typography>
              <Typography>{t('smartdns.form.bootstrap_hint')}</Typography>
            </Stack>
          </InlineHelp>
        </Stack>
        {errors['upstreams.default'] && (
          <Alert severity="info">{t('smartdns.form.default_needed')}</Alert>
        )}
        {value.upstreams.map((s, i) => (
          <Accordion disableGutters key={s.id} defaultExpanded={!s.address}>
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Typography sx={{ overflowWrap: 'anywhere' }}>
                {s.label || s.address || `DNS ${i + 1}`} ·{' '}
                {s.protocol.toUpperCase()}
                {s.default ? ` · ${t('smartdns.form.default')}` : ''}
                {s.domains.length
                  ? ` · ${s.domains.length} ${t('smartdns.form.site_count')}`
                  : ''}
              </Typography>
            </AccordionSummary>
            <AccordionDetails>
              <Stack spacing={2}>
                <Typography component="h3" variant="subtitle1">
                  DNS {i + 1}
                </Typography>
                <TextField
                  disabled={disabled}
                  select
                  fullWidth
                  label={t('smartdns.form.preset')}
                  value={selectedDnsPreset(s, manual[s.id] === true)}
                  onChange={(e) => {
                    setManual((v) => ({
                      ...v,
                      [s.id]: e.target.value === 'custom',
                    }));
                    if (e.target.value !== 'custom')
                      update(i, applyDnsPreset(s, e.target.value));
                  }}
                >
                  <MenuItem value="custom">
                    {t('smartdns.form.custom')}
                  </MenuItem>
                  {DNS_PRESETS.map((p) => (
                    <MenuItem value={p.id} key={p.id}>
                      {p.label}
                    </MenuItem>
                  ))}
                </TextField>
                <TextField
                  disabled={disabled}
                  label={t('smartdns.form.label')}
                  value={s.label}
                  onChange={(e) => update(i, { label: e.target.value })}
                  {...field(`upstreams.${i}.label`)}
                  slotProps={{ htmlInput: { maxLength: 80 } }}
                />
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                  <FieldHelp
                    title={t('smartdns.form.protocol')}
                    hint={t('smartdns.form.protocol_hint')}
                  >
                    <TextField
                      disabled={disabled}
                      select
                      fullWidth
                      label={t('smartdns.form.protocol')}
                      value={s.protocol}
                      onChange={(e) => {
                        const protocol = e.target
                          .value as DnsUpstream['protocol'];
                        update(i, {
                          protocol,
                          port:
                            protocol === 'doh'
                              ? 443
                              : protocol === 'dot'
                                ? 853
                                : 53,
                          tls_name: ['doh', 'dot'].includes(protocol)
                            ? s.tls_name
                            : '',
                          url: protocol === 'doh' ? s.url : '',
                        });
                      }}
                    >
                      {['udp', 'tcp', 'dot', 'doh'].map((p) => (
                        <MenuItem key={p} value={p}>
                          {p.toUpperCase()}
                        </MenuItem>
                      ))}
                    </TextField>
                  </FieldHelp>
                  <FieldHelp
                    title={t('smartdns.form.port')}
                    hint={t('smartdns.form.port_hint')}
                  >
                    <TextField
                      disabled={disabled}
                      fullWidth
                      label={t('smartdns.form.port')}
                      type="number"
                      value={s.port || ''}
                      onChange={(e) =>
                        update(i, { port: Number(e.target.value) })
                      }
                      {...field(`upstreams.${i}.port`)}
                    />
                  </FieldHelp>
                </Stack>
                <FieldHelp
                  title={t('smartdns.form.address')}
                  hint={t('smartdns.form.address_hint')}
                >
                  <TextField
                    disabled={disabled}
                    label={t('smartdns.form.address')}
                    value={s.address}
                    onChange={(e) => update(i, { address: e.target.value })}
                    {...field(`upstreams.${i}.address`)}
                  />
                </FieldHelp>
                <Stack direction="row" alignItems="center">
                  <FormControlLabel
                    control={
                      <Checkbox
                        disabled={disabled}
                        checked={s.default}
                        onChange={(_, v) => update(i, { default: v })}
                      />
                    }
                    label={t('smartdns.form.default')}
                  />
                  <InlineHelp title={t('smartdns.form.default')}>
                    <Typography>{t('smartdns.form.default_hint')}</Typography>
                  </InlineHelp>
                </Stack>
                <Stack direction="row" alignItems="center">
                  <Typography variant="subtitle2">
                    {t('smartdns.form.sites')}
                  </Typography>
                  <InlineHelp title={t('smartdns.form.sites')}>
                    <Typography>{t('smartdns.form.sites_hint')}</Typography>
                  </InlineHelp>
                </Stack>
                {s.domains.map((d, j) => (
                  <Stack key={j} spacing={1}>
                    <TextField
                      disabled={disabled}
                      label={t('smartdns.form.domain')}
                      value={d.name}
                      onChange={(e) =>
                        update(i, {
                          domains: s.domains.map((v, n) =>
                            n === j ? { ...v, name: e.target.value } : v,
                          ),
                        })
                      }
                      {...field(`upstreams.${i}.domains.${j}.name`)}
                    />
                    <Stack direction="row" flexWrap="wrap" alignItems="center">
                      <FormControlLabel
                        control={
                          <Checkbox
                            disabled={disabled}
                            checked={d.include_subdomains}
                            onChange={(_, v) =>
                              update(i, {
                                domains: s.domains.map((x, n) =>
                                  n === j ? { ...x, include_subdomains: v } : x,
                                ),
                              })
                            }
                          />
                        }
                        label={t('smartdns.form.subdomains')}
                      />
                      <Button
                        disabled={disabled}
                        size="small"
                        onClick={() =>
                          update(i, {
                            domains: s.domains.filter((_, n) => n !== j),
                          })
                        }
                      >
                        {t('smartdns.form.remove_site')}
                      </Button>
                    </Stack>
                  </Stack>
                ))}
                <Button
                  disabled={
                    disabled ||
                    value.upstreams.reduce((n, v) => n + v.domains.length, 0) >=
                      256
                  }
                  onClick={() =>
                    onChange(
                      withDomain(value, i, {
                        name: '',
                        include_subdomains: false,
                      }),
                    )
                  }
                >
                  {t('smartdns.form.add_site')}
                </Button>
                <Accordion
                  disabled={disabled}
                  disableGutters
                  defaultExpanded={
                    !!Object.keys(errors).find(
                      (k) =>
                        k.startsWith(`upstreams.${i}.tls`) ||
                        k.startsWith(`upstreams.${i}.bootstrap`) ||
                        k.startsWith(`upstreams.${i}.url`),
                    )
                  }
                >
                  <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                    {t('smartdns.form.connection')}
                  </AccordionSummary>
                  <AccordionDetails>
                    <Stack spacing={2}>
                      {['dot', 'doh'].includes(s.protocol) && (
                        <FieldHelp
                          title={t('smartdns.form.tls_name')}
                          hint={t('smartdns.form.tls_hint')}
                        >
                          <TextField
                            disabled={disabled}
                            required
                            label={t('smartdns.form.tls_name')}
                            value={s.tls_name}
                            onChange={(e) =>
                              update(i, { tls_name: e.target.value })
                            }
                            {...field(`upstreams.${i}.tls_name`)}
                          />
                        </FieldHelp>
                      )}
                      {s.protocol === 'doh' && (
                        <TextField
                          disabled={disabled}
                          required
                          label="DoH URL"
                          value={s.url}
                          onChange={(e) => update(i, { url: e.target.value })}
                          {...field(`upstreams.${i}.url`)}
                          slotProps={{ htmlInput: { maxLength: 2048 } }}
                        />
                      )}
                      <FieldHelp
                        title={t('smartdns.form.bootstrap')}
                        hint={t('smartdns.form.bootstrap_hint')}
                      >
                        <AddressListField
                          disabled={disabled}
                          label={t('smartdns.form.bootstrap')}
                          value={s.bootstrap}
                          onChange={(bootstrap) => update(i, { bootstrap })}
                          {...field(`upstreams.${i}.bootstrap`)}
                          helperText={
                            field(`upstreams.${i}.bootstrap`).helperText
                          }
                        />
                      </FieldHelp>
                    </Stack>
                  </AccordionDetails>
                </Accordion>
                <Button
                  disabled={disabled}
                  color="error"
                  size="small"
                  onClick={() =>
                    onChange({
                      ...value,
                      upstreams: value.upstreams.filter((_, n) => n !== i),
                    })
                  }
                >
                  {t('smartdns.form.remove_dns')}
                </Button>
              </Stack>
            </AccordionDetails>
          </Accordion>
        ))}
        <Button
          disabled={disabled || value.upstreams.length >= 32}
          onClick={() => {
            const s = newUpstream(
              'dns_' + newSupportSubmissionId().replace(/-/g, '').slice(0, 12),
            );
            s.default = value.upstreams.length === 0;
            onChange({ ...value, upstreams: [...value.upstreams, s] });
          }}
        >
          {t('smartdns.form.add_dns')}
        </Button>
        <Stack direction="row" alignItems="center">
          <Typography component="h3" variant="subtitle1">
            {t('smartdns.form.records')}
          </Typography>
          <InlineHelp title={t('smartdns.form.records')}>
            <Typography>{t('smartdns.form.records_hint')}</Typography>
          </InlineHelp>
        </Stack>
        {value.records.map((r, i) => {
          const updateRecord = (patch: Partial<typeof r>) =>
            onChange({
              ...value,
              records: value.records.map((v, n) =>
                n === i ? { ...v, ...patch } : v,
              ),
            });
          return (
            <Accordion
              disableGutters
              key={i}
              defaultExpanded={
                !r.name ||
                Object.keys(errors).some((k) => k.startsWith(`records.${i}.`))
              }
            >
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Typography sx={{ overflowWrap: 'anywhere' }}>
                  {r.name || t('smartdns.form.add_record')}
                  {r.addresses.length ? ` → ${r.addresses.join(', ')}` : ''}
                </Typography>
              </AccordionSummary>
              <AccordionDetails>
                <Stack spacing={2}>
                  <TextField
                    disabled={disabled}
                    label={t('smartdns.form.domain')}
                    value={r.name}
                    onChange={(e) => updateRecord({ name: e.target.value })}
                    {...field(`records.${i}.name`)}
                  />
                  <FieldHelp
                    title={t('smartdns.form.addresses')}
                    hint={t('smartdns.form.records_hint')}
                  >
                    <AddressListField
                      disabled={disabled}
                      label={t('smartdns.form.addresses')}
                      value={r.addresses}
                      onChange={(addresses) => updateRecord({ addresses })}
                      {...field(`records.${i}.addresses`)}
                    />
                  </FieldHelp>
                  <FormControlLabel
                    control={
                      <Checkbox
                        disabled={disabled}
                        checked={r.include_subdomains}
                        onChange={(_, v) =>
                          updateRecord({ include_subdomains: v })
                        }
                      />
                    }
                    label={t('smartdns.form.subdomains')}
                  />
                  <TextField
                    disabled={disabled}
                    type="date"
                    label={t('smartdns.form.checked_at')}
                    value={r.checked_at || ''}
                    onChange={(e) =>
                      updateRecord({ checked_at: e.target.value || null })
                    }
                    slotProps={{ inputLabel: { shrink: true } }}
                    {...field(`records.${i}.checked_at`)}
                  />
                  <Button
                    disabled={disabled}
                    size="small"
                    color="error"
                    onClick={() =>
                      onChange({
                        ...value,
                        records: value.records.filter((_, n) => n !== i),
                      })
                    }
                  >
                    {t('smartdns.form.remove_record')}
                  </Button>
                </Stack>
              </AccordionDetails>
            </Accordion>
          );
        })}
        <FieldHelp
          title={t('smartdns.form.add_record')}
          hint={t('smartdns.form.records_hint')}
        >
          <Button
            disabled={disabled || value.records.length >= 64}
            onClick={() =>
              onChange({
                ...value,
                records: [
                  ...value.records,
                  {
                    name: '',
                    include_subdomains: false,
                    addresses: [],
                    checked_at: null,
                  },
                ],
              })
            }
          >
            {t('smartdns.form.add_record')}
          </Button>
        </FieldHelp>
      </Stack>
    </Box>
  );
};

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
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';

import {
  getShareDnsSources,
  type DnsSelection,
  type DnsSource,
  type DnsSources,
} from '@/api/shareResourcesClient';
import type { DnsUpstream, StaticRecord } from '@/api/smartDnsProfile';

import { FieldHelp } from '@/components/FieldHelp';
import { InlineHelp } from '@/components/InlineHelp';

import { useTranslation } from '@/hooks/useTranslation';

export const ShareDnsSection = ({
  csrfToken,
  providedSources,
  value,
  disabled,
  onChange,
  onError,
}: {
  csrfToken: string;
  providedSources?: DnsSource[];
  value: DnsSelection[];
  disabled: boolean;
  onChange: (value: DnsSelection[]) => void;
  onError: (e: unknown) => void;
}) => {
  const { t } = useTranslation();
  const [sources, setSources] = useState<DnsSources>();
  const [loading, setLoading] = useState(false);
  const alive = useRef(false);
  useEffect(() => {
    alive.current = true;
    if (providedSources)
      return () => {
        alive.current = false;
      };
    let active = true;
    void getShareDnsSources(csrfToken).then(
      (v) => {
        if (active) setSources(v);
      },
      (e) => {
        if (active) onError(e);
      },
    );
    return () => {
      active = false;
      alive.current = false;
    };
  }, [csrfToken, onError, providedSources]);
  const update = (
    source: DnsSource,
    fn: (old: DnsSelection) => DnsSelection,
  ) => {
    const old = value.find((s) => s.source_id === source.id) ?? {
      source_id: source.id,
      source_sha256: source.sha256,
      upstreams: [],
      records: [],
    };
    const next = fn(old);
    onChange([
      ...value.filter((s) => s.source_id !== source.id),
      ...(next.upstreams.length || next.records.length ? [next] : []),
    ]);
  };
  const card = (
    source: DnsSource,
    id: string,
    fn: (v: DnsUpstream) => DnsUpstream,
  ) =>
    update(source, (old) => ({
      ...old,
      upstreams: old.upstreams.map((s) => (s.id === id ? fn(s) : s)),
    }));
  const record = (
    source: DnsSource,
    index: number,
    fn: (v: StaticRecord) => StaticRecord,
  ) =>
    update(source, (old) => ({
      ...old,
      records: old.records.map((r) =>
        r.index === index ? { ...r, value: fn(r.value) } : r,
      ),
    }));
  const refresh = async () => {
    if (disabled || loading) return;
    setLoading(true);
    onChange([]);
    try {
      const v = await getShareDnsSources(csrfToken);
      if (alive.current) setSources(v);
    } catch (e) {
      if (alive.current) onError(e);
    } finally {
      if (alive.current) setLoading(false);
    }
  };
  const data = providedSources
    ? { sources: providedSources, warnings: [] }
    : sources;
  return (
    <Stack spacing={1.5}>
      <Typography>{t('share.dns_title')}</Typography>
      <Typography variant="body2">
        {t(providedSources ? 'import.dns_hint' : 'share.dns_hint')}
      </Typography>
      {!providedSources && (
        <Button disabled={disabled || loading} onClick={() => void refresh()}>
          {t('share.refresh_dns')}
        </Button>
      )}
      {!!data?.warnings.length && (
        <Alert severity="info">{t('share.dns_source_unavailable')}</Alert>
      )}
      {data?.sources.map((source) => {
        const selected = value.find((v) => v.source_id === source.id);
        return (
          <Accordion key={source.id}>
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              {providedSources && t('import.from_json')}
              {t(`share.dns_origins.${source.origin}`)} ·{' '}
              {source.profile.upstreams.length} DNS
            </AccordionSummary>
            <AccordionDetails>
              <Stack spacing={2}>
                {!source.complete && (
                  <Alert severity="info">
                    {t('share.dns_partial')}{' '}
                    {source.warnings
                      .map((w) => `${w.line}: ${w.code}`)
                      .join(', ')}
                  </Alert>
                )}
                {source.profile.upstreams.map((original) => {
                  const copy = selected?.upstreams.find(
                    (s) => s.id === original.id,
                  );
                  const edit = (fn: (v: DnsUpstream) => DnsUpstream) =>
                    card(source, original.id, fn);
                  return (
                    <Stack key={original.id} spacing={1}>
                      <FormControlLabel
                        control={
                          <Checkbox
                            checked={!!copy}
                            disabled={disabled || loading}
                            onChange={(_, checked) =>
                              update(source, (old) => ({
                                ...old,
                                upstreams: checked
                                  ? [
                                      ...old.upstreams,
                                      structuredClone(original),
                                    ]
                                  : old.upstreams.filter(
                                      (s) => s.id !== original.id,
                                    ),
                              }))
                            }
                          />
                        }
                        label={`${original.label || original.address} · ${original.protocol.toUpperCase()}`}
                      />
                      {copy && (
                        <>
                          <TextField
                            size="small"
                            label={t('smartdns.form.label')}
                            value={copy.label}
                            disabled={disabled}
                            onChange={(e) =>
                              edit((v) => ({ ...v, label: e.target.value }))
                            }
                          />
                          <FieldHelp
                            title={t('smartdns.form.protocol')}
                            hint={t('smartdns.form.protocol_hint')}
                          >
                            <TextField
                              select
                              size="small"
                              label={t('smartdns.form.protocol')}
                              value={copy.protocol}
                              disabled={disabled}
                              onChange={(e) =>
                                edit((v) => ({
                                  ...v,
                                  protocol: e.target
                                    .value as DnsUpstream['protocol'],
                                }))
                              }
                            >
                              {['udp', 'tcp', 'dot', 'doh'].map((p) => (
                                <MenuItem key={p} value={p}>
                                  {p.toUpperCase()}
                                </MenuItem>
                              ))}
                            </TextField>
                          </FieldHelp>
                          <FieldHelp
                            title={t('smartdns.form.address')}
                            hint={t('smartdns.form.address_hint')}
                          >
                            <TextField
                              size="small"
                              label={t('smartdns.form.address')}
                              value={copy.address}
                              disabled={disabled}
                              onChange={(e) =>
                                edit((v) => ({ ...v, address: e.target.value }))
                              }
                            />
                          </FieldHelp>
                          <FieldHelp
                            title={t('smartdns.form.port')}
                            hint={t('smartdns.form.port_hint')}
                          >
                            <TextField
                              size="small"
                              type="number"
                              label={t('smartdns.form.port')}
                              value={copy.port}
                              disabled={disabled}
                              onChange={(e) =>
                                edit((v) => ({
                                  ...v,
                                  port: Number(e.target.value),
                                }))
                              }
                            />
                          </FieldHelp>
                          <FieldHelp
                            title={t('smartdns.form.tls_name')}
                            hint={t('smartdns.form.tls_hint')}
                          >
                            <TextField
                              size="small"
                              label={t('smartdns.form.tls_name')}
                              value={copy.tls_name}
                              disabled={disabled}
                              onChange={(e) =>
                                edit((v) => ({
                                  ...v,
                                  tls_name: e.target.value,
                                }))
                              }
                            />
                          </FieldHelp>
                          <TextField
                            size="small"
                            label="DoH URL"
                            value={copy.url}
                            disabled={disabled}
                            onChange={(e) =>
                              edit((v) => ({ ...v, url: e.target.value }))
                            }
                          />
                          <FieldHelp
                            title={t('smartdns.form.bootstrap')}
                            hint={t('smartdns.form.bootstrap_hint')}
                          >
                            <TextField
                              size="small"
                              label={t('smartdns.form.bootstrap')}
                              value={copy.bootstrap.join(', ')}
                              disabled={disabled}
                              onChange={(e) =>
                                edit((v) => ({
                                  ...v,
                                  bootstrap: e.target.value
                                    .split(/[\s,]+/)
                                    .filter(Boolean),
                                }))
                              }
                            />
                          </FieldHelp>
                          <Stack direction="row" alignItems="center">
                            <FormControlLabel
                              control={
                                <Checkbox
                                  checked={copy.default}
                                  disabled={disabled}
                                  onChange={(_, checked) =>
                                    edit((v) => ({ ...v, default: checked }))
                                  }
                                />
                              }
                              label={t('smartdns.form.default')}
                            />
                            <InlineHelp title={t('smartdns.form.default')}>
                              <Typography>
                                {t('smartdns.form.default_hint')}
                              </Typography>
                            </InlineHelp>
                          </Stack>
                          <Typography variant="caption">
                            {t(
                              providedSources
                                ? 'import.dns_default_hint'
                                : 'share.dns_domains_hint',
                            )}
                          </Typography>
                          {copy.domains.map((d, i) => (
                            <Stack
                              key={i}
                              direction="row"
                              useFlexGap
                              flexWrap="wrap"
                              spacing={1}
                            >
                              <TextField
                                size="small"
                                label={t('share.dns_domain')}
                                value={d.name}
                                disabled={disabled}
                                onChange={(e) =>
                                  edit((v) => ({
                                    ...v,
                                    domains: v.domains.map((row, j) =>
                                      i === j
                                        ? { ...row, name: e.target.value }
                                        : row,
                                    ),
                                  }))
                                }
                              />
                              <FormControlLabel
                                control={
                                  <Checkbox
                                    checked={d.include_subdomains}
                                    disabled={disabled}
                                    onChange={(_, checked) =>
                                      edit((v) => ({
                                        ...v,
                                        domains: v.domains.map((row, j) =>
                                          i === j
                                            ? {
                                                ...row,
                                                include_subdomains: checked,
                                              }
                                            : row,
                                        ),
                                      }))
                                    }
                                  />
                                }
                                label={t('share.dns_subdomains')}
                              />
                              <Button
                                disabled={disabled}
                                onClick={() =>
                                  edit((v) => ({
                                    ...v,
                                    domains: v.domains.filter(
                                      (_, j) => j !== i,
                                    ),
                                  }))
                                }
                              >
                                {t('smartdns.form.remove_site')}
                              </Button>
                            </Stack>
                          ))}
                          <Button
                            disabled={disabled}
                            onClick={() =>
                              edit((v) => ({
                                ...v,
                                domains: [
                                  ...v.domains,
                                  { name: '', include_subdomains: true },
                                ],
                              }))
                            }
                          >
                            {t('share.dns_add_domain')}
                          </Button>
                        </>
                      )}
                    </Stack>
                  );
                })}
                {source.profile.records.map((original, index) => {
                  const copy = selected?.records.find(
                    (r) => r.index === index,
                  )?.value;
                  return (
                    <Stack key={index} spacing={1}>
                      <FormControlLabel
                        control={
                          <Checkbox
                            checked={!!copy}
                            disabled={disabled || loading}
                            onChange={(_, checked) =>
                              update(source, (old) => ({
                                ...old,
                                records: checked
                                  ? [
                                      ...old.records,
                                      {
                                        index,
                                        value: structuredClone(original),
                                      },
                                    ]
                                  : old.records.filter(
                                      (r) => r.index !== index,
                                    ),
                              }))
                            }
                          />
                        }
                        label={`${original.name} → ${original.addresses.join(', ')}`}
                      />
                      {copy && (
                        <>
                          <TextField
                            size="small"
                            label={t('share.dns_domain')}
                            value={copy.name}
                            disabled={disabled}
                            onChange={(e) =>
                              record(source, index, (v) => ({
                                ...v,
                                name: e.target.value,
                              }))
                            }
                          />
                          <FieldHelp
                            title={t('smartdns.form.records')}
                            hint={t('smartdns.form.records_hint')}
                          >
                            <TextField
                              size="small"
                              label={t('share.dns_addresses')}
                              value={copy.addresses.join(', ')}
                              disabled={disabled}
                              onChange={(e) =>
                                record(source, index, (v) => ({
                                  ...v,
                                  addresses: e.target.value
                                    .split(/[\s,]+/)
                                    .filter(Boolean),
                                  checked_at: null,
                                }))
                              }
                            />
                          </FieldHelp>
                          <FormControlLabel
                            control={
                              <Checkbox
                                checked={copy.include_subdomains}
                                disabled={disabled}
                                onChange={(_, checked) =>
                                  record(source, index, (v) => ({
                                    ...v,
                                    include_subdomains: checked,
                                    checked_at: null,
                                  }))
                                }
                              />
                            }
                            label={t('share.dns_subdomains')}
                          />
                        </>
                      )}
                    </Stack>
                  );
                })}
              </Stack>
            </AccordionDetails>
          </Accordion>
        );
      })}
    </Stack>
  );
};

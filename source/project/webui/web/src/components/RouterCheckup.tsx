import { useEffect, useState } from 'react';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import { Alert, Button, Chip, Paper, Stack, Typography } from '@mui/material';

import { getRouterCheckup, type Checkup } from '@/api/smartDnsConfigClient';

import { InlineHelp } from '@/components/InlineHelp';

import { useTranslation } from '@/hooks/useTranslation';

export const RouterCheckup = ({
  csrf,
  onOpenSmartDns,
  onResult,
  scope = 'router',
}: {
  scope?: 'router' | 'smartdns';
  csrf: string;
  onOpenSmartDns?: VoidFunction;
  onResult?: (data: Checkup) => void;
}) => {
  const { t } = useTranslation();
  const [data, setData] = useState<Checkup>();
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let active = true;
    void getRouterCheckup(csrf)
      .then((d) => {
        if (active) {
          setData(d);
          onResult?.(d);
          setError(false);
        }
      })
      .catch(() => {
        if (active) setError(true);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [csrf, refresh, onResult]);
  const facts = (id: string) => data?.items.find((x) => x.id === id)?.facts;
  const mib = (v: unknown, scale = 1048576) =>
    typeof v === 'number' || (typeof v === 'string' && /^\d+$/.test(v))
      ? `${(Number(v) / scale).toFixed(1)} MiB`
      : t('smartdns.checkup.unknown');
  const platform = facts('platform');
  const memory = facts('memory');
  const codes = [
    ...new Set(data?.readiness.smartdns_connect.codes ?? []),
  ].filter((code) => code !== 'not_installed' && code !== 'external_smartdns');
  const attention = (code: string) =>
    t(
      ['jffs_scripts_disabled', 'jffs_scripts_unknown'].includes(code)
        ? 'smartdns.checkup.need_scripts'
        : code === 'jffs_unavailable'
          ? 'smartdns.checkup.need_jffs'
          : ['invalid_clock', 'https_unavailable'].includes(code)
            ? 'smartdns.checkup.need_tls'
            : 'smartdns.checkup.need_review',
    );
  return (
    <Paper variant="outlined" sx={{ p: 1.5 }}>
      <Stack spacing={1}>
        <Stack
          direction="row"
          alignItems="center"
          spacing={1}
          useFlexGap
          flexWrap="wrap"
        >
          <Typography variant="subtitle2">
            {t('smartdns.checkup.title')}
            {platform ? ` · ${String(platform.model || '')}` : ''}
          </Typography>
          <InlineHelp title={t('smartdns.checkup.details')}>
            <Stack spacing={2}>
              <Typography variant="body2">
                {t('smartdns.checkup.readonly')}
              </Typography>
              {platform && (
                <Typography variant="body2">
                  {String(platform.kernel || '—')} · Entware{' '}
                  {String(platform.entware_abi || '—')}
                </Typography>
              )}
              {memory && (
                <Typography variant="body2">
                  {t('smartdns.checkup.memory')}:{' '}
                  {mib(memory.available_kib, 1024)}
                  {memory.available_estimated === true ? ' ≈' : ''} · NFQWS2
                  RSS: {mib(memory.nfqws2_rss_kib, 1024)}
                </Typography>
              )}
              {(['storage_opt', 'storage_jffs'] as const).map((id) => {
                const f = facts(id);
                return (
                  f && (
                    <Typography variant="body2" key={id}>
                      {id === 'storage_opt' ? '/opt' : 'JFFS'}:{' '}
                      {mib(f.free_bytes)} ·{' '}
                      {t(
                        f.readonly === true
                          ? 'smartdns.checkup.readonly_storage'
                          : 'smartdns.checkup.write_estimate',
                      )}
                    </Typography>
                  )
                );
              })}
              <Typography variant="body2">
                {t('smartdns.checkup.ark_help')}
              </Typography>
              <Typography variant="body2">
                {t('smartdns.checkup.hooks')}
              </Typography>
            </Stack>
          </InlineHelp>
          <Button
            size="small"
            disabled={loading}
            onClick={() => {
              setLoading(true);
              setRefresh((v) => v + 1);
            }}
          >
            {t('smartdns.checkup.refresh')}
          </Button>
          {onOpenSmartDns && (
            <Button size="small" onClick={onOpenSmartDns}>
              {t('smartdns.checkup.open')}
            </Button>
          )}
        </Stack>
        {error && <Alert severity="info">{t('smartdns.request_error')}</Alert>}
        {scope === 'router' && (
          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
            {(['process', 'nfqueue', 'ark'] as const).map((id) => {
              const x = data?.items.find((v) => v.id === id);
              if (!x) return null;
              const good = x.state === 'ready';
              const label =
                id === 'ark'
                  ? t(
                      x.facts.loaded === true
                        ? 'ark.loaded'
                        : x.facts.loaded === false
                          ? 'ark.unloaded'
                          : 'ark.unknown',
                    )
                  : id === 'process'
                    ? t(
                        x.facts.running === true
                          ? 'smartdns.checkup.running'
                          : x.facts.running === false
                            ? 'smartdns.checkup.stopped'
                            : 'smartdns.checkup.unknown',
                      )
                    : `${String(x.facts.number ?? '—')} · ${t(x.facts.bound === true ? 'smartdns.checkup.bound' : 'smartdns.checkup.unbound')}`;
              return (
                <Chip
                  key={id}
                  size="small"
                  variant="outlined"
                  color={
                    good
                      ? 'success'
                      : id === 'ark' && x.facts.loaded === true
                        ? 'warning'
                        : 'default'
                  }
                  icon={
                    good ? <CheckCircleOutlineIcon /> : <InfoOutlinedIcon />
                  }
                  label={t(`smartdns.checkup.${id}`) + ': ' + label}
                />
              );
            })}
          </Stack>
        )}
        {data &&
          !data.readiness.smartdns_connect.codes.includes(
            'external_smartdns',
          ) &&
          (data.readiness.smartdns_connect.ready ||
            data.readiness.smartdns_install.ready) &&
          codes.length === 0 &&
          scope === 'smartdns' && (
            <Stack direction="row" spacing={1} alignItems="center">
              <CheckCircleOutlineIcon color="success" fontSize="small" />
              <Typography variant="body2">
                {t('smartdns.checkup.suitable')}
              </Typography>
            </Stack>
          )}
        {codes.length > 0 && (
          <Alert severity="info">
            {[...new Set(codes.map(attention))].join(' ')}
          </Alert>
        )}
      </Stack>
    </Paper>
  );
};

import { useEffect, useState } from 'react';
import { Button, Stack, Typography } from '@mui/material';

import { addWanClient, getRouterWan, type RouterWan } from '@/api/routerWan';

import { useStatus } from '@/hooks/useStatus';
import { useTranslation } from '@/hooks/useTranslation';

export const RouterWanInfo = ({
  clients,
  mode,
  onChange,
}: {
  clients: string;
  mode: string;
  onChange: (clients: string) => void;
}) => {
  const { csrfToken } = useStatus();
  const { t } = useTranslation();
  const [data, setData] = useState<RouterWan>();
  const [loading, setLoading] = useState(true);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    if (!csrfToken) return;
    let active = true;
    void getRouterWan(csrfToken)
      .then((value) => {
        if (active) setData(value);
      })
      .catch(() => {
        if (active) setData(undefined);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [csrfToken, refresh]);

  return (
    <Stack spacing={0.5} sx={{ mt: 1 }}>
      <Typography variant="body2">{t('form.WAN_TITLE')}</Typography>
      {loading ? (
        <Typography variant="caption">{t('form.WAN_LOADING')}</Typography>
      ) : data?.addresses.length ? (
        data.addresses.map((row) => (
          <Stack
            key={`${row.interface}:${row.address}`}
            direction="row"
            alignItems="center"
            spacing={1}
            useFlexGap
            flexWrap="wrap"
          >
            <Typography
              component="code"
              variant="body2"
              sx={{ userSelect: 'all' }}
            >
              {row.address}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {row.interface}
            </Typography>
            {mode === 'include' && (
              <Button
                size="small"
                disabled={addWanClient(clients, row.address) === clients}
                onClick={() => onChange(addWanClient(clients, row.address))}
              >
                {t(
                  addWanClient(clients, row.address) === clients
                    ? 'form.WAN_INCLUDED'
                    : 'form.WAN_ADD',
                )}
              </Button>
            )}
          </Stack>
        ))
      ) : (
        <Typography variant="caption">{t('form.WAN_UNAVAILABLE')}</Typography>
      )}
      {data?.state === 'partial' && !loading && (
        <Typography variant="caption">{t('form.WAN_PARTIAL')}</Typography>
      )}
      <Typography variant="caption" color="text.secondary">
        {t('form.WAN_HELP')}{' '}
        {mode === 'all'
          ? t('form.WAN_ALL')
          : mode === 'exclude'
            ? t('form.WAN_EXCLUDE')
            : ''}
      </Typography>
      <Button
        size="small"
        disabled={loading}
        sx={{ alignSelf: 'flex-start' }}
        onClick={() => {
          setLoading(true);
          setData(undefined);
          setRefresh((value) => value + 1);
        }}
      >
        {t('form.WAN_REFRESH')}
      </Button>
    </Stack>
  );
};

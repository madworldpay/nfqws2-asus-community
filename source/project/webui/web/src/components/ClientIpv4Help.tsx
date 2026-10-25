import { Box, Stack } from '@mui/material';

import { useTranslation } from '@/hooks/useTranslation';

export function ClientIpv4Help({ mode }: { mode: string }) {
  const { t } = useTranslation();
  return (
    <>
      {t('form.ASUS_CLIENT_HELP')}
      {mode === 'include' && (
        <Stack component="span" spacing={0.5} sx={{ mt: 1 }}>
          <Box component="span">{t('form.ASUS_CLIENTS4_EXAMPLES')}</Box>
          <Box component="span">
            {t('form.ASUS_CLIENTS4_ONE')} <code>192.168.1.100</code>
          </Box>
          <Box component="span">
            {t('form.ASUS_CLIENTS4_TWO')}{' '}
            <code>192.168.1.100 192.168.1.120</code>
          </Box>
          <Box component="span">{t('form.ASUS_CLIENTS4_DHCP')}</Box>
        </Stack>
      )}
    </>
  );
}

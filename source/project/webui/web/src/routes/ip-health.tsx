import { Alert } from '@mui/material';
import { createFileRoute } from '@tanstack/react-router';

import { App } from '@/components/App';
import { IpHealthPanel } from '@/components/IpHealthPanel';

import { useStatus } from '@/hooks/useStatus';
import { useTranslation } from '@/hooks/useTranslation';

export const Route = createFileRoute('/ip-health')({
  component: IpHealthPage,
});

function IpHealthPage() {
  const { platform } = useStatus();
  const { t } = useTranslation();
  return (
    <App showFilesTabs={false}>
      {platform === 'asus-entware' ? (
        <IpHealthPanel />
      ) : (
        <Alert severity="info" sx={{ m: 2 }}>
          {t('ip_health.runtime.unavailable')}
        </Alert>
      )}
    </App>
  );
}

import { createFileRoute } from '@tanstack/react-router';

import { App } from '@/components/App';
import { KeeneticSmartDnsPanel } from '@/components/KeeneticSmartDnsPanel';
import { SmartDnsPanel } from '@/components/SmartDnsPanel';

import { useStatus } from '@/hooks/useStatus';

export const Route = createFileRoute('/smartdns')({
  component: SmartDnsPage,
});

function SmartDnsPage() {
  const { platform, isReady } = useStatus();
  return (
    <App showFilesTabs={false}>
      {isReady &&
        (platform === 'keenetic-entware' ? (
          <KeeneticSmartDnsPanel />
        ) : (
          <SmartDnsPanel />
        ))}
    </App>
  );
}

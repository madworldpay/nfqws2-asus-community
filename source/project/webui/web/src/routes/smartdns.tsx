import { createFileRoute } from '@tanstack/react-router';

import { App } from '@/components/App';
import { SmartDnsPanel } from '@/components/SmartDnsPanel';

export const Route = createFileRoute('/smartdns')({
  component: SmartDnsPage,
});

function SmartDnsPage() {
  return (
    <App showFilesTabs={false}>
      <SmartDnsPanel />
    </App>
  );
}

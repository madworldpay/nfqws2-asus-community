import type { QueryClient } from '@tanstack/react-query';

import { createRouterAPIClient } from '@/api/createRouterAPIClient';

export interface RouterContext {
  apis: {
    api: ReturnType<typeof createRouterAPIClient>;
  };
}

export function createRouterProviderContext(
  queryClient: QueryClient,
): RouterContext {
  return {
    apis: {
      api: createRouterAPIClient(queryClient),
    },
  };
}

import { requestFn } from '@openapi-qraft/react';
import type { QueryClient } from '@tanstack/react-query';

import { baseUrl } from '@/api/baseUrl';
import { createRouterAPIClientBase } from '@/api/create-router-api-client-base';

export function createRouterAPIClient(queryClient: QueryClient) {
  return createRouterAPIClientBase({
    queryClient,
    baseUrl,
    requestFn,
  });
}

import { routeTree } from '@/routeTree.generated';
import { createRouter } from '@tanstack/react-router';

export function createAppRouter() {
  return createRouter({
    context: {
      apis: {
        api: undefined!, // This will be set in the AppRouterProvider
      },
    },
    routeTree,
    defaultPreload: 'render',
  });
}

import { routeTree } from '@/routeTree.generated';
import { panelBase } from '@/api/panelPaths.js';
import { createHashHistory, createRouter } from '@tanstack/react-router';

export function createAppRouter() {
  return createRouter({
    context: {
      apis: {
        api: undefined!, // This will be set in the AppRouterProvider
      },
    },
    routeTree,
    history: panelBase === '/' ? undefined : createHashHistory(),
    defaultPreload: 'render',
  });
}

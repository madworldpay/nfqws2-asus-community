import type { ReactNode } from 'react';

import './RabbitBuildBadge.css';

export type RabbitBuildState = 'off' | 'idle' | 'update' | 'unknown';

export const RabbitBuildBadge = ({
  state,
  children,
}: {
  state: RabbitBuildState;
  children: ReactNode;
}) => (
  <div className="rabbit-build-stage" data-state={state}>
    {state === 'update' && (
      <div
        className="rabbit-build-sprite rabbit-build-grip rabbit-build-back"
        aria-hidden="true"
      />
    )}
    <div className="rabbit-build-native">{children}</div>
    {state === 'off' && (
      <div
        className="rabbit-build-sprite rabbit-build-off"
        aria-hidden="true"
      />
    )}
    {state === 'idle' && (
      <div
        className="rabbit-build-sprite rabbit-build-idle"
        aria-hidden="true"
      />
    )}
    {state === 'update' && (
      <>
        <div
          className="rabbit-build-sprite rabbit-build-grip rabbit-build-eye-left"
          aria-hidden="true"
        />
        <div
          className="rabbit-build-sprite rabbit-build-grip rabbit-build-eye-right"
          aria-hidden="true"
        />
      </>
    )}
  </div>
);

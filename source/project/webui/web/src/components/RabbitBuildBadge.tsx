import { useId, useState, type ReactNode } from 'react';
import { Menu, MenuItem, useMediaQuery } from '@mui/material';

import { useTranslation } from '@/hooks/useTranslation';

import './RabbitBuildBadge.css';

export type RabbitBuildState = 'off' | 'idle' | 'update' | 'unknown';

export const RabbitBuildBadge = ({
  state,
  children,
}: {
  state: RabbitBuildState;
  children: ReactNode;
}) => {
  const { t } = useTranslation();
  const [anchor, setAnchor] = useState<HTMLButtonElement | null>(null);
  const triggerId = useId();
  const menuId = useId();
  const visible = state !== 'unknown';
  const compact = useMediaQuery('(max-width:599.95px), (max-height:600px)');
  const available = visible && !compact;
  const sprite =
    state === 'update'
      ? 'rabbit-build-grip rabbit-build-back'
      : state === 'idle'
        ? 'rabbit-build-idle'
        : 'rabbit-build-off';
  if (!available && anchor) setAnchor(null);
  return (
    <div className="rabbit-build-stage" data-state={state}>
      <div className="rabbit-build-native">{children}</div>
      {visible && (
        <button
          type="button"
          id={triggerId}
          className={`rabbit-build-sprite rabbit-build-video-trigger ${sprite}`}
          aria-label={t('rabbit_videos.open')}
          aria-haspopup="menu"
          aria-expanded={Boolean(anchor)}
          aria-controls={anchor ? menuId : undefined}
          onClick={(event) => setAnchor(event.currentTarget)}
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
      <Menu
        id={menuId}
        anchorEl={anchor}
        open={Boolean(anchor) && available}
        onClose={() => setAnchor(null)}
        slotProps={{ list: { 'aria-label': t('rabbit_videos.open') } }}
      >
        <MenuItem
          component="a"
          href="https://youtu.be/LXj9dgPvnv4"
          target="_blank"
          rel="noopener noreferrer"
          onClick={() => setAnchor(null)}
        >
          MAKOSH — Заебало
        </MenuItem>
        <MenuItem
          component="a"
          href="https://youtu.be/QYr32Sgwtxk"
          target="_blank"
          rel="noopener noreferrer"
          onClick={() => setAnchor(null)}
        >
          Я один гуляю — Opera Experimental Version
        </MenuItem>
      </Menu>
    </div>
  );
};

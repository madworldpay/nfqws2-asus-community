import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { Menu, MenuItem, useMediaQuery } from '@mui/material';

import { useTranslation } from '@/hooks/useTranslation';

import './RabbitBuildBadge.css';

export type RabbitBuildState = 'off' | 'idle' | 'update' | 'unknown';

export const RabbitBuildBadge = ({
  state,
  serviceOff,
  confirmServiceOff,
  children,
}: {
  state: RabbitBuildState;
  serviceOff: boolean;
  confirmServiceOff: () => Promise<boolean>;
  children: ReactNode;
}) => {
  const { t } = useTranslation();
  const [anchor, setAnchor] = useState<HTMLButtonElement | null>(null);
  const triggerId = useId();
  const menuId = useId();
  const visible = state !== 'unknown';
  const compact = useMediaQuery('(max-width:599.95px), (max-height:600px)');
  const available = state === 'off' && serviceOff && !compact;
  const availableRef = useRef(available);
  availableRef.current = available;
  const request = useRef(0);
  const expires = useRef(0);
  const close = useCallback(() => {
    request.current++;
    expires.current = 0;
    setAnchor(null);
  }, []);
  useEffect(() => {
    if (!available) close();
  }, [available, close]);
  useEffect(
    () => () => {
      request.current++;
    },
    [],
  );
  useEffect(() => {
    if (!anchor) return;
    const timer = window.setTimeout(
      close,
      Math.max(0, expires.current - Date.now()),
    );
    return () => window.clearTimeout(timer);
  }, [anchor, close]);
  useEffect(() => {
    const hidden = () => {
      if (document.visibilityState !== 'visible') close();
    };
    document.addEventListener('visibilitychange', hidden);
    return () => document.removeEventListener('visibilitychange', hidden);
  }, [close]);
  const sprite =
    state === 'update'
      ? 'rabbit-build-grip rabbit-build-back'
      : state === 'idle'
        ? 'rabbit-build-idle'
        : 'rabbit-build-off';
  return (
    <div className="rabbit-build-stage" data-state={state}>
      <div className="rabbit-build-native">{children}</div>
      {visible && (
        <button
          type="button"
          id={triggerId}
          className={`rabbit-build-sprite rabbit-build-video-trigger ${sprite}`}
          aria-label={available ? t('rabbit_videos.open') : undefined}
          aria-hidden={!available || undefined}
          aria-haspopup={available ? 'menu' : undefined}
          aria-expanded={available ? Boolean(anchor) : undefined}
          aria-controls={available && anchor ? menuId : undefined}
          disabled={!available}
          onClick={async (event) => {
            const button = event.currentTarget;
            const id = ++request.current;
            setAnchor(null);
            try {
              const confirmed = await confirmServiceOff();
              if (
                confirmed &&
                request.current === id &&
                availableRef.current &&
                button.isConnected &&
                document.visibilityState === 'visible'
              ) {
                expires.current = Date.now() + 30_000;
                setAnchor(button);
              }
            } catch {
              if (request.current === id) close();
            }
          }}
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
        onClose={close}
        slotProps={{ list: { 'aria-label': t('rabbit_videos.open') } }}
      >
        {available && (
          <MenuItem
            component="a"
            href="https://youtu.be/QYr32Sgwtxk"
            target="_blank"
            rel="noopener noreferrer"
            onClick={(event) => {
              if (!availableRef.current || Date.now() >= expires.current)
                event.preventDefault();
              close();
            }}
          >
            Я один гуляю — Opera
          </MenuItem>
        )}
      </Menu>
    </div>
  );
};

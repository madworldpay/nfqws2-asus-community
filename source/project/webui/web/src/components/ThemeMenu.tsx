import { Menu, MenuItem, useColorScheme } from '@mui/material';

import { useAppearanceStore } from '@/store/useAppearanceStore';

import { useTranslation } from '@/hooks/useTranslation';

export const ThemeMenu = ({
  anchorEl,
  onClose,
}: {
  anchorEl: HTMLElement | null;
  onClose: () => void;
}) => {
  const { t } = useTranslation();
  const { mode, setMode } = useColorScheme();
  const { appearance, setAppearance } = useAppearanceStore();
  return (
    <Menu anchorEl={anchorEl} open={Boolean(anchorEl)} onClose={onClose}>
      <MenuItem
        selected={appearance === 'classic' && mode === 'light'}
        onClick={() => {
          setAppearance('classic');
          setMode('light');
          onClose();
        }}
      >
        {t('system.theme_classic_light')}
      </MenuItem>
      <MenuItem
        selected={appearance === 'classic' && mode === 'dark'}
        onClick={() => {
          setAppearance('classic');
          setMode('dark');
          onClose();
        }}
      >
        {t('system.theme_classic_dark')}
      </MenuItem>
      <MenuItem
        selected={appearance === 'rabbit'}
        onClick={() => {
          setAppearance('rabbit');
          setMode('dark');
          onClose();
        }}
      >
        {t('system.theme_rabbit')}
      </MenuItem>
    </Menu>
  );
};

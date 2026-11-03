import PaletteOutlinedIcon from '@mui/icons-material/PaletteOutlined';
import { IconButton, Tooltip, useColorScheme } from '@mui/material';

import { useAppearanceStore } from '@/store/useAppearanceStore';

import { useTranslation } from '@/hooks/useTranslation';

export const ThemeCycleButton = () => {
  const { t } = useTranslation();
  const { mode, systemMode, setMode } = useColorScheme();
  const { appearance, setAppearance } = useAppearanceStore();
  const current =
    appearance === 'rabbit'
      ? 'rabbit'
      : (mode === 'system' ? systemMode : mode) === 'light'
        ? 'light'
        : 'dark';
  const next =
    current === 'light' ? 'dark' : current === 'dark' ? 'rabbit' : 'light';
  const names = {
    light: t('system.theme_classic_light'),
    dark: t('system.theme_classic_dark'),
    rabbit: t('system.theme_rabbit'),
  };
  return (
    <Tooltip title={`${names[current]} → ${names[next]}`} enterTouchDelay={0}>
      <IconButton
        size="small"
        aria-label={t('system.change_theme')}
        data-current-theme={current}
        onClick={() => {
          setAppearance(next === 'rabbit' ? 'rabbit' : 'classic');
          setMode(next === 'light' ? 'light' : 'dark');
        }}
        sx={{ width: 36, height: 36 }}
      >
        <PaletteOutlinedIcon fontSize="small" />
      </IconButton>
    </Tooltip>
  );
};

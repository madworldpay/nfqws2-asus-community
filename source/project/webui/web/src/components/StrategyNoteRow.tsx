import type { ReactNode } from 'react';
import { Box } from '@mui/material';

import { useTranslation } from '@/hooks/useTranslation';

export function StrategyNoteRow({
  children,
  title,
  number,
  value,
  onChange,
  onEdit,
}: {
  children: ReactNode;
  title: string;
  number: string;
  value: string;
  onChange: (id: string, text: string) => void;
  onEdit: (id: string | null) => void;
}) {
  const { t } = useTranslation();
  return (
    <Box
      component="li"
      sx={{
        display: 'grid',
        gridTemplateColumns: 'minmax(0, 3fr) minmax(0, 2fr)',
        gap: { xs: 0.5, sm: 1.5 },
        alignItems: 'center',
        pr: 0.5,
        '& > button': { minWidth: 0, overflowWrap: 'anywhere' },
      }}
    >
      {children}
      <Box
        component="textarea"
        rows={2}
        aria-label={t('import.notes.label') + ' — ' + title}
        placeholder={t('import.notes.label')}
        value={value}
        onFocus={() => onEdit(number)}
        onBlur={() => onEdit(null)}
        onChange={(event) => onChange(number, event.target.value)}
        sx={{
          boxSizing: 'border-box',
          width: '100%',
          minWidth: 0,
          my: 0.5,
          px: 1,
          py: 0.5,
          resize: 'vertical',
          font: 'inherit',
          typography: 'body2',
          color: 'text.primary',
          bgcolor: 'background.paper',
          border: 1,
          borderColor: 'divider',
          borderRadius: 1,
          '&:focus-visible': {
            outline: '2px solid',
            outlineColor: 'primary.main',
          },
        }}
      />
    </Box>
  );
}

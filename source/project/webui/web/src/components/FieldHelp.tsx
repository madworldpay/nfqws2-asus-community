import type { ReactNode } from 'react';
import { Stack, Typography } from '@mui/material';

import { InlineHelp } from '@/components/InlineHelp';

/** Keep field-specific help beside the control, including on small screens. */
export const FieldHelp = ({
  title,
  hint,
  children,
}: {
  title: string;
  hint: string;
  children: ReactNode;
}) => (
  <Stack
    direction="row"
    alignItems="center"
    sx={{ flex: 1, minWidth: 0, '& > :first-child': { flex: 1, minWidth: 0 } }}
  >
    {children}
    <InlineHelp title={title}>
      <Typography>{hint}</Typography>
    </InlineHelp>
  </Stack>
);

import { useState, type ReactNode } from 'react';
import { Chip, Stack, Tooltip } from '@mui/material';
import type { SxProps } from '@mui/system/styleFunctionSx';

import { packageUpdateBadges } from '@/api/packageUpdates';

import { PackageUpdateDialog } from '@/components/PackageUpdateDialog';

import { usePackageUpdates } from '@/hooks/usePackageUpdates';
import { useStatus } from '@/hooks/useStatus';
import { useTranslation } from '@/hooks/useTranslation';

import { formatPackageVersion } from '@/utils/packageVersion';

export const CurrentVersion = ({ sx }: { sx?: SxProps }) => {
  const {
    packageVersion,
    buildNumber,
    webVersion,
    csrfToken,
    anonym,
    authenticated,
  } = useStatus();
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const updates = usePackageUpdates(csrfToken, anonym || authenticated, open);
  const web = webVersion?.join('.') ?? '0.0.0';
  const badges = packageUpdateBadges(
    updates.data?.check,
    packageVersion,
    web,
    buildNumber,
  );
  const badge = (label: ReactNode, available: boolean) => (
    <Tooltip
      key={String(label)}
      title={t(
        available ? 'package_update.badge_available' : 'package_update.check',
      )}
      enterTouchDelay={0}
    >
      <Chip
        label={label}
        size="small"
        variant="outlined"
        color={available ? 'warning' : 'primary'}
        onClick={() => setOpen(true)}
        sx={{ cursor: 'pointer' }}
      />
    </Tooltip>
  );
  return (
    <>
      <Stack
        direction="row"
        spacing={0.7}
        useFlexGap
        flexWrap="wrap"
        sx={{ fontSize: 14, lineHeight: 1, ...sx }}
      >
        {packageVersion &&
          badge(
            formatPackageVersion(packageVersion),
            badges.core || badges.web || badges.build,
          )}
      </Stack>
      <PackageUpdateDialog
        open={open}
        onClose={() => setOpen(false)}
        updates={updates}
        installed={packageVersion}
      />
    </>
  );
};

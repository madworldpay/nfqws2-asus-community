import FileDownloadOutlinedIcon from '@mui/icons-material/FileDownloadOutlined';
import FileUploadOutlinedIcon from '@mui/icons-material/FileUploadOutlined';
import { Box, Button, Stack, Tooltip } from '@mui/material';

import { useTranslation } from '@/hooks/useTranslation';

export const CommunityActions = ({
  onShare,
  onImport,
  importDisabled = false,
}: {
  onShare: VoidFunction;
  onImport: VoidFunction;
  importDisabled?: boolean;
}) => {
  const { t } = useTranslation();
  const buttonStyle = {
    minWidth: 0,
    height: 34,
    px: 0.7,
    gap: 0.5,
    borderColor: 'divider',
    '&.Mui-disabled img': { opacity: 0.55 },
  };
  const artwork = (src: string) => (
    <Box
      component="img"
      src={src}
      alt=""
      aria-hidden="true"
      draggable={false}
      width={28}
      height={28}
      sx={{ display: 'block', objectFit: 'contain', borderRadius: '50%' }}
    />
  );
  return (
    <Stack direction="row" spacing={0.75} alignItems="center">
      <Tooltip title={t('community.export_help')} enterTouchDelay={0}>
        <Button
          variant="outlined"
          size="small"
          aria-label={t('community.export')}
          onClick={onShare}
          sx={buttonStyle}
        >
          {artwork('/community/export-e9a226cd.png')}
          <FileUploadOutlinedIcon fontSize="small" />
        </Button>
      </Tooltip>
      <Tooltip
        title={t(
          importDisabled ? 'import.save_first' : 'community.import_help',
        )}
        enterTouchDelay={0}
      >
        <span tabIndex={0}>
          <Button
            variant="outlined"
            size="small"
            disabled={importDisabled}
            onClick={onImport}
            aria-label={t('community.import')}
            sx={buttonStyle}
          >
            <FileDownloadOutlinedIcon fontSize="small" />
            {artwork('/community/import-937c2946.png')}
          </Button>
        </span>
      </Tooltip>
    </Stack>
  );
};

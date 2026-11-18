import { Button, Stack, Typography } from '@mui/material';

import type { ImportDocument } from '@/api/importClient';
import {
  downloadContribution,
  resourceBytes,
  type ResourceCopy,
} from '@/api/shareResourcesClient';

import { FrankShareButton } from '@/components/ShareDialog';

import { useTranslation } from '@/hooks/useTranslation';

/** Render reviewed copies as text; Lua and configuration are never evaluated. */
export const ShareResourcesPreview = ({ text }: { text: string }) => {
  const { t } = useTranslation();
  const payload = JSON.parse(text) as {
    files: ResourceCopy[];
    package_files?: ImportDocument['package_files'];
    audit: unknown;
  };
  return (
    <Stack spacing={2}>
      {!!payload.package_files?.length && (
        <Typography>
          {t('share.package_files')}:{' '}
          {payload.package_files.map((f) => f.name).join(', ')}
        </Typography>
      )}
      {!!payload.files.length && (
        <Typography>{t('share.embedded_files')}</Typography>
      )}
      {payload.files.map((file) => {
        const bytes = resourceBytes(file);
        return (
          <Stack key={file.id} spacing={1}>
            <Typography sx={{ overflowWrap: 'anywhere' }}>
              {file.kind}/{file.name} · {bytes.length} B
            </Typography>
            <Typography variant="caption" sx={{ overflowWrap: 'anywhere' }}>
              SHA-256: {file.sha256}
            </Typography>
            {file.encoding === 'utf8' ? (
              <Typography
                component="pre"
                sx={{
                  whiteSpace: 'pre-wrap',
                  overflowWrap: 'anywhere',
                  fontSize: 12,
                  maxHeight: 320,
                  overflow: 'auto',
                }}
              >
                {new TextDecoder('utf-8', { fatal: true }).decode(bytes)}
              </Typography>
            ) : (
              <Typography variant="body2">{t('share.blob_exact')}</Typography>
            )}
            <Button
              onClick={() =>
                downloadContribution(
                  new Blob([bytes], { type: 'application/octet-stream' }),
                  file.name,
                )
              }
            >
              {t('share.download_copy')}
            </Button>
            <FrankShareButton
              load={() => ({
                blob: new Blob([bytes], { type: 'application/octet-stream' }),
                filename: file.name,
              })}
            />
          </Stack>
        );
      })}
      <Typography
        component="pre"
        sx={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', fontSize: 12 }}
      >
        {JSON.stringify(payload.audit, null, 2)}
      </Typography>
    </Stack>
  );
};

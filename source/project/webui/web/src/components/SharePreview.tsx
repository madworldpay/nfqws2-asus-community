import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Stack,
  Typography,
} from '@mui/material';

import type { PreparedShare } from '@/api/shareClient';

import { ShareResourcesPreview } from '@/components/ShareResourcesPreview';

import { useTranslation } from '@/hooks/useTranslation';

export const SharePreview = ({ snapshot }: { snapshot: PreparedShare }) => {
  const { t } = useTranslation();
  return (
    <Stack spacing={1}>
      <Alert severity="info">{t('share.preview_hint')}</Alert>
      {snapshot.source && (
        <Accordion>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            {t('share.source')}
          </AccordionSummary>
          <AccordionDetails>
            <Typography
              component="pre"
              sx={{
                whiteSpace: 'pre-wrap',
                overflowWrap: 'anywhere',
                fontSize: 12,
              }}
            >
              {JSON.stringify(snapshot.source, null, 2)}
            </Typography>
          </AccordionDetails>
        </Accordion>
      )}
      {snapshot.files.map((file) => (
        <Accordion key={file.type}>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Typography sx={{ overflowWrap: 'anywhere' }}>
              {t(`share.kinds.${file.type}`)} · {file.blob.size} B
            </Typography>
          </AccordionSummary>
          <AccordionDetails>
            <Typography variant="caption" sx={{ overflowWrap: 'anywhere' }}>
              {file.filename}
            </Typography>
            {!file.complete && (
              <Alert severity="info">{t('share.partial')}</Alert>
            )}
            {file.type === 'resources' ? (
              <ShareResourcesPreview text={file.text} />
            ) : (
              <Typography
                component="pre"
                sx={{
                  whiteSpace: 'pre-wrap',
                  overflowWrap: 'anywhere',
                  fontSize: 12,
                  maxHeight: 450,
                  overflow: 'auto',
                }}
              >
                {file.text}
              </Typography>
            )}
          </AccordionDetails>
        </Accordion>
      ))}
    </Stack>
  );
};

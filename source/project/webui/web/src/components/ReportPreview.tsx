import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableRow,
  Typography,
} from '@mui/material';

import type { SupportReportPreview } from '@/api/supportReport';

import { useTranslation } from '@/hooks/useTranslation';

export const ReportPreview = ({
  preview,
}: {
  preview: SupportReportPreview;
}) => {
  const { t } = useTranslation();
  return (
    <Stack spacing={1}>
      <Typography variant="body2">
        {t('report.preview_meta', {
          model: preview.model,
          time: preview.capturedAt,
          bytes: preview.bytes,
        })}
      </Typography>
      <Table size="small" aria-label={t('report.section_summary')}>
        <TableBody>
          {preview.sections.map((section) => (
            <TableRow key={section.name}>
              <TableCell>{t(`report.sections.${section.name}`)}</TableCell>
              <TableCell align="right">
                {t(`report.source_states.${section.state}`)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <Typography variant="caption">{t('report.section_hint')}</Typography>
      <Accordion disableGutters>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography>{t('report.view_json')}</Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Typography
            component="pre"
            sx={{
              fontSize: 12,
              whiteSpace: 'pre-wrap',
              overflowWrap: 'anywhere',
              maxHeight: 320,
              overflow: 'auto',
              m: 0,
            }}
          >
            {preview.text}
          </Typography>
        </AccordionDetails>
      </Accordion>
    </Stack>
  );
};

import type { TranslationKey } from '@/context/TranslationProvider';
import en from '@/translations/en.json';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Stack,
  Typography,
} from '@mui/material';

import type { ImportPlan } from '@/api/importClient';

import { useTranslation } from '@/hooks/useTranslation';

export const ImportPreview = ({ plan }: { plan: ImportPlan }) => {
  const { t } = useTranslation();
  const text = (v: unknown) => (
    <Typography
      component="pre"
      sx={{
        whiteSpace: 'pre-wrap',
        overflowWrap: 'anywhere',
        fontSize: 12,
        maxHeight: 360,
        overflow: 'auto',
      }}
    >
      {typeof v === 'string' ? v : JSON.stringify(v, null, 2)}
    </Typography>
  );
  return (
    <Stack spacing={1}>
      <Alert severity={plan.ready ? 'success' : 'info'}>
        {t(plan.ready ? 'import.ready' : 'import.needs_choice')}
      </Alert>
      {plan.problems.map((p, i) => (
        <Alert severity="info" key={i}>
          {Object.prototype.hasOwnProperty.call(en.import.problems, p.code)
            ? t(`import.problems.${p.code}` as TranslationKey)
            : t('import.error')}{' '}
          {p.code === 'unresolved_file'
            ? p.name || p.alias || p.field || p.key || p.id || ''
            : p.key || p.name || p.field || p.alias || p.id || ''}
        </Alert>
      ))}
      {!!plan.affected_blocks.length && (
        <Alert severity="info">
          {t('import.affected')}: {plan.affected_blocks.join(', ')}
        </Alert>
      )}
      {plan.files.some((file) => file.replace) && (
        <Alert severity="info">
          {t('import.replace_files')}:{' '}
          {plan.files.filter((file) => file.replace).length}.{' '}
          {t('import.replace_backup')}
        </Alert>
      )}
      {plan.warnings.map((warning, index) => (
        <Alert severity="info" key={index}>
          {t(
            warning.kind === 'lua_dependencies_unchecked'
              ? 'import.lua_warning'
              : 'import.analysis_warning',
          )}{' '}
          {warning.source} {warning.name ?? ''}
        </Alert>
      ))}
      {plan.changes.map((c) => (
        <Accordion key={c.key}>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            {Object.prototype.hasOwnProperty.call(en.form, c.key)
              ? t(`form.${c.key}` as TranslationKey)
              : c.key}
          </AccordionSummary>
          <AccordionDetails>
            <Typography variant="caption">{t('import.before')}</Typography>
            {text(c.before ?? '')}
            <Typography variant="caption">{t('import.after')}</Typography>
            {text(c.after)}
          </AccordionDetails>
        </Accordion>
      ))}
      {plan.files.length > 0 && (
        <Accordion>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            {t('import.files')} · {plan.files.length}
          </AccordionSummary>
          <AccordionDetails>
            {plan.files.map((f) => (
              <Typography
                key={f.id}
                variant="body2"
                sx={{ overflowWrap: 'anywhere' }}
              >
                {t(
                  f.reuse
                    ? 'import.reuse'
                    : f.replace
                      ? 'import.replace_file'
                      : 'import.new_file',
                )}
                : {f.path} · {f.byte_length} B · SHA256 {f.sha256}
              </Typography>
            ))}
          </AccordionDetails>
        </Accordion>
      )}
      {plan.draft && (
        <Accordion>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            {t('import.dns_preview')}
          </AccordionSummary>
          <AccordionDetails>
            <Typography variant="caption">{t('import.before')}</Typography>
            {text(plan.old_draft)}
            <Typography variant="caption">{t('import.after')}</Typography>
            {text(plan.draft)}
          </AccordionDetails>
        </Accordion>
      )}
    </Stack>
  );
};

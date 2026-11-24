import type { TranslationKey } from '@/context/TranslationProvider';
import en from '@/translations/en.json';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Checkbox,
  FormControlLabel,
  Stack,
  Typography,
} from '@mui/material';

import type { ImportPlan } from '@/api/importClient';
import { STRATEGY_KEYS, type StrategyKey } from '@/api/shareClient';

import { useTranslation } from '@/hooks/useTranslation';

export const ImportPreview = ({
  plan,
  luaTrust,
}: {
  plan: ImportPlan;
  luaTrust?: {
    checked: boolean;
    disabled: boolean;
    onChange: (checked: boolean) => void;
  };
}) => {
  const { t } = useTranslation();
  const strategyChanges = plan.changes.filter(
    ({ key, before, after }) =>
      before !== after && STRATEGY_KEYS.includes(key as StrategyKey),
  );
  const openComparison =
    strategyChanges.find(({ key }) => key === 'NFQWS_ARGS_CUSTOM') ??
    strategyChanges[0];
  const needsLuaTrust = plan.problems.some(({ code }) => code === 'lua_trust');
  const showLuaTrust =
    needsLuaTrust ||
    (luaTrust?.checked &&
      plan.warnings.some(({ kind }) => kind === 'lua_dependencies_unchecked'));
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
        {t(
          plan.ready
            ? 'import.ready'
            : needsLuaTrust && plan.problems.length === 1
              ? 'import.problems.lua_trust'
              : 'import.needs_choice',
        )}
      </Alert>
      {plan.kept_auto_list && (
        <Typography variant="body2">{t('import.kept_auto_list')}</Typography>
      )}
      {plan.problems
        .filter(({ code }) => code !== 'lua_trust' || plan.problems.length > 1)
        .map((p, i) => (
          <Alert severity="info" key={i}>
            {Object.prototype.hasOwnProperty.call(en.import.problems, p.code)
              ? t(`import.problems.${p.code}` as TranslationKey)
              : t('import.error')}{' '}
            {p.code === 'unresolved_file'
              ? p.name || p.alias || p.field || p.key || p.id || ''
              : p.key || p.name || p.field || p.alias || p.id || ''}
          </Alert>
        ))}
      {luaTrust && showLuaTrust && (
        <FormControlLabel
          control={
            <Checkbox
              checked={luaTrust.checked}
              disabled={luaTrust.disabled}
              onChange={(_, checked) => luaTrust.onChange(checked)}
            />
          }
          label={t('import.trust_lua')}
        />
      )}
      {plan.problems.some((p) => p.code === 'unresolved_file') && (
        <Alert severity="info" sx={{ overflowWrap: 'anywhere' }}>
          {t('import.keenetic.missing_files')}
        </Alert>
      )}
      {plan.torrent_sites && (
        <Stack spacing={0.5}>
          <Typography variant="subtitle2">
            {t('import.torrent_sites.preview')}
          </Typography>
          <Typography variant="body2">
            {plan.torrent_sites.sites.join(', ')}
          </Typography>
          {text(plan.torrent_sites.block)}
        </Stack>
      )}
      {!!plan.addons?.length && (
        <Stack spacing={1}>
          <Typography variant="subtitle2">
            {t('import.addons.preview')}
          </Typography>
          {plan.addons.map((addon) => (
            <Stack
              key={addon.id}
              spacing={0.5}
              sx={{ overflowWrap: 'anywhere' }}
            >
              <Typography variant="subtitle2">{addon.title}</Typography>
              <Typography variant="body2">
                {t(`import.addons.${addon.action}`)}
              </Typography>
              {!!addon.domains.length && (
                <>
                  <Typography variant="caption">
                    {t('import.addons.domains')}
                  </Typography>
                  <Typography variant="body2">
                    {addon.domains.join(', ')}
                  </Typography>
                </>
              )}
              {!!addon.note && (
                <Typography variant="body2">{addon.note}</Typography>
              )}
            </Stack>
          ))}
        </Stack>
      )}
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
          {warning.kind === 'inventory_partial' ? (
            t('import.inventory_warning')
          ) : (
            <>
              {t(
                warning.kind === 'lua_dependencies_unchecked'
                  ? 'import.lua_warning'
                  : 'import.analysis_warning',
              )}{' '}
              {warning.source} {warning.name ?? ''}
            </>
          )}
        </Alert>
      ))}
      {plan.changes.map((c) => (
        <Accordion key={c.key} defaultExpanded={c === openComparison}>
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

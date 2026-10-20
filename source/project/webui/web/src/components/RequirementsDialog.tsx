import { useEffect, useState } from 'react';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Link,
  Stack,
  Typography,
} from '@mui/material';

import { getStrategyDraft } from '@/api/shareClient';
import {
  getSmartDnsConfigStatus,
  type Checkup,
  type ConfigView,
} from '@/api/smartDnsConfigClient';
import { startProgress } from '@/api/startProgress';

import { InlineHelp } from '@/components/InlineHelp';
import { RouterCheckup } from '@/components/RouterCheckup';

import { useAppStore } from '@/store/useAppStore';

import { useStatus } from '@/hooks/useStatus';
import { useTranslation } from '@/hooks/useTranslation';

export const RequirementsDialog = ({
  onClose,
  onOpenSmartDns,
  onOpenArk,
}: {
  onClose: VoidFunction;
  onOpenSmartDns?: VoidFunction;
  onOpenArk?: VoidFunction;
}) => {
  const { t } = useTranslation();
  const { csrfToken } = useStatus();
  const dirty = useAppStore((s) => s.needSave);
  const pendingRestart = useAppStore((s) => s.needReload);
  const [checkup, setCheckup] = useState<Checkup>();
  const [dns, setDns] = useState<ConfigView>();
  const [hasStrategy, setHasStrategy] = useState<boolean>();
  useEffect(() => {
    if (!csrfToken || !checkup) return;
    let active = true;
    void getStrategyDraft(csrfToken)
      .then((draft) => {
        if (active)
          setHasStrategy(draft.blocks.some((block) => block.value.trim()));
      })
      .catch(() => {});
    void getSmartDnsConfigStatus(csrfToken)
      .then((value) => {
        if (active) setDns(value);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [csrfToken, checkup]);
  const progress = startProgress({
    checkup,
    dns,
    hasStrategy,
    dirty,
    pendingRestart,
  });
  return (
    <Dialog open maxWidth="sm" fullWidth onClose={onClose}>
      <DialogTitle>{t('requirements.title')}</DialogTitle>
      <DialogContent>
        <Typography variant="body2">{t('requirements.intro')}</Typography>
        {csrfToken && (
          <RouterCheckup
            csrf={csrfToken}
            onOpenSmartDns={onOpenSmartDns}
            onResult={setCheckup}
          />
        )}
        {onOpenArk && (
          <Button onClick={onOpenArk}>{t('requirements.open_ark')}</Button>
        )}
        <Stack direction="row" alignItems="center" spacing={1}>
          <Typography variant="subtitle2">
            {t('requirements.progress.title')}
          </Typography>
          <InlineHelp title={t('requirements.progress.title')}>
            <Typography>{t('requirements.progress.explanation')}</Typography>
          </InlineHelp>
        </Stack>
        <Stack component="ol" spacing={2} sx={{ pl: 3, mb: 3 }}>
          {progress.map(({ id, state }) => (
            <Typography component="li" variant="body2" key={id}>
              <Stack
                direction="row"
                alignItems="center"
                spacing={1}
                useFlexGap
                flexWrap="wrap"
              >
                <Typography variant="subtitle2">
                  {t(`requirements.progress.steps.${id}`)}
                </Typography>
                <Chip
                  size="small"
                  variant="outlined"
                  color={
                    state === 'done'
                      ? 'success'
                      : state === 'partial'
                        ? 'warning'
                        : 'default'
                  }
                  label={t(`requirements.progress.states.${state}`)}
                />
              </Stack>
              {t(`requirements.quick.${id}`)}
            </Typography>
          ))}
        </Stack>
        <Typography variant="body2" sx={{ mb: 2 }}>
          {t('requirements.quick.recover')}
        </Typography>
        <Accordion disableGutters sx={{ mb: 3 }}>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Typography variant="body2">{t('requirements.details')}</Typography>
          </AccordionSummary>
          <AccordionDetails>
            <Stack spacing={2}>
              {(
                [
                  'platform',
                  'storage',
                  'dns',
                  'transit',
                  'ark',
                  'traffic',
                  'verify',
                  'updates',
                ] as const
              ).map((item) => (
                <Typography variant="body2" key={item}>
                  {t(`requirements.items.${item}`)}
                </Typography>
              ))}
            </Stack>
          </AccordionDetails>
        </Accordion>
        <Typography variant="body2">{t('requirements.sources')}:</Typography>
        <Stack spacing={1}>
          <Link
            href="https://github.com/madworldpay/nfqws2-asus-community#readme"
            target="_blank"
            rel="noreferrer"
          >
            NFQWS2 ASUS Community
          </Link>
          <Link
            href="https://www.asuswrt-merlin.net/download"
            target="_blank"
            rel="noreferrer"
          >
            Asuswrt-Merlin
          </Link>
          <Link
            href="https://github.com/nfqws/nfqws2-keenetic#подготовка-keeneticnetcraze"
            target="_blank"
            rel="noreferrer"
          >
            NFQWS2
          </Link>
          <Link
            href="https://www.asus.com/support/faq/1045253/"
            target="_blank"
            rel="noreferrer"
          >
            ASUS DNS
          </Link>
          <Link
            href="https://github.com/RMerl/asuswrt-merlin.ng/wiki/DNS-Director"
            target="_blank"
            rel="noreferrer"
          >
            Merlin DNS Director
          </Link>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.close')}</Button>
      </DialogActions>
    </Dialog>
  );
};

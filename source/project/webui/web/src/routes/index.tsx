import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
} from 'react';
import { useConfig } from '@/config/useConfig';
import {
  Alert,
  Box,
  Button,
  Checkbox,
  FormControl,
  FormControlLabel,
  FormGroup,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography,
  type SelectChangeEvent,
} from '@mui/material';
import { createFileRoute } from '@tanstack/react-router';

import { API } from '@/api/client';

import { App } from '@/components/App';
import { Error404 } from '@/components/Error404';
import { FormEditor } from '@/components/FormEditor';
import { RouterTrafficHelp } from '@/components/RouterTrafficHelp';
import { RouterWanInfo } from '@/components/RouterWanInfo';

import { useAppStore } from '@/store/useAppStore';

import { useStatus } from '@/hooks/useStatus';
import { useTranslation } from '@/hooks/useTranslation';

import {
  changedConfigKeys,
  formatConfig,
  parseConfig,
  resetStrategyConfig,
  type NfqwsConfig,
} from '@/utils/configParser';

export const Route = createFileRoute('/')({
  component: RouteComponent,
  notFoundComponent: Error404,
});

function RouteComponent() {
  const { nfqws2 } = useStatus();
  const { confFile } = useConfig(nfqws2);
  const { auth } = useAppStore();
  const { data: originalConfig, isPending } = API.fileContent(confFile, auth);
  const { data: defaultConfig, isPending: defaultsPending } = API.fileContent(
    `${confFile}.notactive`,
    auth,
  );
  const { setNeedSave, needSave, setOnSave } = useAppStore();

  const { t } = useTranslation();

  const [originalConfigParsed, setOriginalConfigParsed] =
    useState<NfqwsConfig | null>(null);
  const [form, setForm] = useState<NfqwsConfig | null>(null);
  const [strategyBaseline, setStrategyBaseline] = useState<NfqwsConfig | null>(
    null,
  );
  const [strategyRevision, setStrategyRevision] = useState(0);
  const [resetError, setResetError] = useState(false);

  const originalConfigRef = useRef<string | null>(null);
  const formRef = useRef<NfqwsConfig | null>(null);
  const needSaveRef = useRef<boolean>(false);

  useEffect(() => {
    originalConfigRef.current = originalConfig?.content ?? null;
    formRef.current = form;
    needSaveRef.current = needSave;
  }, [originalConfig?.content, form, needSave]);

  const onSave = useCallback(async () => {
    if (!needSaveRef.current) {
      return;
    }

    const oc = originalConfigRef.current;
    const f = formRef.current;
    if (!oc || !f) {
      return;
    }

    const newConfig = formatConfig(
      oc,
      f,
      changedConfigKeys(parseConfig(oc), f),
    );
    if (oc !== newConfig) {
      const { data } = await API.saveFile(confFile, newConfig);
      if (data?.status === 0) {
        void API.invalidateFileContent(confFile);
        setNeedSave(false);
      } else {
        // TODO: error
      }
    }
  }, [confFile, setNeedSave]);

  useEffect(() => {
    if (originalConfig?.content) {
      const parsed = parseConfig(originalConfig.content);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setOriginalConfigParsed(parsed);
      setForm(parsed);
      formRef.current = parsed;
      setStrategyBaseline(null);
      setResetError(false);
    }
  }, [originalConfig?.content]);

  useEffect(() => {
    setNeedSave(false);
  }, [setNeedSave]);

  useEffect(() => {
    setOnSave(onSave);
  }, [onSave, setOnSave]);

  const changeHandler =
    (key: keyof NfqwsConfig, isCheckbox = false) =>
    (
      e:
        | ChangeEvent<HTMLTextAreaElement | HTMLInputElement>
        | SelectChangeEvent
        | string,
    ) => {
      let value: string | boolean;
      if (typeof e === 'string') {
        value = e;
      } else {
        const target = e.target as Omit<HTMLInputElement, 'checked'> & {
          checked?: boolean;
        };
        value = isCheckbox ? Boolean(target.checked) : target.value;
      }

      const previous = formRef.current;
      if (!previous || !originalConfigParsed) return;
      const next = { ...previous, [key]: value };
      formRef.current = next;
      setForm(next);
      setNeedSave(changedConfigKeys(originalConfigParsed, next).length > 0);
    };

  const resetStrategies = () => {
    if (!formRef.current || !originalConfigParsed) return;
    try {
      const next = resetStrategyConfig(
        formRef.current,
        defaultConfig?.content ?? '',
      );
      formRef.current = next;
      setForm(next);
      setStrategyBaseline(next);
      setStrategyRevision((revision) => revision + 1);
      setNeedSave(changedConfigKeys(originalConfigParsed, next).length > 0);
      setResetError(false);
    } catch {
      setResetError(true);
    }
  };

  if (isPending || !originalConfigParsed || !form) {
    return <App />;
  }

  return (
    <App>
      <Box
        flex={1}
        sx={{
          position: 'relative',
          display: 'flex',
          overflowY: 'auto',
        }}
      >
        <FormGroup
          sx={{
            px: 'max(15px, 1.6vh)',
            pt: 3,
            pb: 2,
            gap: 4,
            width: '100%',
            flex: 1,
            position: 'absolute',
            '& .MuiInputBase-root': {
              fontFamily: (theme) => theme.typography.mono.fontFamily,
              fontSize: 14,
            },
            '& .MuiInputBase-input': {
              fontFamily: (theme) => theme.typography.mono.fontFamily,
              fontSize: 13,
            },
            '& .MuiFormLabel-root': {
              fontSize: 13,
            },
            '& .MuiFormControlLabel-label': {
              fontSize: 14,
            },
            '& .MuiInputLabel-shrink': {
              transform: 'translate(14px, -9px) scale(0.95)',
            },
          }}
        >
          <Typography
            variant="subtitle1"
            component="h2"
            sx={{ borderBottom: 1, borderColor: 'divider', pb: 1 }}
          >
            {t('form.section_wan')}
          </Typography>
          <TextField
            id="ISP_INTERFACE"
            label={t('form.ISP_INTERFACE')}
            placeholder={t('form.ISP_INTERFACE_AUTO')}
            helperText={t('form.ISP_INTERFACE_HELP')}
            fullWidth
            value={form.ISP_INTERFACE}
            onChange={changeHandler('ISP_INTERFACE')}
            spellCheck={false}
          />

          {nfqws2 && (
            <>
              <Typography
                variant="subtitle1"
                component="h2"
                sx={{ borderBottom: 1, borderColor: 'divider', pb: 1 }}
              >
                {t('form.section_startup')}
              </Typography>
              <FormEditor
                label={t('form.NFQWS_BASE_ARGS')}
                value={originalConfigParsed.NFQWS_BASE_ARGS}
                onChange={changeHandler('NFQWS_BASE_ARGS')}
              />
            </>
          )}

          <Box sx={{ borderBottom: 1, borderColor: 'divider', pb: 1 }}>
            <Stack
              direction="row"
              alignItems="center"
              justifyContent="space-between"
              useFlexGap
              flexWrap="wrap"
              gap={1}
            >
              <Typography variant="subtitle1" component="h2">
                {t('form.section_strategies')}
              </Typography>
              <Button
                type="button"
                size="small"
                variant="outlined"
                disabled={!auth || defaultsPending}
                onClick={resetStrategies}
              >
                {t('form.strategy_default')}
              </Button>
            </Stack>
            <Typography variant="caption" color="text.secondary">
              {t('form.strategy_default_hint')}
            </Typography>
          </Box>
          {resetError && (
            <Alert severity="warning" role="alert">
              {t('form.strategy_default_unavailable')}
            </Alert>
          )}
          <FormEditor
            key={`tcp-${strategyRevision}`}
            label={t('form.NFQWS_ARGS')}
            value={(strategyBaseline ?? originalConfigParsed).NFQWS_ARGS}
            onChange={changeHandler('NFQWS_ARGS')}
          />

          <FormEditor
            key={`quic-${strategyRevision}`}
            label={t('form.NFQWS_ARGS_QUIC')}
            value={(strategyBaseline ?? originalConfigParsed).NFQWS_ARGS_QUIC}
            onChange={changeHandler('NFQWS_ARGS_QUIC')}
          />

          <FormEditor
            key={`udp-${strategyRevision}`}
            label={t('form.NFQWS_ARGS_UDP')}
            value={(strategyBaseline ?? originalConfigParsed).NFQWS_ARGS_UDP}
            onChange={changeHandler('NFQWS_ARGS_UDP')}
          />

          <FormEditor
            key={`custom-${strategyRevision}`}
            label={t('form.NFQWS_ARGS_CUSTOM')}
            value={(strategyBaseline ?? originalConfigParsed).NFQWS_ARGS_CUSTOM}
            onChange={changeHandler('NFQWS_ARGS_CUSTOM')}
          />

          <Typography
            variant="subtitle1"
            component="h2"
            sx={{ borderBottom: 1, borderColor: 'divider', pb: 1 }}
          >
            {t('form.section_scope')}
          </Typography>
          <FormEditor
            label={t('form.NFQWS_ARGS_IPSET')}
            value={originalConfigParsed.NFQWS_ARGS_IPSET}
            onChange={changeHandler('NFQWS_ARGS_IPSET')}
          />

          <FormControl fullWidth>
            <InputLabel>{t('form.NFQWS_EXTRA_ARGS')}</InputLabel>
            <Select
              id="NFQWS_EXTRA_ARGS"
              label={t('form.NFQWS_EXTRA_ARGS')}
              value={form.NFQWS_EXTRA_ARGS}
              fullWidth
              sx={{ minWidth: 120 }}
              onChange={changeHandler('NFQWS_EXTRA_ARGS')}
            >
              <MenuItem value="MODE_AUTO">Auto</MenuItem>
              <MenuItem value="MODE_LIST">List</MenuItem>
              <MenuItem value="MODE_ALL">All</MenuItem>
            </Select>
          </FormControl>
          <TextField
            id="TCP_PORTS"
            label={t('form.TCP_PORTS')}
            minRows={2}
            fullWidth
            value={form.TCP_PORTS}
            onChange={changeHandler('TCP_PORTS')}
            spellCheck={false}
          />
          <TextField
            id="UDP_PORTS"
            label={t('form.UDP_PORTS')}
            minRows={2}
            fullWidth
            value={form.UDP_PORTS}
            onChange={changeHandler('UDP_PORTS')}
            spellCheck={false}
          />
          <Typography
            variant="subtitle1"
            component="h2"
            sx={{ borderBottom: 1, borderColor: 'divider', pb: 1 }}
          >
            {t('form.section_clients')}
          </Typography>
          <FormControl fullWidth>
            <InputLabel id="asus-client-mode-label">
              {t('form.ASUS_CLIENT_MODE')}
            </InputLabel>
            <Select
              labelId="asus-client-mode-label"
              value={form.ASUS_CLIENT_MODE}
              label={t('form.ASUS_CLIENT_MODE')}
              onChange={changeHandler('ASUS_CLIENT_MODE')}
            >
              <MenuItem value="all">{t('form.ASUS_ALL')}</MenuItem>
              <MenuItem value="include">{t('form.ASUS_INCLUDE')}</MenuItem>
              <MenuItem value="exclude">{t('form.ASUS_EXCLUDE')}</MenuItem>
            </Select>
          </FormControl>
          <Box>
            <TextField
              id="ASUS_CLIENTS4"
              label={t('form.ASUS_CLIENTS4')}
              fullWidth
              value={form.ASUS_CLIENTS4}
              onChange={changeHandler('ASUS_CLIENTS4')}
              helperText={t('form.ASUS_CLIENT_HELP')}
              spellCheck={false}
            />
            <RouterWanInfo
              clients={form.ASUS_CLIENTS4}
              mode={form.ASUS_CLIENT_MODE}
              onChange={changeHandler('ASUS_CLIENTS4')}
            />
            <RouterTrafficHelp title={t('form.ASUS_CLIENT_SOURCE_TITLE')}>
              <Typography variant="caption" color="text.secondary">
                {t('form.ASUS_CLIENT_SOURCE_HELP')}
              </Typography>
            </RouterTrafficHelp>
          </Box>
          <TextField
            id="ASUS_CLIENTS6"
            label={t('form.ASUS_CLIENTS6')}
            fullWidth
            value={form.ASUS_CLIENTS6}
            onChange={changeHandler('ASUS_CLIENTS6')}
            helperText={t('form.ASUS_CLIENT_HELP')}
            spellCheck={false}
          />
          <FormControlLabel
            label={t('form.IPV6_ENABLED')}
            control={
              <Checkbox
                id="IPV6_ENABLED"
                checked={form.IPV6_ENABLED}
                onChange={changeHandler('IPV6_ENABLED', true)}
              />
            }
            sx={{ mt: '-1em' }}
          />
          <FormControlLabel
            label={t('form.LOG_LEVEL')}
            control={
              <Checkbox
                id="LOG_LEVEL"
                checked={form.LOG_LEVEL}
                onChange={changeHandler('LOG_LEVEL', true)}
              />
            }
            sx={{ mt: '-1em' }}
          />
        </FormGroup>
      </Box>
    </App>
  );
}

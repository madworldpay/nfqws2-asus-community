import ArticleOutlinedIcon from '@mui/icons-material/ArticleOutlined';
import DescriptionOutlinedIcon from '@mui/icons-material/DescriptionOutlined';
import DevicesOtherOutlinedIcon from '@mui/icons-material/DevicesOtherOutlined';
import DisplaySettingsIcon from '@mui/icons-material/DisplaySettings';
import DnsOutlinedIcon from '@mui/icons-material/DnsOutlined';
import ShieldOutlinedIcon from '@mui/icons-material/ShieldOutlined';
import TuneOutlinedIcon from '@mui/icons-material/TuneOutlined';
import { Box, Tab, Tabs } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useLocation, useNavigate, useParams } from '@tanstack/react-router';

import { panelApi } from '@/api/panelPaths.js';
import {
  smartDnsConfigQuery,
  smartDnsConnectionState,
} from '@/api/smartDnsConfigClient';

import { mainTabsValues, type MainTabsValues } from '@/types/types';

import { useStatus } from '@/hooks/useStatus';
import { useTranslation } from '@/hooks/useTranslation';

const deviceProfilesHref = '/device-profiles-lab/device-profiles-lab.html';

const strategyPickerHref = panelApi + '?strategy-picker=1';

export const MainTabs = () => {
  const navigate = useNavigate();
  const { pathname } = useLocation();

  const { t } = useTranslation();
  const { platform, isPending, csrfToken } = useStatus();

  const { tab } = useParams({ strict: false }) as {
    tab?: MainTabsValues;
  };

  const currentTab = /^\/smartdns\/?$/.test(pathname)
    ? 'smartdns'
    : /^\/ip-health\/?$/.test(pathname)
      ? 'ip-health'
      : !tab
        ? 'settings'
        : mainTabsValues.includes(tab)
          ? tab
          : false;

  const dns = useQuery({
    ...smartDnsConfigQuery(csrfToken ?? ''),
    enabled: !!csrfToken,
    refetchInterval: currentTab === 'smartdns' ? false : 30_000,
  });
  const dnsState = smartDnsConnectionState(dns.isError ? undefined : dns.data);

  return (
    <>
      <Box
        sx={{
          display: 'flex',
          alignItems: 'stretch',
          borderBottom: '1px solid',
          borderColor: 'divider',
        }}
      >
        <Tabs
          value={currentTab}
          onChange={(_, value) => {
            if (value === deviceProfilesHref || value === strategyPickerHref)
              return;
            void navigate({ to: value === 'settings' ? '/' : `/${value}` });
          }}
          variant="scrollable"
          scrollButtons="auto"
          sx={{
            minHeight: 50,
            flex: 1,
          }}
        >
          <Tab
            key="settings"
            value="settings"
            icon={<DisplaySettingsIcon fontSize="small" />}
            iconPosition="start"
            label={t('tabs.settings')}
            sx={{
              minHeight: '50px',
              fontSize: 14,
              transition: 'color 0.1s ease-in-out',
              '&.Mui-selected': {
                color: 'text.primary',
              },
              '&:hover': {
                color: 'text.primary',
              },
            }}
          />

          <Tab
            key="lists"
            value="lists"
            icon={<DescriptionOutlinedIcon fontSize="small" />}
            iconPosition="start"
            label={t('tabs.lists')}
            sx={{
              minHeight: '50px',
              fontSize: 14,
              transition: 'color 0.1s ease-in-out',
              '&.Mui-selected': {
                color: 'text.primary',
              },
              '&:hover': {
                color: 'text.primary',
              },
            }}
          />

          <Tab
            value="smartdns"
            icon={
              <DnsOutlinedIcon
                fontSize="small"
                color={
                  ['on', 'running', 'external'].includes(dnsState)
                    ? 'success'
                    : 'inherit'
                }
              />
            }
            iconPosition="start"
            label={`SmartDNS · ${t(`smartdns.connection_state.${dnsState}`)}`}
            sx={{ minHeight: 50, fontSize: 14 }}
          />

          {platform !== 'keenetic-entware' && (
            <Tab
              component="a"
              href={deviceProfilesHref}
              value={deviceProfilesHref}
              icon={<DevicesOtherOutlinedIcon fontSize="small" />}
              iconPosition="start"
              label={t('tabs.devices_beta')}
              sx={{ minHeight: 50, fontSize: 14 }}
            />
          )}

          <Tab
            component="a"
            href={strategyPickerHref}
            value={strategyPickerHref}
            icon={<TuneOutlinedIcon fontSize="small" />}
            iconPosition="start"
            label={t('tabs.strategy_picker_beta')}
            sx={{ minHeight: 50, fontSize: 14 }}
          />

          <Tab
            key="logs"
            value="logs"
            icon={<ArticleOutlinedIcon fontSize="small" />}
            iconPosition="start"
            label={t('tabs.logs')}
            sx={{
              minHeight: '50px',
              fontSize: 14,
              transition: 'color 0.1s ease-in-out',
              '&.Mui-selected': {
                color: 'text.primary',
              },
              '&:hover': {
                color: 'text.primary',
              },
            }}
          />

          {platform === 'asus-entware' && !isPending && (
            <Tab
              value="ip-health"
              icon={<ShieldOutlinedIcon fontSize="small" />}
              iconPosition="start"
              label={t('tabs.ip_health')}
              sx={{ minHeight: 50, fontSize: 14 }}
            />
          )}
        </Tabs>
      </Box>
    </>
  );
};

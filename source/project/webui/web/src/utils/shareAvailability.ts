import type { ShareState } from '@/api/shareClient';

export const shareMailUnavailableReason = (mail?: ShareState['mail']) => {
  if (!mail) return 'loading';
  if (mail.code === 'not_configured') return 'not_configured';
  if (mail.code === 'https_unavailable') return 'https_unavailable';
  if (mail.code === 'invalid_config') return 'invalid_config';
  if (!mail.configured || mail.code !== 'ready') return 'unavailable';
  return mail.sharing_v4 === true ? null : 'v4_unsupported';
};

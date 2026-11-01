import { useState } from 'react';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import TelegramIcon from '@mui/icons-material/Telegram';
import { Button, Link, Stack, Typography } from '@mui/material';

import { useTranslation } from '@/hooks/useTranslation';

import { copyText } from '@/utils/copyText';

const chatUrl = 'https://t.me/nfqws2AsusCommunityChat';

export function CommunityChatLink({
  copyable = false,
}: {
  copyable?: boolean;
}) {
  const { t } = useTranslation();
  const [result, setResult] = useState<'copied' | 'copy_failed' | ''>('');
  return (
    <Stack
      direction="row"
      spacing={1}
      useFlexGap
      flexWrap="wrap"
      alignItems="center"
    >
      <Link
        href={chatUrl}
        target="_blank"
        rel="noopener noreferrer"
        underline="hover"
        variant="body2"
        sx={{ display: 'inline-flex', gap: 0.75, alignItems: 'center' }}
      >
        <TelegramIcon sx={{ fontSize: '1.2em' }} />
        {t('community.chat')}
      </Link>
      {copyable && (
        <Button
          size="small"
          color="inherit"
          startIcon={<ContentCopyIcon sx={{ fontSize: '1em' }} />}
          sx={{ color: 'text.secondary' }}
          onClick={() => {
            void copyText(chatUrl)
              .then((ok) => setResult(ok ? 'copied' : 'copy_failed'))
              .catch(() => setResult('copy_failed'));
          }}
        >
          {t('community.copy_link')}
        </Button>
      )}
      {copyable && result && (
        <Typography variant="caption" role="status" color="text.secondary">
          {t(`community.${result}`)}
        </Typography>
      )}
    </Stack>
  );
}

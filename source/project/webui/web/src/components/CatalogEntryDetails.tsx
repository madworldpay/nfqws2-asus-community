import { Typography } from '@mui/material';

import { useTranslation } from '@/hooks/useTranslation';

// Previously published catalogs can still return these two stock sentences.
const boilerplate = new Set([
  'адаптация для asus',
  'адаптация под asus',
  'результат зависит от провайдера',
  'результаты зависят от провайдера',
  'работа зависит от провайдера и сети',
  'adaptation for asus',
  'adapted for asus',
  'asus adaptation',
  'result depends on provider',
  'results depend on provider',
  'result depends on isp',
  'results depend on isp',
  'results depend on isp and network',
  'results vary by provider',
]);

export function catalogDescription(text: string) {
  const sentences = text.split(/(?<=[.!?])\s+|[\r\n]+/u);
  const visible = sentences.filter((sentence) => {
    const normalized = sentence
      .trim()
      .toLowerCase()
      .replace('асус', 'asus')
      .replace(/\b(?:the|your)\s+/g, '')
      .replace(/\s+/g, ' ')
      .replace(/[.!?]+$/, '');
    return !boilerplate.has(normalized);
  });
  return visible.length === sentences.length ? text : visible.join(' ').trim();
}

export function CatalogEntryDetails({
  description = '',
  date,
  archiveDate = false,
  attribution,
  note,
}: {
  description?: string;
  date: string;
  archiveDate?: boolean;
  attribution?: string;
  note?: string;
}) {
  const { t, langcode } = useTranslation();
  const visibleDescription = catalogDescription(description);
  return (
    <>
      {visibleDescription && (
        <Typography component="span" display="block" variant="body2">
          {visibleDescription}
        </Typography>
      )}
      <Typography
        component="time"
        dateTime={date}
        display="block"
        variant="caption"
        color="text.secondary"
      >
        {t(
          archiveDate ? 'import.local.archive_date' : 'import.catalog.updated',
        )}
        {': '}
        {new Date(date).toLocaleDateString(
          langcode === 'en' ? 'en-GB' : 'ru-RU',
          {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            timeZone: 'UTC',
          },
        )}
      </Typography>
      {attribution && (
        <Typography
          component="span"
          display="block"
          variant="caption"
          color="text.secondary"
        >
          {attribution}
        </Typography>
      )}
      {note && (
        <Typography component="span" display="block" variant="caption">
          {note}
        </Typography>
      )}
    </>
  );
}

import { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  CircularProgress,
  List,
  ListItemButton,
  ListItemText,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';

import { ShareError, shareRequest } from '@/api/shareClient';

import { CatalogEntryDetails } from '@/components/CatalogEntryDetails';
import { StrategyNoteRow } from '@/components/StrategyNoteRow';

import {
  matchesStrategy,
  strategyNumber,
  useStrategyNotes,
} from '@/hooks/useStrategyNotes';
import { useTranslation } from '@/hooks/useTranslation';

const groups = ['presets', 'http80', 'tcp', 'udp', 'voice', 'assets'] as const;
type Group = (typeof groups)[number];
type Entry = {
  id: string;
  title: string;
  group: Group;
  attribution?: string;
  updated_at?: string;
  kind?: string;
  methods?: string[];
  adapted?: string[];
  unavailable?: string[];
  resident?: boolean;
};

export async function readLocalPreset(
  csrf: string,
  entry: string,
): Promise<string[]> {
  const result = await shareRequest(
    csrf,
    'importlocalentry',
    { entry },
    4194304,
    25000,
  );
  if (
    !result ||
    typeof result !== 'object' ||
    !('documents' in result) ||
    !Array.isArray(result.documents) ||
    ![1, 2].includes(result.documents.length) ||
    !result.documents.every((d: unknown) => typeof d === 'string')
  )
    throw new ShareError('invalid_import');
  return result.documents;
}

export function ImportLocalPack({
  csrf,
  disabled,
  onSelect,
}: {
  csrf: string;
  disabled: boolean;
  onSelect: (id: string) => void;
}) {
  const { t } = useTranslation();
  const [catalog, setCatalog] = useState<{
    entries: (Entry & { number: string })[];
    archiveDate: string;
    attribution: string;
  }>();
  const entries = catalog?.entries;
  const [group, setGroup] = useState<Group>('presets');
  const [query, setQuery] = useState('');
  const [failed, setFailed] = useState(false);
  const { notes, write, failed: notesFailed } = useStrategyNotes();
  const [editing, setEditing] = useState<string | null>(null);
  useEffect(() => {
    let current = true;
    setFailed(false);
    setCatalog(undefined);
    shareRequest(csrf, 'importlocalpack', {}, 524288, 25000)
      .then((result) => {
        if (
          !result ||
          typeof result !== 'object' ||
          !('entries' in result) ||
          !('assets' in result) ||
          !('archive_date' in result) ||
          typeof result.archive_date !== 'string' ||
          !('attribution' in result) ||
          typeof result.attribution !== 'string' ||
          !Array.isArray(result.entries) ||
          !Array.isArray(result.assets)
        )
          throw new Error();
        const rows = [...result.entries, ...result.assets] as Entry[];
        if (
          new Set(rows.map((row) => row?.id)).size !== rows.length ||
          !rows.every(
            (row) =>
              row &&
              groups.includes(row.group) &&
              typeof row.title === 'string' &&
              typeof row.id === 'string' &&
              /^[a-f0-9]{24}$/.test(row.id) &&
              (row.attribution === undefined ||
                typeof row.attribution === 'string') &&
              (row.updated_at === undefined ||
                typeof row.updated_at === 'string') &&
              [row.methods, row.adapted, row.unavailable].every(
                (values) =>
                  values === undefined ||
                  (Array.isArray(values) &&
                    values.every((v) => typeof v === 'string')),
              ),
          )
        )
          throw new Error();
        if (current)
          setCatalog({
            entries: rows.map((row) => ({
              ...row,
              number: strategyNumber('library', row.id),
            })),
            archiveDate: result.archive_date,
            attribution: result.attribution,
          });
      })
      .catch(() => {
        if (current) setFailed(true);
      });
    return () => {
      current = false;
    };
  }, [csrf]);
  const filtered = useMemo(() => {
    const words = query.trim().toLocaleLowerCase().split(/\s+/);
    return (entries ?? []).filter((row) => {
      return (
        row.group === group &&
        (row.number === editing ||
          matchesStrategy(words, [
            row.title,
            row.kind,
            row.attribution ?? catalog?.attribution,
            ...(row.methods ?? []),
            notes[row.number],
          ]))
      );
    });
  }, [entries, query, group, catalog?.attribution, notes, editing]);
  if (failed) return <Alert severity="error">{t('import.local.error')}</Alert>;
  if (!catalog) return <CircularProgress size={20} />;
  return (
    <Stack spacing={1} sx={{ minWidth: 0 }}>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
        <TextField
          select
          size="small"
          label={t('import.local.group')}
          value={group}
          onChange={(e) => setGroup(e.target.value as Group)}
          sx={{ minWidth: { xs: 0, sm: 180 } }}
        >
          {groups.map((g) => (
            <MenuItem key={g} value={g}>
              {t(('import.local.' + g) as 'import.local.presets')}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          size="small"
          type="search"
          fullWidth
          label={t('import.local.search')}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </Stack>
      <Typography variant="caption">{t('import.local.evidence')}</Typography>
      {group !== 'assets' && (
        <Typography variant="caption">{t('import.notes.local')}</Typography>
      )}
      {notesFailed && (
        <Alert severity="warning">{t('import.notes.unavailable')}</Alert>
      )}
      <Typography variant="body2" aria-live="polite">
        {t('import.local.found')} {filtered.length}
      </Typography>
      <List
        disablePadding
        aria-label={t('import.local.choose')}
        sx={{
          maxHeight: 'min(46dvh, 26rem)',
          overflowY: 'auto',
          overflowX: 'hidden',
          overscrollBehavior: 'contain',
        }}
      >
        {filtered.map((row) => {
          const note = row.unavailable?.length
            ? t('import.local.unavailable') + ' ' + row.unavailable.join(', ')
            : row.adapted?.length
              ? t('import.local.adapted') +
                ' ' +
                row.adapted.join(', ') +
                ' → multisplit (1,midsld)'
              : row.resident
                ? t('import.local.resident')
                : undefined;
          const choice = (
            <ListItemButton
              key={row.id}
              component="button"
              disabled={disabled || !!row.unavailable?.length || row.resident}
              onClick={() => onSelect(row.id)}
              sx={{
                width: '100%',
                textAlign: 'left',
                overflowWrap: 'anywhere',
              }}
            >
              <ListItemText
                primary={row.title}
                secondary={
                  <CatalogEntryDetails
                    description={row.kind}
                    date={row.updated_at ?? catalog.archiveDate}
                    archiveDate={!row.updated_at}
                    attribution={row.attribution ?? catalog.attribution}
                    note={note}
                  />
                }
              />
            </ListItemButton>
          );
          return row.group === 'assets' ? (
            choice
          ) : (
            <StrategyNoteRow
              key={row.id}
              number={row.number}
              title={row.title}
              value={notes[row.number] ?? ''}
              onChange={write}
              onEdit={setEditing}
            >
              {choice}
            </StrategyNoteRow>
          );
        })}
      </List>
    </Stack>
  );
}

import { Fragment, useEffect, useLayoutEffect, useRef, useState } from 'react';
import {
  Alert,
  Box,
  CircularProgress,
  List,
  ListItemButton,
  ListItemText,
  ListSubheader,
  MenuItem,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';

import {
  loadProfileCatalog,
  type CatalogProfile,
  type ProfileCatalog,
} from '@/api/profileCatalogClient';
import { shareRequest } from '@/api/shareClient';

import {
  catalogDescription,
  CatalogEntryDetails,
} from '@/components/CatalogEntryDetails';
import { StrategyNoteRow } from '@/components/StrategyNoteRow';

import {
  matchesStrategy,
  strategyNumber,
  useStrategyNotes,
} from '@/hooks/useStrategyNotes';
import { useTranslation } from '@/hooks/useTranslation';

const localGroups = [
  'presets',
  'http80',
  'tcp',
  'udp',
  'voice',
  'assets',
] as const;
type Group = (typeof localGroups)[number] | 'provider' | 'global';
const sections = {
  complete: ['global', 'presets'],
  providers: ['provider'],
  rules: ['http80', 'tcp', 'udp', 'voice'],
  files: ['assets'],
} as const satisfies Record<string, readonly Group[]>;
type Section = keyof typeof sections;

type LocalEntry = {
  id: string;
  title: string;
  group: (typeof localGroups)[number];
  attribution?: string;
  updated_at?: string;
  kind?: string;
  description?: string;
  collection?: string;
  methods?: string[];
  adapted?: string[];
  unavailable?: string[];
  resident?: boolean;
};
type LocalCatalog = {
  entries: LocalEntry[];
  archiveDate: string;
  attribution: string;
};
type Loaded<T> = { csrf: string; catalog: T | null };
type Row = {
  number: string;
  group: Group;
  title: string;
  description: string;
  attribution: string;
  date: string;
  archiveDate?: boolean;
  location?: string;
  terms?: string[];
  note?: string;
  disabled?: boolean;
  select: () => void;
};
type SourceMark = { top: number; target: number; size: number };

async function loadLocalCatalog(csrf: string): Promise<LocalCatalog> {
  const result = await shareRequest(csrf, 'importlocalpack', {}, 524288, 25000);
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
    throw new Error('invalid_catalog');
  const entries = [...result.entries, ...result.assets] as LocalEntry[];
  if (
    new Set(entries.map((entry) => entry?.id)).size !== entries.length ||
    !entries.every(
      (entry) =>
        entry &&
        localGroups.includes(entry.group) &&
        typeof entry.title === 'string' &&
        typeof entry.id === 'string' &&
        /^[a-f0-9]{24}$/.test(entry.id) &&
        [
          entry.attribution,
          entry.updated_at,
          entry.kind,
          entry.description,
          entry.collection,
        ].every((value) => value === undefined || typeof value === 'string') &&
        [entry.methods, entry.adapted, entry.unavailable].every(
          (values) =>
            values === undefined ||
            (Array.isArray(values) &&
              values.every((value) => typeof value === 'string')),
        ),
    )
  )
    throw new Error('invalid_catalog');
  return {
    entries,
    archiveDate: result.archive_date,
    attribution: result.attribution,
  };
}

export function ImportStrategies({
  csrf,
  disabled,
  onSelectLocal,
  onSelectProfile,
}: {
  csrf: string;
  disabled: boolean;
  onSelectLocal: (id: string, title?: string) => void;
  onSelectProfile: (profile: CatalogProfile) => void;
}) {
  const { t } = useTranslation();
  const [local, setLocal] = useState<Loaded<LocalCatalog>>();
  const [profiles, setProfiles] = useState<Loaded<ProfileCatalog>>();
  const [section, setSection] = useState<Section>('complete');
  const [query, setQuery] = useState('');
  const [editing, setEditing] = useState<string | null>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const [marks, setMarks] = useState<SourceMark[]>([]);
  const { notes, write, failed: notesFailed } = useStrategyNotes();

  useEffect(() => {
    let current = true;
    const readLocal = (catalog: LocalCatalog | null) => {
      if (current) setLocal({ csrf, catalog });
    };
    const readProfiles = (catalog: ProfileCatalog | null) => {
      if (current) setProfiles({ csrf, catalog });
    };
    void loadLocalCatalog(csrf).then(readLocal, () => readLocal(null));
    void loadProfileCatalog(csrf, 'package').then(readProfiles, () =>
      readProfiles(null),
    );
    return () => {
      current = false;
    };
  }, [csrf]);

  const library = local?.csrf === csrf ? local.catalog : undefined;
  const packaged = profiles?.csrf === csrf ? profiles.catalog : undefined;
  const rows: Row[] = [
    ...(packaged?.profiles ?? []).map((profile) => {
      const needsUpdate = profile.min_build > (packaged?.build ?? 0);
      return {
        number: strategyNumber('cloud', profile.id),
        group: profile.category,
        title: profile.title,
        description: profile.description,
        attribution: profile.attribution,
        date: profile.updated_at,
        location: [profile.provider, profile.region]
          .filter(Boolean)
          .join(' · '),
        note: needsUpdate ? t('import.catalog.update') : undefined,
        disabled: needsUpdate,
        select: () => onSelectProfile(profile),
      };
    }),
    ...(library?.entries ?? []).map((entry) => ({
      number: strategyNumber('library', entry.id),
      group:
        entry.collection === 'zemidala' && entry.group === 'presets'
          ? ('provider' as const)
          : entry.group,
      title: entry.title,
      description: entry.description ?? entry.kind ?? '',
      attribution: entry.attribution ?? library?.attribution ?? '',
      date: entry.updated_at ?? library?.archiveDate ?? '',
      archiveDate: !entry.updated_at,
      terms: [entry.collection ?? '', ...(entry.methods ?? [])],
      note: entry.unavailable?.length
        ? t('import.local.unavailable') + ' ' + entry.unavailable.join(', ')
        : !entry.collection && entry.adapted?.length
          ? t('import.local.adapted') +
            ' ' +
            entry.adapted.join(', ') +
            ' → multisplit (1,midsld)'
          : entry.resident
            ? t('import.local.resident')
            : undefined,
      disabled: Boolean(entry.unavailable?.length || entry.resident),
      select: () =>
        onSelectLocal(
          entry.id,
          entry.group === 'assets' ? undefined : entry.title,
        ),
    })),
  ];
  const words = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  const shownGroups: readonly Group[] = words.length
    ? Object.values(sections).flat()
    : sections[section];
  const visible = rows.filter(
    (row) =>
      (row.number === editing || shownGroups.includes(row.group)) &&
      (row.number === editing ||
        matchesStrategy(words, [
          row.title,
          catalogDescription(row.description),
          row.location,
          row.attribution,
          row.note,
          ...(row.terms ?? []),
          notes[row.number],
        ])),
  );
  const groups = shownGroups.flatMap((group) => {
    const sources = new Map<string, Row[]>();
    for (const row of visible) {
      if (row.group !== group) continue;
      const source =
        row.attribution.trim() || t('import.strategies.unknown_source');
      const members = sources.get(source);
      if (members) members.push(row);
      else sources.set(source, [row]);
    }
    return sources.size ? [{ group, sources: Array.from(sources) }] : [];
  });
  const blockLabels = groups.flatMap(({ sources }) =>
    sources.map(([source]) => source),
  );
  const blockKey = JSON.stringify(
    groups.map(({ group, sources }) => [
      group,
      sources.map(([source]) => source),
    ]),
  );
  useLayoutEffect(() => {
    const list = listRef.current;
    if (!list) return;
    const blocks = Array.from(
      list.querySelectorAll<HTMLElement>('[data-strategy-block]'),
    );
    const measure = () => {
      const { clientHeight, scrollHeight } = list;
      if (blocks.length < 2 || scrollHeight <= clientHeight || !clientHeight) {
        setMarks([]);
        return;
      }
      const origin = list.getBoundingClientRect().top - list.scrollTop;
      const size = Math.min(24, clientHeight / blocks.length);
      let next = size / 2;
      setMarks(
        blocks.map((block, index) => {
          const target = block.getBoundingClientRect().top - origin;
          const preferred = (target / scrollHeight) * clientHeight;
          // Leave room for the next mark even when several small blocks are adjacent.
          const last = clientHeight - (blocks.length - index - 0.5) * size;
          const top = Math.max(next, Math.min(preferred, last));
          next = top + size;
          return { top, target, size };
        }),
      );
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(list);
    blocks.forEach((block) => observer.observe(block));
    return () => observer.disconnect();
  }, [blockKey]);
  const loading = library === undefined || packaged === undefined;
  return (
    <Stack spacing={1} sx={{ minWidth: 0 }}>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
        <TextField
          select
          size="small"
          label={t('import.local.group')}
          value={section}
          onChange={(event) => setSection(event.target.value as Section)}
          sx={{ minWidth: { xs: 0, sm: 208 } }}
        >
          {(Object.keys(sections) as Section[]).map((key) => (
            <MenuItem key={key} value={key}>
              {t(`import.strategies.${key}`)}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          size="small"
          type="search"
          fullWidth
          label={t('import.strategies.search')}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
      </Stack>
      {loading && <CircularProgress size={20} />}
      {library === null && (
        <Alert severity="info">{t('import.local.error')}</Alert>
      )}
      {packaged === null && (
        <Alert severity="info">
          {t('import.strategies.package_unavailable')}
        </Alert>
      )}
      {notesFailed && (
        <Alert severity="warning">{t('import.notes.unavailable')}</Alert>
      )}
      <Typography variant="body2" aria-live="polite">
        {t('import.local.found')} {visible.length}
      </Typography>
      {!loading && !visible.length && (
        <Typography variant="body2">{t('import.notes.no_matches')}</Typography>
      )}
      <Box
        sx={{
          display: 'grid',
          minWidth: 0,
          gridTemplateColumns: 'minmax(0, 1fr) auto',
        }}
      >
        <List
          ref={listRef}
          disablePadding
          aria-label={t('import.strategies.choose')}
          sx={{
            maxHeight: 'min(46dvh, 32rem)',
            overflowY: 'auto',
            overflowX: 'hidden',
            overscrollBehavior: 'contain',
          }}
        >
          {groups.map(({ group, sources }) => (
            <Fragment key={group}>
              <ListSubheader disableSticky>
                {t(
                  group === 'global' || group === 'provider'
                    ? `import.catalog.${group}`
                    : `import.local.${group}`,
                )}
              </ListSubheader>
              {sources.map(([source, members]) => (
                <Box
                  key={source}
                  component="li"
                  data-strategy-block
                  sx={{ listStyle: 'none' }}
                >
                  <Typography
                    component="h3"
                    variant="body2"
                    sx={{
                      px: 2,
                      py: 0.6,
                      borderTop: 1,
                      borderColor: 'divider',
                      color: 'text.secondary',
                      overflowWrap: 'anywhere',
                    }}
                  >
                    {source}
                  </Typography>
                  <List disablePadding>
                    {members.map((row) => {
                      const choice = (
                        <ListItemButton
                          key={row.number}
                          component="button"
                          disabled={disabled || row.disabled}
                          onClick={row.select}
                          sx={{
                            width: '100%',
                            textAlign: 'left',
                            overflowWrap: 'anywhere',
                          }}
                        >
                          <ListItemText
                            primary={row.title}
                            secondary={
                              <>
                                {row.location}
                                <CatalogEntryDetails
                                  description={row.description}
                                  date={row.date}
                                  archiveDate={row.archiveDate}
                                  attribution={row.attribution}
                                  note={row.note}
                                />
                              </>
                            }
                          />
                        </ListItemButton>
                      );
                      return group === 'assets' ? (
                        choice
                      ) : (
                        <StrategyNoteRow
                          key={row.number}
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
                </Box>
              ))}
            </Fragment>
          ))}
        </List>
        {blockLabels.length > 1 && (
          <Box sx={{ width: 24, position: 'relative' }}>
            {marks.length === blockLabels.length && (
              <Box
                component="nav"
                aria-label={t('import.strategies.source_navigation')}
                sx={{
                  position: 'absolute',
                  inset: 0,
                  '&::before': {
                    content: '""',
                    position: 'absolute',
                    insetBlock: 0,
                    left: '50%',
                    borderLeft: 1,
                    borderColor: 'divider',
                  },
                }}
              >
                {marks.map(({ top, target, size }, index) => {
                  const source = blockLabels[index];
                  return (
                    <Tooltip
                      key={index}
                      title={source}
                      placement="left"
                      describeChild
                    >
                      <Box
                        component="button"
                        type="button"
                        aria-label={
                          t('import.strategies.jump_source') + ' — ' + source
                        }
                        onClick={() => listRef.current?.scrollTo(0, target)}
                        sx={{
                          position: 'absolute',
                          top,
                          width: '100%',
                          height: size,
                          transform: 'translateY(-50%)',
                          cursor: 'pointer',
                          border: 0,
                          p: 0,
                          borderRadius: 1,
                          bgcolor: 'transparent',
                          color: 'primary.main',
                          '&::after': {
                            content: '""',
                            display: 'block',
                            mx: 'auto',
                            width: 13,
                            height: 3,
                            borderRadius: 1,
                            bgcolor: 'currentColor',
                          },
                          '&:hover, &:focus-visible': {
                            bgcolor: 'action.hover',
                          },
                          '&:focus-visible': {
                            outline: '2px solid currentColor',
                            outlineOffset: '-2px',
                          },
                        }}
                      />
                    </Tooltip>
                  );
                })}
              </Box>
            )}
          </Box>
        )}
      </Box>
    </Stack>
  );
}

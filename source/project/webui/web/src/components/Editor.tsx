import { useCallback, useEffect, useMemo, useState } from 'react';
import { history, undo } from '@codemirror/commands';
import { StreamLanguage } from '@codemirror/language';
import { lua } from '@codemirror/legacy-modes/mode/lua';
import { linter, lintGutter } from '@codemirror/lint';
import { Compartment } from '@codemirror/state';
import { EditorView, keymap } from '@codemirror/view';
import AutoFixHighIcon from '@mui/icons-material/AutoFixHigh';
import UndoIcon from '@mui/icons-material/Undo';
import WrapTextIcon from '@mui/icons-material/WrapText';
import {
  Box,
  Button,
  IconButton,
  Stack,
  Tooltip,
  Typography,
  useTheme,
} from '@mui/material';
import { type SxProps } from '@mui/system/styleFunctionSx';
import { vscodeDark, vscodeLight } from '@uiw/codemirror-theme-vscode';
import ReactCodeMirror from '@uiw/react-codemirror';

import type { FilenamesRequest } from '@/api/schema';

import { InlineHelp } from '@/components/InlineHelp';

import { useTranslation } from '@/hooks/useTranslation';

import { codeMirrorLangList } from '@/utils/codeMirrorLangList';
import { codeMirrorLangLog } from '@/utils/codeMirrorLangLog';
import {
  codeMirrorLangNfqws,
  codeMirrorLangNfqwsArgs,
} from '@/utils/codeMirrorLangNfqws';
import { configSectionSpacing } from '@/utils/configSectionSpacing';
import { newlineMarkers } from '@/utils/newlineMarkers';
import { findUnclosedQuotes, type QuoteIssue } from '@/utils/quoteDiagnostics';

const historyCompartment = new Compartment();

interface EditorProps {
  type: FilenamesRequest['type'] | 'lua' | 'arg';
  value: string;
  onChange?: (value: string, changed: boolean) => void;
  onSave?: () => void;
  readonly?: boolean;
  autoFocus?: boolean;
  maxHeight?: number | string;
  minHeight?: string;
  sx?: SxProps;
}

export const Editor = ({
  type,
  value,
  onChange,
  onSave,
  readonly = false,
  autoFocus = false,
  maxHeight = 'auto',
  minHeight = 'auto',
  sx,
}: EditorProps) => {
  const { palette } = useTheme();

  const { t } = useTranslation();

  const [editorView, setEditorView] = useState<EditorView | null>(null);
  const [changed, setChanged] = useState(false);
  const [wrap, setWrap] = useState(true);
  const [input, setInput] = useState({ source: value, text: value });
  const currentText = input.source === value ? input.text : value;
  const syntax = type === 'conf' || type === 'arg';
  const issues = useMemo(
    () =>
      syntax
        ? findUnclosedQuotes(currentText, type === 'arg' ? 'arg' : 'conf')
        : [],
    [currentText, syntax, type],
  );
  const issueMessage = useCallback(
    (issue: QuoteIssue) =>
      t('editor.quote_missing')
        .replace('{quote}', issue.quote)
        .replace('{line}', String(issue.line))
        .replace('{column}', String(issue.column)),
    [t],
  );

  const extensions = useMemo(() => {
    const result = [historyCompartment.of([])];

    if (onSave) {
      result.push(
        keymap.of([
          {
            key: 'Ctrl-s',
            mac: 'Cmd-s',
            run: () => {
              onSave();
              return true;
            },
          },
        ]),
      );
    }
    if (type === 'conf') {
      result.push(codeMirrorLangNfqws(), configSectionSpacing);
    } else if (type === 'arg') {
      result.push(codeMirrorLangNfqwsArgs());
    } else if (type === 'list') {
      result.push(codeMirrorLangList());
    } else if (type === 'log') {
      result.push(codeMirrorLangLog());
    } else if (type === 'lua') {
      result.push(StreamLanguage.define(lua));
    }

    if (syntax) {
      if (wrap) result.push(EditorView.lineWrapping);
      result.push(
        newlineMarkers(t('editor.hard_break')),
        lintGutter(),
        linter(
          (view) =>
            findUnclosedQuotes(
              view.state.doc.toString(),
              type === 'arg' ? 'arg' : 'conf',
            ).map((issue) => ({
              from: issue.from,
              to: issue.to,
              severity: 'warning' as const,
              message: issueMessage(issue),
            })),
          { delay: 350 },
        ),
      );
    }
    return result;
  }, [type, onSave, syntax, wrap, t, issueMessage]);

  const handleMagicButton = useCallback(() => {
    if (!editorView) {
      return;
    }

    const text = editorView.state.doc.toString();
    const lines = text.split('\n');

    const seen = new Set<string>();
    const result: string[] = [];

    for (const line of lines) {
      const trimmed = line.trim();

      if (
        trimmed.length === 0 ||
        trimmed.startsWith('#') ||
        trimmed.startsWith('//')
      ) {
        result.push(line);
        continue;
      }

      if (seen.has(trimmed)) {
        continue;
      }

      seen.add(trimmed);
      result.push(trimmed);
    }

    const data = result.join('\n');

    editorView.dispatch({
      changes: {
        from: 0,
        to: editorView.state.doc.length,
        insert: data,
      },
    });
  }, [editorView]);

  const handleUndoButton = useCallback(() => {
    if (editorView) {
      undo({ state: editorView.state, dispatch: editorView.dispatch });
    }
  }, [editorView]);

  useEffect(() => {
    editorView?.dispatch({
      effects: historyCompartment.reconfigure([]),
    });
    editorView?.dispatch({
      effects: historyCompartment.reconfigure([history()]),
    });
  }, [value, editorView]);

  return (
    <Stack spacing={0.5} sx={{ minWidth: 0, minHeight: 0, flex: 1, ...sx }}>
      {syntax && (
        <Stack direction="row" alignItems="center" useFlexGap flexWrap="wrap">
          <Button
            size="small"
            startIcon={<WrapTextIcon />}
            aria-pressed={wrap}
            onClick={() => setWrap((v) => !v)}
          >
            {t('editor.wrap')}: {t(wrap ? 'editor.wrap_on' : 'editor.wrap_off')}
          </Button>
          <InlineHelp title={t('editor.wrap')}>
            <Typography>{t('editor.wrap_hint')}</Typography>
          </InlineHelp>
          <Typography variant="caption" color="text.secondary">
            ↵ — {t('editor.hard_break')}
          </Typography>
        </Stack>
      )}
      <Box
        flex={1}
        sx={{
          display: 'flex',
          minHeight: 0,
          position: 'relative',
          overflow: 'auto',
          '& .cm-theme': {
            display: 'flex',
            minWidth: '100%',
            fontSize: 13,
            maxHeight,
            minHeight,
          },
          '& .cm-editor': {
            display: 'flex !important',
            minWidth: '100%',
            minHeight: '100%',
            background: (theme) => theme.palette.background.default,
            outline: 'none',
          },
          '& .cm-gutters': {
            background: (theme) => theme.palette.background.paper,
          },
          '& .cm-scroller': { overflow: 'auto' },
          '& .cm-hard-break': { opacity: 0.45, paddingLeft: '0.4em' },
          '& .cm-lineNumbers .cm-gutterElement': {
            paddingLeft: '13px !important',
          },
          '& .cm-line.cm-config-section': {
            paddingTop: '0.85em',
            borderTop: '1px solid',
            borderColor: 'divider',
          },
        }}
      >
        <ReactCodeMirror
          value={value}
          minHeight={minHeight}
          theme={palette.mode === 'light' ? vscodeLight : vscodeDark}
          autoFocus={autoFocus}
          readOnly={readonly}
          editable={!readonly}
          onCreateEditor={(view) => setEditorView(view)}
          onChange={(newValue) => {
            setInput({ source: value, text: newValue });
            setChanged(value !== newValue);
            onChange?.(newValue, value !== newValue);
          }}
          basicSetup={{
            lineNumbers: true,
            foldGutter: type !== 'conf',
            foldKeymap: type !== 'conf',
            history: false, // enabled in extensions
            historyKeymap: true,
          }}
          extensions={extensions}
        />

        {type !== 'arg' && !readonly && (
          <Tooltip
            title={t('editor.undo_button')}
            enterTouchDelay={0}
            placement="bottom"
          >
            <IconButton
              size="small"
              onClick={handleUndoButton}
              disabled={!changed}
              sx={{
                position: 'absolute',
                right: '16pt',
                top: '4pt',
                opacity: 0.7,
                color: 'text.secondary',
                transition: 'color 0.1s ease-in-out, opacity 0.1s ease-in-out',
                minWidth: 0,
                '&:hover': {
                  opacity: 1,
                  color: 'primary.main',
                },
              }}
            >
              <UndoIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        )}

        {type === 'list' && !readonly && (
          <Tooltip
            title={t('editor.magic_button')}
            enterTouchDelay={0}
            placement="bottom"
          >
            <IconButton
              size="small"
              onClick={handleMagicButton}
              sx={{
                position: 'absolute',
                right: '16pt',
                top: '4pt',
                transform: 'translateX(-120%)',
                opacity: 0.7,
                color: 'text.secondary',
                transition: 'color 0.1s ease-in-out, opacity 0.1s ease-in-out',
                minWidth: 0,
                '&:hover': {
                  opacity: 1,
                  color: 'primary.main',
                },
              }}
            >
              <AutoFixHighIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        )}
      </Box>
      {issues.map((issue) => (
        <Button
          key={issue.from}
          size="small"
          color="warning"
          sx={{ justifyContent: 'flex-start' }}
          onClick={() => {
            editorView?.dispatch({
              selection: { anchor: issue.from },
              scrollIntoView: true,
            });
            editorView?.focus();
          }}
        >
          {issueMessage(issue)}
        </Button>
      ))}
    </Stack>
  );
};

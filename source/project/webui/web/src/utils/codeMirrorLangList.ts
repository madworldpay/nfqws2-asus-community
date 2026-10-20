// CodeMirror 6 language support for nfqws *.list (comments only)

import {
  LanguageSupport,
  StreamLanguage,
  type StringStream,
} from '@codemirror/language';

type ListState = {
  tokenize: (stream: StringStream, state: ListState) => string | null;
};

function tokenBase(stream: StringStream, _state: ListState): string | null {
  // Line comments only (starting with #, after optional spaces)
  if (stream.sol()) {
    stream.eatSpace();

    if (stream.peek() === '#') {
      stream.skipToEnd();
      return 'comment';
    }
  }

  stream.skipToEnd();
  return null;
}

export const nfqwsListStream = StreamLanguage.define<ListState>({
  name: 'nfqws-list',
  startState() {
    const state: ListState = {
      tokenize: tokenBase,
    };
    return state;
  },
  token(stream, state) {
    if (stream.eatSpace()) return null;
    return state.tokenize(stream, state);
  },
  languageData: {
    commentTokens: { line: '#' },
  },
});

export function codeMirrorLangList() {
  return new LanguageSupport(nfqwsListStream);
}
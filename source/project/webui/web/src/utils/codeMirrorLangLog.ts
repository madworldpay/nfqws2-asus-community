// CodeMirror 6 language support for logs

import {
  LanguageSupport,
  StreamLanguage,
  type StringStream,
} from '@codemirror/language';

/**
 * Helpers
 */
function wordRegexp(words: string[]) {
  return new RegExp('^(?:' + words.join('|') + ')$', 'i');
}

/**
 * nfqws logs
 */
type LogState = {
  tokenize: (stream: StringStream, state: LogState) => string | null;
};

const logLevels = wordRegexp([
  'ERROR',
  'WARN',
  'WARNING',
  'INFO',
  'DEBUG',
  'TRACE',
  'FATAL',
  'CRITICAL',
  'SEVERE',
  'NOTICE',
]);

const logKeywords = wordRegexp([
  'started',
  'stopped',
  'restarted',
  'failed',
  'success',
  'connection',
  'packet',
  'rule',
  'match',
  'drop',
  'accept',
  'forward',
  'queue',
  'process',
  'thread',
  'memory',
  'cpu',
  'timeout',
  'retry',
  'attempt',
  'session',
  'client',
  'server',

  // common nfqws fields
  'profile',
  'proto',
  'udp_in',
  'udp_out',
  'fail',
  'counter',
  'retrans',
  'threshold',
  'reached',

  // common key=value fields in debug logs
  'src',
  'dst',
  'sport',
  'dport',
  'ttl',
  'flags',
  'seq',
  'ack',
  'ack_seq',
  'len',
  'id',
  'mark',
  'ifin',
  'ifout',
  'hostname',
  'ssid',
  'icmp',
  'l7proto',
  'track_direction',
  'fixed_direction',
  'connection_proto',
  'payload_type',
]);

const logProtocols = wordRegexp([
  'tls',
  'quic',
  'http',
  'https',
  'tcp',
  'udp',
  'ip4',
  'ip6',
]);

const logWarnWords = wordRegexp([
  'retrans',
  'threshold',
  'reached',
  'timeout',
  'retry',
]);

const logErrorWords = wordRegexp(['failed', 'error', 'fatal', 'critical']);

function looksLikeDomain(s: string) {
  // very lightweight: contains a dot, has letters, and no spaces
  return /[A-Za-z]/.test(s) && s.includes('.') && !s.includes('..');
}

function logTokenBase(stream: StringStream, _state: LogState): string | null {
  // Common separators in these logs
  if (stream.peek() === ':' || stream.peek() === '=') {
    stream.next();
    return 'operator';
  }

  // Timestamp at start of line: `08.02.2026 15:24:39`
  if (stream.sol()) {
    if (stream.match(/^\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2}:\d{2}/, true)) {
      return 'atom';
    }
    // ISO-ish variants
    if (
      stream.match(/^\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?/, true)
    ) {
      return 'atom';
    }
    // Time-only
    if (stream.match(/^\d{2}:\d{2}:\d{2}/, true)) {
      return 'atom';
    }
  }

  // Bracketed module like [nfqws]
  if (stream.peek() === '[') {
    stream.next();
    stream.eatWhile(/[^\]]/);
    if (stream.peek() === ']') stream.next();
    return 'bracket';
  }

  // Parenthesized marker like (noname)
  if (stream.peek() === '(') {
    stream.next();
    stream.eatWhile(/[^)]/);
    if (stream.peek() === ')') stream.next();
    return 'comment';
  }

  // Arrows / comparisons seen in counters: `udp_in 0<=1 udp_out 4>=4`
  if (stream.match(/^(<==|==>|<=>|<=|>=|=>|=<)/, true)) {
    return 'operator';
  }

  // IPs (optionally with port)
  if (stream.match(/^\d+\.\d+\.\d+\.\d+(?::\d+)?/, true)) {
    return 'number';
  }

  // UUID-like ids should be a single token (avoid highlighting the leading digits as a number)
  if (
    stream.match(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i,
      true,
    )
  ) {
    return 'string-2';
  }

  // Other long hex-ish ids (at least 12 chars, with letters+digits) as a single token
  if (stream.match(/^[0-9a-f]{12,}(?![A-Za-z0-9_.-])/i, true)) {
    return 'string-2';
  }

  // Numbers and counters like 1/3
  if (stream.match(/^\d+\/\d+/, true)) {
    return 'number';
  }
  if (stream.match(/^\d+(?![A-Za-z0-9_.-])/, true)) {
    return 'number';
  }

  // Hex numbers like 0xFFFFFAAC
  if (stream.match(/^0x[0-9a-f]+/i, true)) {
    return 'number';
  }

  // Words / ids / domains (consume a token-like chunk)
  const ch = stream.next();
  if (ch == null) return null;
  stream.eatWhile(/[\w\-./]/);
  const cur = stream.current();

  // Highlight any token that looks like a key in `key=value`
  if (stream.peek() === '=') {
    return 'def';
  }

  // Levels
  if (logLevels.test(cur)) {
    if (cur === 'ERROR' || cur === 'FATAL' || cur === 'CRITICAL')
      return 'error';
    if (cur === 'WARN' || cur === 'WARNING') return 'warning';
    if (cur === 'INFO' || cur === 'NOTICE') return 'info';
    if (cur === 'DEBUG' || cur === 'TRACE') return 'comment';
    return 'tag';
  }

  // Protocols
  if (logProtocols.test(cur)) return 'typeName';

  // Warnings / errors expressed as words
  if (logErrorWords.test(cur)) return 'error';
  if (logWarnWords.test(cur)) return 'warning';

  // Field keys like `client`, `profile`, `proto`, `udp_in`
  if (logKeywords.test(cur)) return 'def';

  // Hostnames / domains (e.g. mainscope.jamfcloud.com)
  if (looksLikeDomain(cur)) return 'string-2';

  return null;
}

export const nfqwsLogStream = StreamLanguage.define<LogState>({
  name: 'nfqws-log',
  startState() {
    return { tokenize: logTokenBase };
  },
  token(stream, state) {
    if (stream.eatSpace()) return null;
    return state.tokenize(stream, state);
  },
});

export function codeMirrorLangLog() {
  return new LanguageSupport(nfqwsLogStream);
}

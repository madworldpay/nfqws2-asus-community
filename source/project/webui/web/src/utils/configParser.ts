export type NfqwsConfig = {
  ISP_INTERFACE: string;
  NFQWS_BASE_ARGS: string;
  NFQWS_ARGS: string;
  NFQWS_ARGS_QUIC: string;
  NFQWS_ARGS_UDP: string;
  NFQWS_EXTRA_ARGS: 'MODE_LIST' | 'MODE_ALL' | 'MODE_AUTO';
  NFQWS_ARGS_IPSET: string;
  NFQWS_ARGS_CUSTOM: string;
  IPV6_ENABLED: boolean;
  TCP_PORTS: string;
  UDP_PORTS: string;
  POLICY_NAME: string;
  POLICY_EXCLUDE: boolean;
  ASUS_CLIENT_MODE: string;
  ASUS_CLIENTS4: string;
  ASUS_CLIENTS6: string;
  LOG_LEVEL: boolean;
};

const NFQWS_CONFIG_KEYS: (keyof NfqwsConfig)[] = [
  'ISP_INTERFACE',
  'NFQWS_BASE_ARGS',
  'NFQWS_ARGS',
  'NFQWS_ARGS_QUIC',
  'NFQWS_ARGS_UDP',
  'NFQWS_EXTRA_ARGS',
  'NFQWS_ARGS_IPSET',
  'NFQWS_ARGS_CUSTOM',
  'IPV6_ENABLED',
  'TCP_PORTS',
  'UDP_PORTS',
  'POLICY_NAME',
  'POLICY_EXCLUDE',
  'ASUS_CLIENT_MODE',
  'ASUS_CLIENTS4',
  'ASUS_CLIENTS6',
  'LOG_LEVEL',
] as const;

type LineBlock = {
  start: number;
  end: number;
  indent: string;
  quote: '"' | "'" | '';
  hadMultiline: boolean;
  lineBackslashes: number[];
};

export const parseConfig = (config: string) => {
  const defaults: NfqwsConfig = {
    ISP_INTERFACE: '',
    NFQWS_BASE_ARGS: '',
    NFQWS_ARGS: '',
    NFQWS_ARGS_QUIC: '',
    NFQWS_ARGS_UDP: '',
    NFQWS_EXTRA_ARGS: 'MODE_AUTO',
    NFQWS_ARGS_IPSET: '',
    NFQWS_ARGS_CUSTOM: '',
    IPV6_ENABLED: false,
    TCP_PORTS: '',
    UDP_PORTS: '',
    POLICY_NAME: '',
    POLICY_EXCLUDE: false,
    ASUS_CLIENT_MODE: 'all',
    ASUS_CLIENTS4: '',
    ASUS_CLIENTS6: '',
    LOG_LEVEL: false,
  };

  const rawValues: Record<string, string> = {};

  const lines = config.split('\n');
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    if (!trimmed || trimmed.startsWith('#')) {
      i += 1;
      continue;
    }

    const eqIndex = line.indexOf('=');
    if (eqIndex === -1) {
      i += 1;
      continue;
    }

    const key = line.slice(0, eqIndex).trim();
    let value = line.slice(eqIndex + 1).trim();

    if (value.startsWith('"') || value.startsWith("'")) {
      const quote = value[0];
      value = value.slice(1);
      let isMultiline = false;

      while (true) {
        let quoteIndex = -1;
        for (let at = 0; at < value.length; at++) {
          if (quote === '"' && value[at] === '\\') at++;
          else if (value[at] === quote) {
            quoteIndex = at;
            break;
          }
        }
        if (quoteIndex !== -1) {
          const before = value.slice(0, quoteIndex);
          const after = value.slice(quoteIndex + 1).trim();
          value = before;
          if (after && !after.startsWith('#')) {
            value = `${value}${after}`;
          }
          break;
        }

        i += 1;
        if (i >= lines.length) {
          break;
        }
        isMultiline = true;
        value = `${value}\n${lines[i].trimStart()}`;
      }

      if (isMultiline) {
        value = value.replace(/\n[ \t]+/g, '\n');
      }

      if (quote === '"') {
        value = value.replace(/\\(["\\])/g, '$1');
      } else {
        value = value.replace(/\\'/g, "'");
      }
    } else {
      value = value.split('#')[0]?.trim() ?? value;
    }

    rawValues[key] = value;
    i += 1;
  }

  const resolveValue = (value: string, depth = 0): string => {
    if (depth > 5) {
      return value;
    }
    return value.replace(/\$(\w+)|\$\{(\w+)}/g, (_match, name1, name2) => {
      const name = name1 ?? name2;
      const resolved = rawValues[name];
      if (resolved === undefined) {
        return '';
      }
      return resolveValue(resolved, depth + 1);
    });
  };

  const toBoolean = (value: string): boolean => {
    const normalized = value.trim().toLowerCase();
    return normalized === '1' || normalized === 'true' || normalized === 'yes';
  };

  const configObj: NfqwsConfig = { ...defaults };

  for (const key of NFQWS_CONFIG_KEYS) {
    const raw = rawValues[key];
    if (raw === undefined) {
      continue;
    }
    const resolved = resolveValue(raw);

    switch (key) {
      case 'IPV6_ENABLED':
      case 'POLICY_EXCLUDE':
      case 'LOG_LEVEL':
        configObj[key] = toBoolean(resolved);
        break;
      case 'NFQWS_EXTRA_ARGS': {
        const rawMode = raw.match(/^\$?\{?(MODE_(?:LIST|ALL|AUTO))}?$/);
        if (rawMode?.[1]) {
          configObj[key] = rawMode[1] as NfqwsConfig['NFQWS_EXTRA_ARGS'];
          break;
        }
        if (resolved === rawValues.MODE_LIST) {
          configObj[key] = 'MODE_LIST';
        } else if (resolved === rawValues.MODE_ALL) {
          configObj[key] = 'MODE_ALL';
        } else if (resolved === rawValues.MODE_AUTO) {
          configObj[key] = 'MODE_AUTO';
        }
        break;
      }
      default:
        configObj[key] = resolved;
    }
  }

  return configObj;
};

const toRawValue = (
  key: keyof NfqwsConfig,
  value: NfqwsConfig[keyof NfqwsConfig],
) => {
  if (key === 'NFQWS_EXTRA_ARGS') {
    return `$${value}`;
  }
  if (
    key === 'IPV6_ENABLED' ||
    key === 'POLICY_EXCLUDE' ||
    key === 'LOG_LEVEL'
  ) {
    return value ? '1' : '0';
  }
  return String(value ?? '');
};

const needsQuotes = (raw: string) =>
  raw.includes(' ') || raw.includes('\n') || raw === '';

const stringifyValue = (
  key: keyof NfqwsConfig,
  value: NfqwsConfig[keyof NfqwsConfig],
  block: LineBlock | null,
): string => {
  const raw = toRawValue(key, value);
  const quote = block?.quote ?? '';
  const shouldQuote = quote !== '' || needsQuotes(raw);
  const quoteChar: '"' | "'" = (quote || '"') as '"' | "'";

  if (!shouldQuote) {
    return raw;
  }

  const encoded = raw
    .split('\n')
    .map((line, index) => {
      if (quoteChar !== '"') return line;
      let text = line.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
      const originalSlashes = block?.lineBackslashes[index] ?? 0;
      const currentSlashes = line.match(/(\\+)$/)?.[0].length ?? 0;
      // parseConfig retains continuation layout. Preserve the source's odd/even
      // escape parity when a different part of the same line is edited.
      if (
        originalSlashes % 2 === 1 &&
        currentSlashes === Math.ceil(originalSlashes / 2)
      )
        text =
          text.slice(0, -currentSlashes * 2) + '\\'.repeat(originalSlashes);
      return text;
    })
    .join('\n');
  if (!encoded.includes('\n')) {
    return `${quoteChar}${encoded}${quoteChar}`;
  }

  const indent = block?.indent ?? '  ';
  const lines = encoded.split('\n');
  const rendered = lines
    .map((line, idx) => (idx === 0 ? line : `${indent}${line}`))
    .join('\n');

  return `${quoteChar}${rendered}${quoteChar}`;
};

const readBlock = (lines: string[], startIndex: number): LineBlock => {
  const line = lines[startIndex];
  const eqIndex = line.indexOf('=');
  const valuePart = eqIndex === -1 ? '' : line.slice(eqIndex + 1).trimStart();
  const quote =
    valuePart.startsWith('"') || valuePart.startsWith("'")
      ? (valuePart[0] as '"' | "'")
      : '';
  let end = startIndex;
  let indent = '';
  let hadMultiline = false;
  let openQuote = '';
  const lineBackslashes: number[] = [];
  for (let i = startIndex; i < lines.length; i++) {
    lineBackslashes.push(lines[i].match(/(\\+)$/)?.[0].length ?? 0);
    if (i > startIndex) {
      hadMultiline = true;
      if (!indent) indent = lines[i].match(/^[ \t]*/)?.[0] ?? '';
    }
    const scanned = scanConfigLine(lines[i], openQuote);
    openQuote = scanned.quote;
    end = i;
    if (!openQuote && !scanned.continued) break;
  }

  return {
    start: startIndex,
    end,
    indent,
    quote,
    hadMultiline,
    lineBackslashes,
  };
};

export const formatConfig = (
  source: string,
  config: NfqwsConfig,
  changedKeys?: (keyof NfqwsConfig)[],
): string => {
  const lines = source.split('\n');
  const keys = changedKeys ?? NFQWS_CONFIG_KEYS;
  const seen = new Set<keyof NfqwsConfig>();
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) {
      i += 1;
      continue;
    }

    const eqIndex = line.indexOf('=');
    if (eqIndex === -1) {
      i += 1;
      continue;
    }

    const key = line.slice(0, eqIndex).trim() as keyof NfqwsConfig;
    const block = readBlock(lines, i);
    if (!keys.includes(key)) {
      i = block.end + 1;
      continue;
    }

    seen.add(key);
    const newValue = stringifyValue(key, config[key], block);
    const prefix = line.slice(0, eqIndex + 1);
    lines[i] = `${prefix}${newValue}`;

    if (block.end > i) {
      lines.splice(i + 1, block.end - i);
    }

    i += 1;
  }

  // Configs from the IPv4-only release lack these restored settings.
  for (const key of changedKeys ??
    (['IPV6_ENABLED', 'ASUS_CLIENTS6'] as const)) {
    if (!seen.has(key)) {
      lines.push(`${key}=${stringifyValue(key, config[key], null)}`);
    }
  }
  return lines.join('\n');
};

export const STRATEGY_CONFIG_KEYS = [
  'NFQWS_ARGS',
  'NFQWS_ARGS_QUIC',
  'NFQWS_ARGS_UDP',
  'NFQWS_ARGS_CUSTOM',
] as const;

export const changedConfigKeys = (original: NfqwsConfig, form: NfqwsConfig) =>
  NFQWS_CONFIG_KEYS.filter((key) => original[key] !== form[key]);

function scanConfigLine(line: string, initialQuote: string) {
  let quote = initialQuote;
  let continued = false;
  for (let i = 0; i < line.length; i++) {
    const char = line[i];
    if (quote === "'") {
      if (char === "'") quote = '';
    } else if (char === '\\') {
      if (i === line.length - 1) continued = true;
      i++;
    } else if (quote) {
      if (char === quote) quote = '';
    } else if (char === '#' && (i === 0 || /\s/.test(line[i - 1]))) break;
    else if (char === '"' || char === "'") quote = char;
  }
  return { quote, continued };
}

/** Top-level assignments only: apparent keys inside multiline values are data. */
function assignmentLines(source: string) {
  const assignments: { key: string; from: number; heading: number }[] = [];
  let quote = '';
  let offset = 0;
  let heading: number | null = null;
  let continued = false;
  for (const line of source.split('\n')) {
    if (!quote && !continued) {
      if (line.trimStart().startsWith('#')) heading ??= offset;
      else {
        const match = line.match(/^\s*([A-Z][A-Z0-9_]*)\s*=/);
        if (match)
          assignments.push({
            key: match[1],
            from: offset,
            heading: heading ?? offset,
          });
        heading = null;
      }
    }
    const scanned = scanConfigLine(line, quote);
    quote = scanned.quote;
    continued = scanned.continued;
    offset += line.length + 1;
  }
  return { assignments, closed: !quote && !continued };
}

export function resetStrategyConfig(
  form: NfqwsConfig,
  template: string,
): NfqwsConfig {
  const { assignments, closed } = assignmentLines(template);
  const keys = new Set(assignments.map(({ key }) => key));
  if (
    !template ||
    template.length > 262144 ||
    !closed ||
    STRATEGY_CONFIG_KEYS.some((key) => !keys.has(key))
  ) {
    throw new Error('default_strategy_unavailable');
  }
  const defaults = parseConfig(template);
  if (STRATEGY_CONFIG_KEYS.slice(0, 3).some((key) => !defaults[key].trim())) {
    throw new Error('default_strategy_unavailable');
  }
  return {
    ...form,
    NFQWS_ARGS: defaults.NFQWS_ARGS,
    NFQWS_ARGS_QUIC: defaults.NFQWS_ARGS_QUIC,
    NFQWS_ARGS_UDP: defaults.NFQWS_ARGS_UDP,
    NFQWS_ARGS_CUSTOM: defaults.NFQWS_ARGS_CUSTOM,
  };
}

/** Positions for visual spacing, without inserting any document characters. */
export function configSectionStarts(source: string): number[] {
  const groups: Record<string, string> = {
    ISP_INTERFACE: 'wan',
    NFQWS_BASE_ARGS: 'startup',
    NFQWS_ARGS: 'tcp',
    NFQWS_ARGS_QUIC: 'quic',
    NFQWS_ARGS_UDP: 'udp',
    MODE_LIST: 'mode',
    MODE_ALL: 'mode',
    MODE_AUTO: 'mode',
    NFQWS_EXTRA_ARGS: 'mode',
    NFQWS_ARGS_IPSET: 'ipset',
    NFQWS_ARGS_CUSTOM: 'custom',
    IPV6_ENABLED: 'ports',
    TCP_PORTS: 'ports',
    UDP_PORTS: 'ports',
    POLICY_NAME: 'clients',
    POLICY_EXCLUDE: 'clients',
    ASUS_CLIENT_MODE: 'clients',
    ASUS_CLIENTS4: 'clients',
    ASUS_CLIENTS6: 'clients',
    LOG_LEVEL: 'logging',
    LOG_DEBUG_PATH: 'logging',
    NFQUEUE_NUM: 'runtime',
    USER: 'runtime',
    CONFIG_VERSION: 'runtime',
  };
  let previous: string | undefined;
  const starts: number[] = [];
  for (const { key, heading } of assignmentLines(source).assignments) {
    const group = groups[key];
    if (group && group !== previous) starts.push(heading);
    if (group) previous = group;
  }
  return starts;
}

export type BlobBinding = Readonly<{
  alias: string;
  path: string;
  source: string;
  from: number;
  to: number;
  quote: string;
}>;

type Word = { text: string; raw: string; from: number; to: number };

// Decode shell-style words without evaluating expansions. Offsets always refer
// to the original editor text so unrelated whitespace and arguments stay exact.
function words(source: string): { tokens: Word[]; unsafe: boolean } | null {
  const result: Word[] = [];
  let unsafe = false;
  let at = 0;
  while (at < source.length) {
    if (/\s/.test(source[at])) {
      at++;
      continue;
    }
    if (source.slice(at, at + 2) === '\\\n') {
      at += 2;
      continue;
    }
    if (source[at] === '#') {
      while (at < source.length && source[at] !== '\n') at++;
      continue;
    }
    const from = at;
    let text = '';
    let quote = '';
    while (at < source.length) {
      const c = source[at];
      if (!quote && /\s/.test(c)) break;
      if (
        (!quote && /[;|&()<>]/.test(c)) ||
        (quote !== "'" && (c === '`' || (c === '$' && source[at + 1] === '(')))
      )
        unsafe = true;
      if (c === '\\' && quote !== "'") {
        if (at + 1 >= source.length) return null;
        const next = source[at + 1];
        if (next !== '\n') {
          // In double quotes only shell's special escapes lose the slash.
          if (quote === '"' && !['$', '`', '"', '\\'].includes(next))
            text += '\\';
          text += next;
        }
        at += 2;
        continue;
      }
      if (c === "'" || c === '"') {
        if (!quote) quote = c;
        else if (quote === c) quote = '';
        else text += c;
      } else text += c;
      at++;
    }
    if (quote) return null;
    result.push({ text, raw: source.slice(from, at), from, to: at });
  }
  return { tokens: result, unsafe };
}

export function parseBlobBindings(source: string): {
  bindings: BlobBinding[];
  unsupported: number;
} {
  const parsed = words(source);
  if (!parsed || parsed.unsafe) return { bindings: [], unsupported: 1 };
  const { tokens } = parsed;
  const bindings: BlobBinding[] = [];
  const aliases = new Map<string, number>();
  let unsupported = 0;
  for (let i = 0; i < tokens.length; i++) {
    const option = tokens[i];
    if (option.text !== '--blob' && !option.text.startsWith('--blob='))
      continue;
    const separate = option.text === '--blob';
    const operand = separate
      ? (tokens[i + 1]?.text ?? '')
      : option.text.slice(7);
    // A quoted/escaped option can still declare the same name. Count it before
    // declining its unsupported spelling so a visible slot never hides a duplicate.
    const name = /^([A-Za-z_][A-Za-z0-9_-]{0,63}):/.exec(operand)?.[1];
    if (name) aliases.set(name, (aliases.get(name) ?? 0) + 1);
    let raw: string;
    let from: number;
    let to: number;
    if (option.raw.startsWith('--blob=')) {
      raw = option.raw.slice(7);
      from = option.from + 7;
      to = option.to;
    } else if (option.raw === '--blob' && tokens[i + 1]) {
      const next = tokens[++i];
      raw = next.raw;
      from = next.from;
      to = next.to;
    } else {
      if (separate && tokens[i + 1]) i++;
      unsupported++;
      continue;
    }
    const match = /^([A-Za-z_][A-Za-z0-9_-]{0,63}):@(.+)$/.exec(operand);
    if (!match) {
      // Inline/built-in blob data has no file binding to offer in this picker.
      if (!name || operand.slice(name.length + 1).startsWith('@'))
        unsupported++;
      continue;
    }
    if (
      Array.from(operand).some(
        (c) => c.charCodeAt(0) < 32 || c.charCodeAt(0) === 127,
      ) ||
      /[$`;|&()<>]/.test(operand) ||
      !match[2].startsWith('/')
    ) {
      unsupported++;
      continue;
    }
    const quote =
      (raw.startsWith("'") && raw.endsWith("'")) ||
      (raw.startsWith('"') && raw.endsWith('"'))
        ? raw[0]
        : '';
    bindings.push({ alias: match[1], path: match[2], source, from, to, quote });
  }
  return {
    bindings: bindings.filter((binding) => {
      if (aliases.get(binding.alias) === 1) return true;
      unsupported++;
      return false;
    }),
    unsupported,
  };
}

export function replaceBlobBinding(
  current: string,
  binding: BlobBinding,
  path: string,
): string {
  if (
    !/^\/(?:opt\/)?etc\/nfqws2\/blobs\/[A-Za-z0-9][A-Za-z0-9_.-]*\.bin$/i.test(
      path,
    ) ||
    path.slice(path.lastIndexOf('/') + 1).length > 128
  )
    throw new Error('invalid_path');
  if (current !== binding.source) throw new Error('stale_binding');
  const found = parseBlobBindings(current).bindings.find(
    (candidate) =>
      candidate.alias === binding.alias &&
      candidate.path === binding.path &&
      candidate.from === binding.from &&
      candidate.to === binding.to,
  );
  if (!found) throw new Error('stale_binding');
  const operand = `${found.quote}${found.alias}:@${path}${found.quote}`;
  return current.slice(0, found.from) + operand + current.slice(found.to);
}

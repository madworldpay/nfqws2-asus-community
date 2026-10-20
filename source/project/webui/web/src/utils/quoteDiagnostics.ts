export type QuoteIssue = {
  from: number;
  to: number;
  quote: string;
  line: number;
  column: number;
};

type Context = {
  end?: ')' | '}' | '`';
  depth: number;
  quote: string;
  opener: number;
  ansi: boolean;
};

/** Quote pairing only, never a claim that arbitrary shell code is valid. */
export function findUnclosedQuotes(
  text: string,
  mode: 'conf' | 'arg' = 'conf',
): QuoteIssue[] {
  const stack: Context[] = [{ depth: 0, quote: '', opener: 0, ansi: false }];
  const here: { word: string; tabs: boolean }[] = [];
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    const ctx = stack[stack.length - 1];
    if (ctx.quote === "'") {
      if (ctx.ansi && c === '\\') i++;
      else if (c === "'") ctx.quote = '';
      continue;
    }
    if (c === '\\') {
      i++;
      continue;
    }
    if (c === '$' && ['(', '{'].includes(text[i + 1])) {
      stack.push({
        end: text[i + 1] === '(' ? ')' : '}',
        depth: 1,
        quote: '',
        opener: 0,
        ansi: false,
      });
      i++;
      continue;
    }
    if (c === '`' && ctx.end !== '`') {
      stack.push({ end: '`', depth: 1, quote: '', opener: 0, ansi: false });
      continue;
    }
    if (ctx.quote === '"') {
      if (c === '"') ctx.quote = '';
      continue;
    }
    if (ctx.end && c === ctx.end) {
      if (--ctx.depth === 0) stack.pop();
      continue;
    }
    if ((ctx.end === ')' && c === '(') || (ctx.end === '}' && c === '{')) {
      ctx.depth++;
      continue;
    }
    if (
      mode === 'conf' &&
      c === '#' &&
      (i === 0 || /[\s;|&()<>]/.test(text[i - 1]))
    ) {
      const end = text.indexOf('\n', i);
      i = end < 0 ? text.length : end - 1;
      continue;
    }
    if (
      mode === 'conf' &&
      c === '<' &&
      text[i + 1] === '<' &&
      text[i + 2] !== '<'
    ) {
      const match =
        /^<<(-?)[ \t]*(?:'([^'\n]+)'|"([^"\n]+)"|\\?([A-Za-z_][\w-]*))/.exec(
          text.slice(i),
        );
      if (match) {
        here.push({ word: match[2] || match[3] || match[4], tabs: !!match[1] });
        i += match[0].length - 1;
        continue;
      }
    }
    if (c === '\n' && here.length) {
      let cursor = i + 1;
      for (const delimiter of here.splice(0)) {
        while (cursor < text.length) {
          const end = text.indexOf('\n', cursor);
          const line = text.slice(cursor, end < 0 ? text.length : end);
          cursor = end < 0 ? text.length : end + 1;
          if (
            (delimiter.tabs ? line.replace(/^\t+/, '') : line) ===
            delimiter.word
          )
            break;
        }
      }
      i = cursor - 1;
      continue;
    }
    if (c === "'" || c === '"') {
      ctx.quote = c;
      ctx.opener = i;
      ctx.ansi = c === "'" && text[i - 1] === '$';
    }
  }
  return stack
    .filter((ctx) => ctx.quote)
    .map((ctx) => {
      const before = text.slice(0, ctx.opener);
      return {
        from: ctx.opener,
        to: ctx.opener + 1,
        quote: ctx.quote,
        line: before.split('\n').length,
        column: ctx.opener - before.lastIndexOf('\n'),
      };
    });
}

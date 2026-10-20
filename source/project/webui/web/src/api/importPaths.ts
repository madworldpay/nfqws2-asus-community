import type { ImportDocument } from '@/api/importClient';

type Files = ImportDocument['resources'];
const aliasPattern = /\bRESOURCE_[1-9][0-9]*\b/g;

/** Show one argument per line for canonical single-line strategy values,
 * without changing quoted values, escaped spaces or existing manual layout. */
export function formatImportArguments(value: string): string {
  if (value.includes('\n')) return value;
  let quote = '';
  let result = '';
  for (let i = 0; i < value.length; i++) {
    const char = value[i];
    if (char === '\\' && quote !== "'") {
      result += char + (value[++i] ?? '');
      continue;
    }
    if ((char === '"' || char === "'") && (!quote || quote === char)) {
      quote = quote ? '' : char;
    }
    if (!quote && /[ \t]/.test(char)) {
      let end = i + 1;
      while (end < value.length && /[ \t]/.test(value[end])) end++;
      if (/^--[A-Za-z0-9]/.test(value.slice(end))) {
        result += '\n';
        i = end - 1;
        continue;
      }
    }
    result += char;
  }
  return result;
}

function paths(files: Files) {
  const groups = new Map<string, Files>();
  for (const file of files) {
    if (
      !/^[A-Za-z0-9_.-]{1,128}$/.test(file.name) ||
      ['.', '..'].includes(file.name)
    )
      continue;
    const path = `/opt/etc/nfqws2/${file.kind}/${file.name}`;
    groups.set(path, [...(groups.get(path) ?? []), file]);
  }
  const aliases = new Map<string, string>();
  const conflicts = new Set<string>();
  for (const [path, rows] of groups) {
    // Different contents under one name must keep their separate identities
    // until the importer reports the conflict. Never guess which file to use.
    if (new Set(rows.map((row) => row.sha256)).size > 1) continue;
    for (const row of rows)
      for (const alias of row.aliases ?? []) {
        if (typeof alias !== 'string' || !/^RESOURCE_[1-9][0-9]*$/.test(alias))
          continue;
        if (aliases.has(alias) && aliases.get(alias) !== path)
          conflicts.add(alias);
        else aliases.set(alias, path);
      }
  }
  for (const alias of conflicts) aliases.delete(alias);
  const reverse = new Map<string, string>();
  for (const [alias, path] of aliases)
    if (!reverse.has(path)) reverse.set(path, alias);
  return { aliases, reverse };
}

/** Show the same paths as the normal strategy editor; keep JSON IDs internal. */
export function displayImportValue(value: string, files: Files): string {
  const { aliases } = paths(files);
  let fileOperand = false;
  return value.replace(/\S+/g, (word) => {
    const at = fileOperand || /^--(?:lua-init|blob)=/.test(word);
    fileOperand = word === '--lua-init' || word === '--blob';
    return word.replace(
      /(@?)\b(RESOURCE_[1-9][0-9]*)\b/g,
      (original, marker: string, alias: string) => {
        const path = aliases.get(alias);
        return path ? `${at ? '@' : marker}${path}` : original;
      },
    );
  });
}

/** Preserve dependency selection and the backend's binding checks after edits. */
export function encodeImportValue(value: string, files: Files): string {
  const { reverse } = paths(files);
  if (!reverse.size) return value;
  const names = [...reverse.keys()]
    .sort((a, b) => b.length - a.length)
    .map((path) => path.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  const pattern = new RegExp(
    `(^|[\\s"'=@:,])(${names.join('|')})(?![A-Za-z0-9_./-])`,
    'g',
  );
  return value.replace(
    pattern,
    (_original, prefix: string, path: string) =>
      `${prefix}${reverse.get(path)}`,
  );
}

export function unresolvedImportAliases(value: string, files: Files): string[] {
  const { aliases } = paths(files);
  return [...new Set(value.match(aliasPattern) ?? [])].filter(
    (alias) => !aliases.has(alias),
  );
}

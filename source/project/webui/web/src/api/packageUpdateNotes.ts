export type PackageUpdateNotes = {
  from_build: number;
  to_build: number;
  complete: boolean;
  releases: { build: number; notes: string }[];
};

const RELEASES =
  'https://api.github.com/repos/madworldpay/nfqws2-asus-community/releases';

async function readPage(response: Response) {
  if (
    !response.ok ||
    !/^application\/(?:vnd\.github\+)?json(?:;|$)/i.test(
      response.headers.get('Content-Type') ?? '',
    )
  )
    throw new Error('notes_unavailable');
  const reader = response.body?.getReader();
  if (!reader) throw new Error('notes_unavailable');
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.length;
      if (size > 1048576) throw new Error('notes_unavailable');
      chunks.push(value);
    }
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.length;
  }
  const value: unknown = JSON.parse(new TextDecoder().decode(bytes));
  if (!Array.isArray(value) || value.length > 30)
    throw new Error('notes_unavailable');
  return value as unknown[];
}

async function* releasePages(signal?: AbortSignal) {
  signal?.throwIfAborted();
  const controller = new AbortController();
  const cancel = () => controller.abort();
  signal?.addEventListener('abort', cancel, { once: true });
  const timer = setTimeout(cancel, 10000);
  try {
    for (let page = 1; page <= 4; page++) {
      const releases = await readPage(
        await fetch(`${RELEASES}?per_page=30&page=${page}`, {
          credentials: 'omit',
          referrerPolicy: 'no-referrer',
          redirect: 'error',
          headers: { Accept: 'application/vnd.github+json' },
          signal: controller.signal,
        }),
      );
      yield releases;
      if (releases.length < 30) return;
    }
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', cancel);
  }
}

/** Returns a release page only when it contains a published package for this router. */
export async function getKeeneticPanelUpdate(
  installed: string,
  arch: string,
  signal?: AbortSignal,
) {
  const local = /^(\d+\.\d+\.\d+)\+b([1-9]\d*)-([1-9]\d*)$/.exec(installed);
  if (!local || !['aarch64-3.10', 'mips-3.4', 'mipsel-3.4'].includes(arch))
    return null;
  let build = Number(local[2]),
    revision = Number(local[3]);
  let url: string | null = null;
  for await (const releases of releasePages(signal)) {
    for (const value of releases) {
      if (!value || typeof value !== 'object') continue;
      const r = value as Record<string, unknown>;
      if (
        r.draft !== false ||
        r.prerelease !== false ||
        typeof r.published_at !== 'string' ||
        !r.published_at ||
        typeof r.tag_name !== 'string' ||
        !Array.isArray(r.assets)
      )
        continue;
      const tag = /^keenetic-build([1-9]\d*)(?:-r([1-9]\d*))?$/.exec(
        r.tag_name,
      );
      if (!tag) continue;
      const b = Number(tag[1]),
        rev = Number(tag[2] ?? 1);
      if (
        !Number.isSafeInteger(b) ||
        !Number.isSafeInteger(rev) ||
        b < build ||
        (b === build && rev <= revision)
      )
        continue;
      const suffix = `+b${b}-${rev}_${arch}.ipk`;
      if (
        r.assets.some(
          (a) =>
            typeof a?.name === 'string' &&
            /^nfqws2-keenetic-community_\d+\.\d+\.\d+\+/.test(a.name) &&
            a.name.slice(a.name.indexOf('+')) === suffix &&
            a.state === 'uploaded' &&
            a.size > 0,
        )
      ) {
        build = b;
        revision = rev;
        url = `https://github.com/madworldpay/nfqws2-asus-community/releases/tag/${r.tag_name}`;
      }
    }
  }
  return url;
}

/** Advisory text only. This never selects a package or authorizes installation. */
export async function getPackageUpdateNotes(
  installed: string,
  target: number,
  signal?: AbortSignal,
): Promise<PackageUpdateNotes> {
  const match = installed.match(
    /^[0-9]+\.[0-9]+\.[0-9]+(?:-asus[1-9][0-9]*\+b([1-9][0-9]*)|-r?([1-9][0-9]*))$/,
  );
  const from = Number(match?.[1] ?? match?.[2]);
  if (
    !Number.isSafeInteger(from) ||
    !Number.isSafeInteger(target) ||
    target <= from
  )
    throw new Error('notes_unavailable');
  const entries = new Map<number, string>();
  let complete = false;
  for await (const releases of releasePages(signal)) {
    for (const release of releases) {
      if (!release || typeof release !== 'object')
        throw new Error('notes_unavailable');
      const r = release as Record<string, unknown>;
      if (
        r.draft !== false ||
        r.prerelease !== false ||
        typeof r.published_at !== 'string'
      )
        continue;
      const tag =
        typeof r.tag_name === 'string'
          ? r.tag_name.match(/^build([1-9][0-9]*)$/)
          : null;
      const build = Number(tag?.[1]);
      if (!Number.isSafeInteger(build) || build <= from || build > target)
        continue;
      if (entries.has(build)) throw new Error('notes_unavailable');
      entries.set(
        build,
        typeof r.body === 'string' && r.body.length <= 16000
          ? r.body.trim()
          : '',
      );
    }
    if (releases.length < 30) {
      complete = true;
      break;
    }
  }
  return {
    from_build: from,
    to_build: target,
    complete:
      complete && entries.has(target) && [...entries.values()].every(Boolean),
    releases: [...entries]
      .sort(([a], [b]) => a - b)
      .map(([build, notes]) => ({
        build,
        notes,
      })),
  };
}

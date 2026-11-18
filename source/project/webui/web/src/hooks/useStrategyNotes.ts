import { useEffect, useState } from 'react';

const prefix = 'nfqws2.strategy-note.';

// Encode the publisher's permanent ASCII identifier losslessly. Each catalog
// owns a separate namespace, even when both publish the same identifier.
export function strategyNumber(source: 'library' | 'cloud', id: string) {
  const digits =
    source === 'library'
      ? '1' + id
      : '2' +
        Array.from(id, (char) => char.charCodeAt(0).toString(16)).join('');
  return BigInt('0x' + digits).toString();
}

function readNotes() {
  const notes: Record<string, string> = {};
  try {
    const storage = window.localStorage;
    for (let i = 0; i < storage.length; i++) {
      const key = storage.key(i);
      if (key?.startsWith(prefix)) {
        const id = key.slice(prefix.length);
        if (/^[0-9]+$/.test(id)) notes[id] = storage.getItem(key) ?? '';
      }
    }
    return { notes, unavailable: false };
  } catch {
    return { notes, unavailable: true };
  }
}

export function useStrategyNotes() {
  const [state, setState] = useState(readNotes);
  const [unsaved, setUnsaved] = useState<Set<string>>(() => new Set());
  useEffect(() => {
    const sync = (event: StorageEvent) => {
      if (event.key !== null && !event.key.startsWith(prefix)) return;
      if (event.storageArea !== window.localStorage) return;
      const stored = readNotes();
      setState((previous) => {
        for (const id of unsaved) stored.notes[id] = previous.notes[id] ?? '';
        return stored;
      });
    };
    window.addEventListener('storage', sync);
    return () => window.removeEventListener('storage', sync);
  }, [unsaved]);

  function write(id: string, text: string) {
    let failed = false;
    try {
      if (text) window.localStorage.setItem(prefix + id, text);
      else window.localStorage.removeItem(prefix + id);
    } catch {
      failed = true;
    }
    setState((previous) => ({
      notes: { ...previous.notes, [id]: text },
      unavailable: previous.unavailable && failed,
    }));
    setUnsaved((previous) => {
      if (previous.has(id) === failed) return previous;
      const next = new Set(previous);
      if (failed) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  return {
    notes: state.notes,
    write,
    failed: state.unavailable || unsaved.size > 0,
  };
}

export function matchesStrategy(
  words: string[],
  fields: (string | undefined)[],
) {
  const text = fields.join(' ').toLocaleLowerCase();
  return words.every((word) => text.includes(word));
}

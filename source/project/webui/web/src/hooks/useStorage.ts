export function useStorage() {
  const storageRead = <T = string>(key: string): T | null => {
    const raw = localStorage.getItem(key);
    try {
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  };

  const storageWrite = (key: string, value: unknown) => {
    localStorage.setItem(key, JSON.stringify(value));
  };

  return { storageRead, storageWrite };
}

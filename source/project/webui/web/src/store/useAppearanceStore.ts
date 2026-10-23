import { create } from 'zustand';

export type Appearance = 'classic' | 'rabbit';

function savedAppearance(): Appearance {
  try {
    return localStorage.getItem('nfqws2-appearance') === 'classic'
      ? 'classic'
      : 'rabbit';
  } catch {
    return 'rabbit';
  }
}

export const useAppearanceStore = create<{
  appearance: Appearance;
  setAppearance: (value: Appearance) => void;
}>((set) => ({
  appearance: savedAppearance(),
  setAppearance: (appearance) => {
    try {
      localStorage.setItem('nfqws2-appearance', appearance);
    } catch {
      // The choice still works for this visit when browser storage is unavailable.
    }
    set({ appearance });
  },
}));

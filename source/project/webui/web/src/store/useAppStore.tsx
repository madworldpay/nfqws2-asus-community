import { create } from 'zustand';

type AppStore = {
  auth: boolean | undefined;
  setAuth: (v: boolean) => void;

  needSave: boolean;
  setNeedSave: (v: boolean) => void;

  needReload: boolean;
  setNeedReload: (v: boolean) => void;

  importRestartPending: boolean;
  setImportRestartPending: (v: boolean) => void;

  onSave: () => Promise<void>;
  setOnSave: (v: () => Promise<void>) => void;
};

export const useAppStore = create<AppStore>((set) => ({
  auth: undefined,
  setAuth: (auth) => set({ auth }),

  needSave: false,
  setNeedSave: (needSave) => set({ needSave }),

  needReload: false,
  setNeedReload: (needReload: boolean) => set({ needReload }),

  importRestartPending: false,
  setImportRestartPending: (importRestartPending) => set({ importRestartPending }),

  onSave: async () => {},
  setOnSave: (onSave: () => Promise<void>) => set({ onSave }),
}));

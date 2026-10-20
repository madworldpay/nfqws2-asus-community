import { isValidElement, useCallback, useState, type ReactNode } from 'react';
import { TranslationContext } from '@/context/TranslationContext';
import en from '@/translations/en.json';
import ru from '@/translations/ru.json';

import { useStorage } from '@/hooks/useStorage';

const SUPPORTED_LANGUAGES = ['en', 'ru'] as const;
const DEFAULT_LANGUAGE = 'en';
const STORAGE_KEY = 'lang';

type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];

interface JsonObject {
  [key: string]: JsonValue;
}

type JsonValue = string | JsonObject;

type DotPrefix<T extends string> = T extends '' ? '' : `.${T}`;

type LeafStringPaths<T> = T extends string
  ? ''
  : T extends Record<string, JsonValue>
    ? {
        [K in Extract<keyof T, string>]: T[K] extends string
          ? `${K}`
          : T[K] extends Record<string, JsonValue>
            ? `${K}${DotPrefix<LeafStringPaths<T[K]>>}`
            : never;
      }[Extract<keyof T, string>]
    : never;

export type TranslationSchema = typeof en;
export type TranslationKey = LeafStringPaths<TranslationSchema>;

export type TranslationParamValue = string | number | ReactNode;
export type TranslationParams = Record<string, TranslationParamValue>;

export type TFunction = {
  (key: TranslationKey): string;
  (key: TranslationKey, params: TranslationParams): ReactNode;
};

export type TranslationApi = {
  t: TFunction;
  setLanguage: (lang: SupportedLanguage) => void;
  langcode: SupportedLanguage;
};

const FALLBACK = '__MISSING__';

const resolve = (keys: string[], pack: JsonValue): string | undefined => {
  let current: JsonValue = pack;

  for (const key of keys) {
    if (current && typeof current === 'object' && key in current) {
      current = (current as JsonObject)[key];
    } else {
      return undefined;
    }
  }

  return typeof current === 'string' ? current : undefined;
};

const interpolate = (
  template: string,
  params?: TranslationParams,
): ReactNode => {
  if (!params) return template;

  const allPrimitive = Object.values(params).every(
    (v) => typeof v === 'string' || typeof v === 'number',
  );
  if (allPrimitive) {
    return template.replace(/\{\{(\w+)}}/g, (_, key) =>
      key in params ? String(params[key]) : `{{${key}}}`,
    );
  }

  const re = /\{\{(\w+)}}/g;
  const parts: ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = re.exec(template)) !== null) {
    const [raw, key] = match;
    const index = match.index;

    if (index > lastIndex) {
      parts.push(template.slice(lastIndex, index));
    }

    if (key in params) {
      const value = params[key];
      if (isValidElement(value)) {
        parts.push({ ...value, key: `${key}-${index}` } as ReactNode);
      } else {
        parts.push(value as ReactNode);
      }
    } else {
      parts.push(raw);
    }

    lastIndex = index + raw.length;
  }

  if (lastIndex < template.length) {
    parts.push(template.slice(lastIndex));
  }

  return parts;
};

export const TranslationProvider = ({ children }: { children: ReactNode }) => {
  const { storageRead, storageWrite } = useStorage();

  const getInitialLanguage = () => {
    const saved = storageRead<SupportedLanguage>(STORAGE_KEY);
    if (saved && SUPPORTED_LANGUAGES.includes(saved)) {
      return saved;
    }

    const detected = window.navigator.language?.split(
      '-',
    )[0] as SupportedLanguage;
    if (SUPPORTED_LANGUAGES.includes(detected)) {
      return detected;
    }
    return DEFAULT_LANGUAGE;
  };

  const [language, setLanguageState] =
    useState<SupportedLanguage>(getInitialLanguage());

  const langpack = language === 'ru' ? ru : en;
  const defaultLangpack = en;

  const setLanguage = useCallback(
    (lang: (typeof SUPPORTED_LANGUAGES)[number]) => {
      setLanguageState(lang);
      storageWrite(STORAGE_KEY, lang);
    },
    [storageWrite],
  );

  const t = useCallback(
    (path, params) => {
      const keys = path.split('.');

      const primary = resolve(keys, langpack);
      if (primary !== undefined) {
        return interpolate(primary, params);
      }

      if (langpack !== defaultLangpack) {
        const secondary = resolve(keys, defaultLangpack);
        if (secondary !== undefined) {
          return interpolate(secondary, params);
        }
      }

      return FALLBACK;
    },
    [defaultLangpack, langpack],
  ) as TFunction;

  const value = { t, setLanguage, langcode: language };

  return (
    <TranslationContext.Provider value={value}>
      {children}
    </TranslationContext.Provider>
  );
};

import { createContext } from 'react';
import type { TranslationApi } from '@/context/TranslationProvider';

export const TranslationContext = createContext<TranslationApi | null>(null);

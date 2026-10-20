import { useContext } from 'react';
import { TranslationContext } from '@/context/TranslationContext';

export const useTranslation = () => {
  const ctx = useContext(TranslationContext);
  if (!ctx) {
    throw new Error(
      'useTranslationContext must be used inside TranslationProvider',
    );
  }
  return ctx;
};

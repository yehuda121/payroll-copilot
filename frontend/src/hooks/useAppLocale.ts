import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import {
  applyDocumentLocale,
  isAppLocale,
  LOCALE_META,
  LOCALE_STORAGE_KEY,
  SUPPORTED_LOCALES,
  type AppLocale,
} from '../i18n';

export function useAppLocale() {
  const { i18n, t } = useTranslation();
  const locale = (isAppLocale(i18n.language) ? i18n.language : 'he') as AppLocale;

  const setLocale = useCallback(
    (next: AppLocale) => {
      void i18n.changeLanguage(next);
      try {
        localStorage.setItem(LOCALE_STORAGE_KEY, next);
      } catch {
        // Ignore storage write failures.
      }
      applyDocumentLocale(next);
    },
    [i18n],
  );

  return {
    locale,
    dir: LOCALE_META[locale].dir,
    setLocale,
    supportedLocales: SUPPORTED_LOCALES,
    localeMeta: LOCALE_META,
    t,
  };
}

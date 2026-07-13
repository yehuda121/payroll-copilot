import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import arAccountant from './locales/accountant.ar.json';
import enAccountant from './locales/accountant.en.json';
import heAccountant from './locales/accountant.he.json';
import ar from './locales/ar.json';
import en from './locales/en.json';
import he from './locales/he.json';

export const SUPPORTED_LOCALES = ['he', 'en', 'ar'] as const;
export type AppLocale = (typeof SUPPORTED_LOCALES)[number];

export const LOCALE_STORAGE_KEY = 'payroll-copilot.locale';

export const LOCALE_META: Record<AppLocale, { label: string; dir: 'rtl' | 'ltr' }> = {
  he: { label: 'עברית', dir: 'rtl' },
  en: { label: 'English', dir: 'ltr' },
  ar: { label: 'العربية', dir: 'rtl' },
};

type LocaleBundle = Record<string, unknown>;

/** Deep-merge accountant portal extensions into the base locale bundle. */
export function mergeLocaleBundle(base: LocaleBundle, extension: LocaleBundle): LocaleBundle {
  const result: LocaleBundle = { ...base };
  for (const [key, value] of Object.entries(extension)) {
    const existing = result[key];
    if (
      value &&
      typeof value === 'object' &&
      !Array.isArray(value) &&
      existing &&
      typeof existing === 'object' &&
      !Array.isArray(existing)
    ) {
      result[key] = mergeLocaleBundle(existing as LocaleBundle, value as LocaleBundle);
    } else {
      result[key] = value;
    }
  }
  return result;
}

export function isAppLocale(value: string): value is AppLocale {
  return (SUPPORTED_LOCALES as readonly string[]).includes(value);
}

export function readStoredLocale(): AppLocale {
  try {
    if (typeof localStorage === 'undefined') return 'he';
    const stored = localStorage.getItem(LOCALE_STORAGE_KEY);
    if (stored && isAppLocale(stored)) {
      return stored;
    }
  } catch {
    // Ignore storage errors (private mode, etc.).
  }
  return 'he';
}

export function applyDocumentLocale(locale: AppLocale): void {
  if (typeof document === 'undefined') return;
  const meta = LOCALE_META[locale];
  document.documentElement.lang = locale;
  document.documentElement.dir = meta.dir;
}

void i18n.use(initReactI18next).init({
  resources: {
    he: { translation: mergeLocaleBundle(he as LocaleBundle, heAccountant as LocaleBundle) },
    en: { translation: mergeLocaleBundle(en as LocaleBundle, enAccountant as LocaleBundle) },
    ar: { translation: mergeLocaleBundle(ar as LocaleBundle, arAccountant as LocaleBundle) },
  },
  lng: readStoredLocale(),
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
});

applyDocumentLocale(readStoredLocale());

export default i18n;

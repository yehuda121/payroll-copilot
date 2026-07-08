import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
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

export function isAppLocale(value: string): value is AppLocale {
  return (SUPPORTED_LOCALES as readonly string[]).includes(value);
}

export function readStoredLocale(): AppLocale {
  try {
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
  const meta = LOCALE_META[locale];
  document.documentElement.lang = locale;
  document.documentElement.dir = meta.dir;
}

void i18n.use(initReactI18next).init({
  resources: {
    he: { translation: he },
    en: { translation: en },
    ar: { translation: ar },
  },
  lng: readStoredLocale(),
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
});

applyDocumentLocale(readStoredLocale());

export default i18n;

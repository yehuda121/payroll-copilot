import i18n from 'i18next';
import { beforeAll, describe, expect, it } from 'vitest';
import { LOCALE_META, mergeLocaleBundle } from './index';
import arAccountant from './locales/accountant.ar.json';
import enAccountant from './locales/accountant.en.json';
import heAccountant from './locales/accountant.he.json';
import ar from './locales/ar.json';
import en from './locales/en.json';
import he from './locales/he.json';

function collectKeys(obj: Record<string, unknown>, prefix = ''): string[] {
  const keys: string[] = [];
  for (const [key, value] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      keys.push(...collectKeys(value as Record<string, unknown>, path));
    } else {
      keys.push(path);
    }
  }
  return keys;
}

describe('employee/auth i18n', () => {
  beforeAll(async () => {
    await i18n.init({
      lng: 'en',
      fallbackLng: 'en',
      resources: {
        en: {
          translation: mergeLocaleBundle(
            en as Record<string, unknown>,
            enAccountant as Record<string, unknown>,
          ),
        },
        he: {
          translation: mergeLocaleBundle(
            he as Record<string, unknown>,
            heAccountant as Record<string, unknown>,
          ),
        },
        ar: {
          translation: mergeLocaleBundle(
            ar as Record<string, unknown>,
            arAccountant as Record<string, unknown>,
          ),
        },
      },
    });
  });

  it('has auth + employee navigation keys in all locales', () => {
    const required = [
      'auth.signInTitle',
      'auth.roles.employee',
      'employee.navigation.payslips',
      'employee.payslips.yearLabel',
      'employee.status.passed',
      'common.logout',
      'common.language',
    ];
    for (const lng of Object.keys(LOCALE_META) as Array<'en' | 'he' | 'ar'>) {
      for (const key of required) {
        expect(i18n.getResource(lng, 'translation', key) || i18n.t(key, { lng })).toBeTruthy();
      }
    }
  });

  it('keeps employee payslip keys aligned across locales', () => {
    const enKeys = collectKeys((en as { employee: Record<string, unknown> }).employee, 'employee');
    const heKeys = collectKeys((he as { employee: Record<string, unknown> }).employee, 'employee');
    const arKeys = collectKeys((ar as { employee: Record<string, unknown> }).employee, 'employee');
    expect(heKeys.sort()).toEqual(enKeys.sort());
    expect(arKeys.sort()).toEqual(enKeys.sort());
  });
});

import i18n from 'i18next';
import { describe, expect, it, beforeAll } from 'vitest';
import {
  getBatchStageLabel,
  getBatchStatusLabel,
  getDocumentStatusLabel,
  getDocumentTypeLabel,
  getEmployeeStatusLabel,
  getValidationModuleName,
} from './accountantLabels';
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

describe('accountant i18n', () => {
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
      interpolation: { escapeValue: false },
    });
  });

  it('keeps accountant extension keys in sync across en/he/ar', () => {
    const enKeys = collectKeys(enAccountant as Record<string, unknown>).sort();
    const heKeys = collectKeys(heAccountant as Record<string, unknown>).sort();
    const arKeys = collectKeys(arAccountant as Record<string, unknown>).sort();
    expect(heKeys).toEqual(enKeys);
    expect(arKeys).toEqual(enKeys);
  });

  it('maps employee and document statuses to translated labels', async () => {
    await i18n.changeLanguage('en');
    expect(getEmployeeStatusLabel('active', i18n.t.bind(i18n))).toBe('Active');
    expect(getDocumentStatusLabel('missing', i18n.t.bind(i18n))).toBe('Missing');
    await i18n.changeLanguage('he');
    expect(getEmployeeStatusLabel('active', i18n.t.bind(i18n))).toBe('פעיל');
    expect(getDocumentStatusLabel('missing', i18n.t.bind(i18n))).toBe('חסר');
  });

  it('maps batch statuses and stages', async () => {
    await i18n.changeLanguage('en');
    expect(getBatchStatusLabel('running', i18n.t.bind(i18n))).toBe('Running');
    expect(getBatchStageLabel('ocr', i18n.t.bind(i18n))).toBe('OCR');
  });

  it('resolves document type and validation module registry labels', async () => {
    await i18n.changeLanguage('en');
    expect(getDocumentTypeLabel('payslip', i18n.t.bind(i18n))).toBe('Payslips');
    expect(getValidationModuleName('payroll', i18n.t.bind(i18n))).toBe('Payroll validation');
  });

  it('supports interpolation for dynamic values', async () => {
    await i18n.changeLanguage('en');
    expect(
      i18n.t('accountant.employees.createMessage', { number: 'E-1', name: 'Ada Lovelace' }),
    ).toContain('E-1');
    expect(
      i18n.t('accountant.batches.slipsProgress', { processed: 3, total: 10 }),
    ).toBe('3/10');
  });

  it('applies RTL for Hebrew and Arabic and LTR for English', () => {
    expect(LOCALE_META.he.dir).toBe('rtl');
    expect(LOCALE_META.ar.dir).toBe('rtl');
    expect(LOCALE_META.en.dir).toBe('ltr');
  });

  it('includes required accountant navigation keys after merge', () => {
    const merged = mergeLocaleBundle(
      en as Record<string, unknown>,
      enAccountant as Record<string, unknown>,
    );
    const keys = new Set(collectKeys(merged));
    expect(keys.has('accountant.navigation.dashboard')).toBe(true);
    expect(keys.has('common.save')).toBe(true);
    expect(keys.has('common.cancel')).toBe(true);
  });
});

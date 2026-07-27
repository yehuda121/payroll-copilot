import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { TFunction } from 'i18next';
import i18n from 'i18next';
import { beforeAll } from 'vitest';
import { getDisplayError, isNetworkFetchError } from '../getDisplayError';
import { checkRowStatusVisual, summarizeCheckRows, type CheckCatalogRow } from './check-catalog';
import { detectEmployeeFieldType, formatFieldPreview } from './field-types';
import { mergeLocaleBundle } from '../../i18n';
import arAccountant from '../../i18n/locales/accountant.ar.json';
import enAccountant from '../../i18n/locales/accountant.en.json';
import heAccountant from '../../i18n/locales/accountant.he.json';
import ar from '../../i18n/locales/ar.json';
import en from '../../i18n/locales/en.json';
import he from '../../i18n/locales/he.json';

const root = join(process.cwd(), 'src');

function read(rel: string): string {
  return readFileSync(join(root, rel), 'utf8');
}

const t = ((key: string) => key) as TFunction;

function row(status: CheckCatalogRow['status']): CheckCatalogRow {
  return {
    key: `k-${status}`,
    ruleId: 'employee.name.match',
    taxonomy: 'employee',
    uiGroup: 'employee_checks',
    title: 'Name',
    status,
    deterministicStatus: status === 'manually_approved' ? 'failed' : status,
    explanation: null,
    skipReasonKey: null,
    reasonCode: null,
    findingId: null,
    approvalReason: null,
  };
}

describe('Scope A validation UI hardening', () => {
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

  it('maps summary statuses to distinct semantic CSS tokens', () => {
    expect(checkRowStatusVisual('passed', t).css).toBe('is-passed');
    expect(checkRowStatusVisual('failed', t).css).toBe('is-failed');
    expect(checkRowStatusVisual('uncertain', t).css).toBe('is-uncertain');
    expect(checkRowStatusVisual('not_run', t).css).toBe('is-not-run');

    const css = read('features/employee/employee-payslip.css');
    expect(css).toMatch(
      /\.employee-validation-summary__compact-counts \.is-passed[\s\S]*?var\(--color-success/,
    );
    expect(css).toMatch(
      /\.employee-validation-summary__compact-counts \.is-failed[\s\S]*?var\(--color-danger/,
    );
    expect(css).toMatch(
      /\.employee-validation-summary__compact-counts \.is-uncertain[\s\S]*?var\(--color-warning/,
    );
    expect(css).toMatch(
      /\.employee-validation-summary__compact-counts \.is-not-run[\s\S]*?var\(--color-surface/,
    );
  });

  it('keeps summary counts unchanged for mixed statuses', () => {
    const summary = summarizeCheckRows([
      row('passed'),
      row('passed'),
      row('failed'),
      row('uncertain'),
      row('not_run'),
      row('manually_approved'),
    ]);
    expect(summary.passed).toBe(2);
    expect(summary.failed).toBe(2); // failed + manually_approved(deterministic failed)
    expect(summary.uncertain).toBe(1);
    expect(summary.not_run).toBe(1);
    expect(summary.manually_approved).toBe(1);
    expect(summary.total).toBe(6);
  });

  it('localizes Run again / Approve manually in en, he, and ar', async () => {
    for (const lng of ['en', 'he', 'ar'] as const) {
      await i18n.changeLanguage(lng);
      expect(i18n.t('employee.validation.actions.runAgain')).not.toMatch(/employee\.validation/);
      expect(i18n.t('employee.validation.actions.approveManually')).not.toMatch(/employee\.validation/);
      expect(i18n.t('employee.validation.originalCheck', { status: 'failed' })).not.toMatch(
        /employee\.validation/,
      );
      expect(i18n.t('employee.validation.actions.rerunFailed')).not.toMatch(/employee\.validation/);
      expect(i18n.t('employee.validation.actions.approveFailed')).not.toMatch(/employee\.validation/);
      expect(i18n.t('common.networkUnavailable')).not.toMatch(/common\./);
    }
    expect(i18n.t('employee.validation.actions.runAgain', { lng: 'en' })).toBe('Run again');
    expect(i18n.t('employee.validation.actions.approveManually', { lng: 'en' })).toBe(
      'Approve manually',
    );
  });

  it('places delete action inline with the field value row', () => {
    const form = read('features/employee/EmployeeDigitalForm.tsx');
    expect(form).toContain('employee-digital-form__value-row');
    expect(form).toContain('onRemoveField');
    expect(form).toMatch(
      /employee-digital-form__value-row[\s\S]*?digital-form__value-btn[\s\S]*?onRemoveField[\s\S]*?Trash2/,
    );
    expect(form).not.toMatch(
      /employee-digital-form__card-footer[\s\S]{0,400}requestDeleteField/,
    );

    const css = read('pages/employee/PayslipMonthWorkspace.css');
    expect(css).toContain('.employee-digital-form__value-row');
    expect(css).toMatch(
      /\.employee-digital-form__value-row[\s\S]*?display:\s*flex/,
    );
  });

  it('preserves identifier formatting without thousands separators', () => {
    expect(detectEmployeeFieldType('national_id', '313366783')).toBe('identifier');
    expect(formatFieldPreview('313366783', 'identifier', 'en')).toBe('313366783');
    expect(formatFieldPreview('313366783', 'identifier', 'he')).toBe('313366783');
    expect(formatFieldPreview('5300', 'currency', 'en')).not.toBe('313366783');
  });

  it('maps Failed to fetch to i18n network copy instead of raw English', () => {
    expect(isNetworkFetchError(new Error('Failed to fetch'))).toBe(true);
    expect(
      getDisplayError(new Error('Failed to fetch'), 'fallback', {
        networkFallback: 'Unable to reach the server',
      }),
    ).toBe('Unable to reach the server');
  });

  it('does not show validation errors while loading', () => {
    const results = read('features/employee/EmployeeValidationResults.tsx');
    expect(results).toContain('errorMessage && !loading && !validating');
  });

  it('splits batch workspace vs action errors to avoid duplicate Failed to fetch', () => {
    const page = read('pages/accountant/BatchItemReviewWorkspace.tsx');
    expect(page).toContain('workspaceError');
    expect(page).toContain('actionError');
    expect(page).toContain('getDisplayError');
    expect(page).toContain('common.networkUnavailable');
    expect(page).not.toMatch(/setError\(reason instanceof Error \? reason\.message/);
  });

  it('keeps compact Validation Summary rail structure', () => {
    const results = read('features/employee/EmployeeValidationResults.tsx');
    expect(results).toContain('employee-validation-summary--rail');
    expect(results).toContain('employee-validation-summary__compact-counts');
    expect(results).toContain('employee.validation.status.passed');
    expect(results).toContain('employee.validation.status.failed');
    expect(results).toContain('employee.validation.status.uncertain');
    expect(results).toContain('employee.validation.status.notRun');
  });

  it('Employee and Accountant month workspace use shared checkRows presentation', () => {
    const page = read('pages/employee/PayslipMonthWorkspace.tsx');
    expect(page).toContain('presentation="checkRows"');
    expect(page).not.toContain("presentation={batchReview ? 'checkRows' : 'default'}");
    expect(page).toContain('canRerun: true');
    expect(page).toContain('canManualApprove: true');
    expect(page).toContain('approveFinding');
    expect(page).toContain("runValidation('rules'");
    expect(page).toContain('employee.upload.tabOriginal');
    expect(page).toContain('ensureOriginalPreview');
    expect(page).toContain('originalPreviewError');
  });

  it('scopes Original Document failures away from workspace/validation error', () => {
    const hook = read('hooks/useEmployeeMonthWorkspace.ts');
    expect(hook).toContain('originalPreviewError');
    expect(hook).toContain('ensureOriginalPreview');
    expect(hook).toContain('Scoped to Original Document only');
    // Must not eagerly fetch content on every documentId change into setError.
    expect(hook).not.toMatch(
      /fetchDocumentContentBlob[\s\S]{0,400}setError\(\s*toUserFacingError/,
    );
    expect(hook).toMatch(
      /setOriginalPreviewError\(\s*toUserFacingError/,
    );
  });

  it('manual approval UI keeps deterministic overlay semantics in catalog', () => {
    const catalog = read('lib/employee/check-catalog.ts');
    expect(catalog).toContain('deterministicStatus');
    expect(catalog).toContain('manually_approved');
    expect(catalog).toContain('Immutable deterministic outcome');
    const summary = summarizeCheckRows([row('manually_approved')]);
    expect(summary.failed).toBe(1);
    expect(summary.passed).toBe(0);
    expect(summary.manually_approved).toBe(1);
  });
});

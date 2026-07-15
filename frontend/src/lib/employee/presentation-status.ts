/**
 * Maps backend payroll-month presentation/status codes to UI categories.
 *
 * This utility does NOT evaluate payroll law. It only maps stable backend codes
 * already produced by identity comparison / validation persistence into
 * presentation buckets for Employee Portal chrome.
 *
 * Backend `presentation_status` values (preferred):
 * - passed      → success (green)
 * - error       → error (red)
 * - warning     → warning (yellow)
 * - unavailable → unavailable (gray)
 *
 * Fallback mapping when only validation overall_result/severity is present:
 * - critical → error
 * - warnings / warning / low confidence → warning
 * - pass → success
 * - missing / not_run / null → unavailable
 */

export type PresentationCategory = 'success' | 'error' | 'warning' | 'unavailable';

export type StatusVisual = {
  category: PresentationCategory;
  /** i18n key under employee.status.* */
  labelKey: string;
  /** Accessible icon character (not color-only). */
  icon: string;
  cssClass: string;
};

const CATEGORY_VISUAL: Record<PresentationCategory, Omit<StatusVisual, 'category'>> = {
  success: {
    labelKey: 'employee.status.passed',
    icon: '✓',
    cssClass: 'status-badge--success',
  },
  error: {
    labelKey: 'employee.status.error',
    icon: '!',
    cssClass: 'status-badge--error',
  },
  warning: {
    labelKey: 'employee.status.warning',
    icon: '⚠',
    cssClass: 'status-badge--warning',
  },
  unavailable: {
    labelKey: 'employee.status.unavailable',
    icon: '–',
    cssClass: 'status-badge--unavailable',
  },
};

export function mapPresentationStatus(code: string | null | undefined): StatusVisual {
  const normalized = (code || '').toLowerCase();
  let category: PresentationCategory = 'unavailable';
  if (normalized === 'passed' || normalized === 'pass' || normalized === 'success') {
    category = 'success';
  } else if (normalized === 'error' || normalized === 'critical' || normalized === 'failed') {
    category = 'error';
  } else if (
    normalized === 'warning' ||
    normalized === 'warnings' ||
    normalized === 'uncertain' ||
    normalized === 'pending' ||
    normalized === 'running'
  ) {
    category = 'warning';
  } else {
    category = 'unavailable';
  }
  return { category, ...CATEGORY_VISUAL[category] };
}

export function mapOverallResultToPresentation(
  overallResult: string | null | undefined,
  highestSeverity?: string | null,
): PresentationCategory {
  const result = (overallResult || '').toLowerCase();
  const severity = (highestSeverity || '').toLowerCase();
  if (result === 'critical' || severity === 'critical') return 'error';
  if (result === 'warnings' || severity === 'warning') return 'warning';
  if (result === 'pass') return 'success';
  return 'unavailable';
}

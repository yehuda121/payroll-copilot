import { describe, expect, it } from 'vitest';
import {
  mapOverallResultToPresentation,
  mapPresentationStatus,
} from '../../lib/employee/presentation-status';

describe('employee presentation status mapping', () => {
  it('maps backend presentation statuses to categories with labels and icons', () => {
    expect(mapPresentationStatus('passed').category).toBe('success');
    expect(mapPresentationStatus('error').category).toBe('error');
    expect(mapPresentationStatus('warning').category).toBe('warning');
    expect(mapPresentationStatus('unavailable').category).toBe('unavailable');
    expect(mapPresentationStatus('passed').labelKey).toBe('employee.status.passed');
    expect(mapPresentationStatus('error').icon).toBeTruthy();
  });

  it('does not invent law outcomes from overall_result alone beyond code mapping', () => {
    expect(mapOverallResultToPresentation('critical')).toBe('error');
    expect(mapOverallResultToPresentation('warnings')).toBe('warning');
    expect(mapOverallResultToPresentation('pass')).toBe('success');
    expect(mapOverallResultToPresentation(null)).toBe('unavailable');
  });
});

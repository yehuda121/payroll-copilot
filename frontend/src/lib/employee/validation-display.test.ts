import { describe, expect, it } from 'vitest';
import {
  mapCompareToCardStatus,
  mapFindingToCardStatus,
  mapScopeToCardStatus,
} from './validation-display';

describe('employee validation card status mapping', () => {
  it('never marks missing data as passed', () => {
    expect(
      mapFindingToCardStatus({
        severity: 'info',
        message_key: 'validation.missing_data',
      }),
    ).toBe('unchecked');
    expect(
      mapFindingToCardStatus({
        severity: 'passed',
        message_key: 'validation.missing_data',
      }),
    ).toBe('unchecked');
  });

  it('maps executed outcomes consistently', () => {
    expect(mapFindingToCardStatus({ severity: 'critical' })).toBe('failed');
    expect(mapFindingToCardStatus({ severity: 'warning' })).toBe('uncertain');
    expect(mapFindingToCardStatus({ severity: 'pass' })).toBe('passed');
  });

  it('maps compare and scope statuses', () => {
    expect(mapCompareToCardStatus('match')).toBe('passed');
    expect(mapCompareToCardStatus('mismatch')).toBe('failed');
    expect(mapCompareToCardStatus('uncertain')).toBe('uncertain');
    expect(mapCompareToCardStatus('missing')).toBe('unchecked');
    expect(mapCompareToCardStatus('cannot_validate')).toBe('unchecked');
    expect(mapScopeToCardStatus('completed')).toBe('passed');
    expect(mapScopeToCardStatus('partial')).toBe('uncertain');
    expect(mapScopeToCardStatus('not_available')).toBe('unchecked');
    expect(mapScopeToCardStatus('completed', 'payroll_core_fields_incomplete')).toBe('unchecked');
  });
});
